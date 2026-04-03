# 后台任务：定时调度、后台 Agent 与 Dream

## 一句话理解

Claude Code 不只是一个"你问我答"的工具。它可以**在后台默默干活**：比如一个 Agent 在后台搜索代码，一个定时任务每小时检查一次构建状态，或者一个"Dream"任务在你不用的时候整理记忆。

> **比喻**：如果前台对话是你在和秘书面对面沟通，那后台任务就是秘书回到办公室后帮你做的事——不需要你盯着，做完了给你发个通知。

## 什么是后台任务

```typescript
// src/tasks/types.ts (lines 22-46)
function isBackgroundTask(task) {
  // 条件1: 任务正在运行或等待中
  if (task.status !== 'running' && task.status !== 'pending') return false

  // 条件2: 任务已经被放到后台（或天生就是后台任务）
  if ('isBackgrounded' in task && task.isBackgrounded === false) return false

  return true
}
```

能在后台运行的任务类型：

| 类型 | 说明 | 如何进入后台 |
|------|------|-------------|
| LocalAgentTask | AI Agent | 创建时指定 `run_in_background` 或 Ctrl+B |
| LocalShellTask | Bash 命令 | 长时间运行时自动后台 |
| RemoteAgentTask | 远程 Agent | 天生后台（在云端执行） |
| InProcessTeammateTask | 队友 Agent | 天生后台 |
| DreamTask | 记忆整理 | 天生后台 |

## 后台 Agent 的执行模型

后台 Agent 和前台 Agent 运行的是**完全相同的 query() 循环**，区别只在于：

```
前台 Agent                     后台 Agent
──────────                    ──────────
共享父级的 AbortController      独立的 AbortController
输出实时显示在终端              输出写入磁盘文件
权限弹窗可以交互               不能弹窗（自动拒绝）
阻塞主流程                     不阻塞主流程
结果直接返回                   结果通过通知送达
```

### 创建后台 Agent

```typescript
// 用户代码或主 Agent 调用
Agent({
  description: "审计认证模块",
  prompt: "检查 src/auth/ 下的所有安全隐患",
  subagent_type: "Explore",
  run_in_background: true  // ← 关键参数
})
```

内部处理：

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx (lines 466-515)
function registerAsyncAgent({ agentId, prompt, ... }) {
  return {
    type: 'local_agent',
    status: 'running',
    isBackgrounded: true,     // 后台标记
    abortController: new AbortController(),  // 独立的中断控制
    pendingMessages: [],      // 接收 SendMessage 的邮箱
    // ...
  }
}
```

### 通知机制

后台 Agent 完成后，生成 XML 通知插入到主 Agent 的消息队列：

```xml
<task-notification>
  <task-id>a8f2x9kq</task-id>
  <status>completed</status>
  <summary>找到 3 个潜在安全隐患</summary>
  <result>
    1. src/auth/login.ts:42 - SQL 注入风险
    2. src/auth/session.ts:87 - Token 未过期处理
    3. src/auth/middleware.ts:15 - 缺少 CSRF 防护
  </result>
  <usage>
    <total_tokens>15234</total_tokens>
    <tool_uses>12</tool_uses>
    <duration_ms>8500</duration_ms>
  </usage>
</task-notification>
```

主 Agent 在下一轮循环时读到这个通知，就能基于后台 Agent 的发现继续工作。

## 前台 ↔ 后台切换

Agent 可以在前后台之间切换：

```
用户正在和 Agent 对话
        │
        │ 按 Ctrl+B
        ▼
┌─────────────────────────┐
│ backgroundAgentTask()    │
│                          │
│ isBackgrounded: false    │
│         ↓                │
│ isBackgrounded: true     │
│                          │
│ Agent 继续在后台运行      │
│ 用户可以开始新对话        │
└─────────────────────────┘
        │
        │ 收到通知后，可以切回前台
        ▼
┌─────────────────────────┐
│ foregroundMainSession()  │
│                          │
│ 恢复显示 Agent 的消息    │
│ 用户可以继续对话         │
└─────────────────────────┘
```

## DreamTask：记忆整理

Dream 是一种特殊的后台任务，功能是**整理和归纳记忆**。

> **比喻**：就像人在睡觉时大脑会整理白天的记忆一样。Dream 任务在空闲时"复盘"之前的对话，把分散的记忆整理成有条理的笔记。

```typescript
// src/tasks/DreamTask/DreamTask.ts (lines 25-41)
type DreamTaskState = {
  type: 'dream',
  phase: 'starting' | 'updating',  // 阶段
  sessionsReviewing: number,         // 正在复盘多少个会话
  filesTouched: string[],            // 修改了哪些记忆文件
  turns: DreamTurn[],                // 执行过程记录
  abortController: AbortController,
  priorMtime: number,                // 整理锁的时间戳（用于回滚）
}
```

### Dream 的生命周期

```
用户空闲时
    │
    ▼
┌──────────────────────────────────┐
│ 创建 DreamTask                    │
│ phase: 'starting'                 │
│                                   │
│  读取最近的对话历史                  │
│  分析需要整理的记忆                  │
│                                   │
│  第一次使用 Edit/Write 工具时：     │
│  phase → 'updating'               │
│                                   │
│  整理 MEMORY.md 索引               │
│  更新/创建记忆文件                   │
│  最多 30 轮                         │
│                                   │
│  完成 → 标记 notified=true          │
│  （不发通知给用户，静默完成）          │
└──────────────────────────────────┘
```

Dream 有一个特殊设计：**可回滚**。如果 Dream 被用户中断（abort），它会把整理锁的时间戳恢复到之前的值，这样下次可以重新整理。

## Cron 定时任务

Claude Code 内置了一个定时调度器，可以按 cron 表达式定期执行任务。

### 存储

定时任务存在两个地方：

```
持久化任务: .claude/scheduled_tasks.json  ← 重启后仍在
会话任务:   内存中                         ← 关闭就没了
```

```typescript
// src/utils/cronTasks.ts (lines 1-70)
type CronTask = {
  id: string,         // 8位随机 ID
  cron: string,        // cron 表达式 "0 9 * * 1-5" (工作日9点)
  prompt: string,      // 触发时执行的 prompt
  recurring: boolean,  // 是否重复
  durable: boolean,    // 是否持久化
  lastFiredAt?: number, // 上次触发时间
}
```

### 调度器核心

```typescript
// src/utils/cronScheduler.ts (lines 40-44)
const CHECK_INTERVAL_MS = 1000       // 每秒检查一次
const LOCK_PROBE_INTERVAL_MS = 5000  // 非所有者每5秒检查锁
```

调度器是一个**每秒检查一次的循环**：

```
每 1 秒
    │
    ▼
遍历所有定时任务
    │
    ├─ 还没到时间 → 跳过
    │
    └─ 到时间了 → 触发！
         │
         ├─ 一次性任务 → 执行后删除
         │
         └─ 重复任务 → 执行 + 计算下次时间
              │
              └─ 加入随机延迟（防止雷群效应）
```

### 防雷群效应（Jitter）

如果 1000 个用户都设了"每天早上9点"，所有请求会同时打到服务器。所以系统加入了**随机延迟**：

```typescript
// src/utils/cronTasks.ts (lines 348-355)
const JITTER_CONFIG = {
  recurringFrac: 0.1,          // 间隔时间的 10%
  recurringCapMs: 15 * 60_000, // 最多延迟 15 分钟
  oneShotMaxMs: 90_000,        // 一次性任务最多提前 90 秒
}
```

```
设定时间: 09:00
实际触发: 09:00 ~ 09:06 之间的随机时刻（对于每小时任务）
```

> **比喻**：就像下课铃响了，不是所有人同时冲出教室，而是错开几分钟出去——避免堵在门口。

### 多会话互斥

如果你开了两个 Claude Code 窗口，定时任务不能触发两次。系统用**文件锁**来保证：

```typescript
// src/utils/cronTasksLock.ts (lines 25-31)
// 锁文件: .claude/scheduled_tasks.lock
{
  sessionId: "abc123",  // 谁持有锁
  pid: 12345,           // 进程 ID（用于检测进程是否还活着）
  acquiredAt: 17...     // 什么时候拿到的锁
}
```

```
窗口 A: 成功获取锁 → 负责触发持久化任务
窗口 B: 获取锁失败 → 每5秒检查一次，如果 A 的进程死了，接管锁

两个窗口: 各自独立管理自己的会话级任务（不需要锁）
```

### Cron 工具

用户通过三个工具管理定时任务：

```typescript
// CronCreate: 创建定时任务
CronCreate({
  cron: "0 9 * * 1-5",       // 工作日早上9点
  prompt: "检查 CI 构建状态",
  recurring: true,
  durable: true,              // 持久化，重启后仍在
})
// → 返回 { id: "a1b2c3d4", humanSchedule: "Every weekday at 9:00 AM" }

// CronList: 列出所有定时任务
// CronDelete: 删除定时任务
```

## 远程后台 Agent

某些任务可以在**远程云环境**中执行：

```typescript
// src/utils/background/remote/remoteSession.ts (lines 14-26)
type BackgroundRemoteSession = {
  id: string,
  command: string,
  status: 'starting' | 'running' | 'completed' | 'failed' | 'killed',
  todoList: TodoList,  // 远程任务的进度列表
  log: SDKMessage[],    // 累积的远程事件日志
}
```

远程 Agent 的特点：
- 在云端执行，不占用本地资源
- 通过轮询获取进度更新
- 可以访问 GitHub 仓库（需要安装 GitHub App）
- 可以被 `--resume` 恢复连接

### 前提条件

```typescript
// src/utils/background/remote/remoteSession.ts (lines 45-98)
// 启动远程 Agent 需要满足：
// 1. 已登录 claude.ai
// 2. 有远程环境的访问权限
// 3. 在 Git 仓库中
// 4. GitHub App 已安装（如果是 GitHub 仓库）
// 5. 策略允许远程会话
```

## 收件箱轮询

后台 Agent 之间（特别是 Teammate 类型）通过**收件箱**通信：

```typescript
// src/hooks/useInboxPoller.ts (lines 126-131)
function useInboxPoller({ enabled, onSubmitMessage }) {
  // 每 1 秒轮询一次收件箱
  // 分类处理收到的消息：
  //   - 权限请求 → 路由到权限队列
  //   - 权限回复 → 触发回调
  //   - 普通消息 → 排队等待空闲时提交
  //   - 模式设置 → 更新权限模式
}
```

## 整体架构图

```
┌────────────────────────────────────────────────────────┐
│                    Claude Code 主进程                     │
│                                                          │
│  ┌─────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 前台对话  │  │ 后台Agent │  │  Dream   │  │ Cron    │ │
│  │         │  │ (搜索中)  │  │ (整理中)  │  │ 调度器   │ │
│  │ 用户 ◄──┤  │          │  │          │  │         │ │
│  │  交互   │  │  输出→磁盘 │  │  静默执行 │  │ 每秒检查 │ │
│  └────┬────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │            │             │              │       │
│       │     ┌──────┘             │              │       │
│       │     │  task-notification │              │       │
│       │     ▼                    │              │       │
│  ┌────┴──────────────────────────┴──────────────┴────┐ │
│  │               消息队列 + 事件分发                     │ │
│  │  通知、定时触发、收件箱消息都在这里排队                  │ │
│  └───────────────────────────────────────────────────┘ │
│                                                          │
│  ┌───────────────────────────────────────────────────┐  │
│  │                  磁盘存储                           │  │
│  │  tasks/*.output   scheduled_tasks.json   memory/  │  │
│  └───────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

## 小结

后台任务系统的设计让 Claude Code 从一个"聊天工具"变成了一个**长期运行的工作平台**：

1. **后台 Agent**：不阻塞前台，完成后通知。像多线程编程一样并行工作
2. **Dream**：空闲时自动整理记忆，静默完成不打扰用户
3. **Cron 调度**：文件锁保证不重复执行，Jitter 防止服务器过载
4. **远程执行**：大任务可以放到云端跑
5. **收件箱**：后台 Agent 之间通过消息队列协作

> **比喻**：整个系统就像一个 7x24 小时运转的办公室。有人在前台接待客户（前台对话），有人在后台处理文件（后台 Agent），有保洁阿姨定时打扫（Cron），还有人在深夜整理档案（Dream）。每个人干完活就在公告板（消息队列）上贴个便条。
