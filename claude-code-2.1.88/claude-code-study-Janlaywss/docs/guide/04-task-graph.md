# 任务图：状态机、父子关系与回收

## 一句话理解

当你在 Claude Code 中运行一个复杂操作——比如后台跑一个 Agent，同时执行一个 Bash 命令，再加上一个定时任务——这些东西需要被**统一管理**。任务图就是 Claude Code 用来跟踪"谁在做什么、做到哪了、什么时候清理"的系统。

> **比喻**：想象一个快递公司的调度中心。每个快递（任务）有状态（在途/已送达/退回），有关系（A 快递是 B 快递的附件），有超时回收机制（无人领取的快递 30 天后销毁）。

## 7 种任务类型

```typescript
// src/Task.ts (lines 6-13)
type TaskType =
  | 'local_bash'            // 本地 Shell 命令
  | 'local_agent'           // 本地 AI Agent
  | 'remote_agent'          // 远程云端 Agent
  | 'in_process_teammate'   // 进程内队友 Agent
  | 'local_workflow'        // 工作流脚本
  | 'monitor_mcp'           // MCP 监控
  | 'dream'                 // 记忆整理（Dream）
```

每种类型就像不同岗位的员工，虽然做的事不同，但都遵循同一套考勤规则。

## 状态机：一个任务的一生

所有任务都遵循同一个状态机：

```
         创建任务
            │
            ▼
    ┌──────────────┐
    │   pending     │  ← 排队等待
    │   (等待中)     │
    └──────┬───────┘
           │ 开始执行
           ▼
    ┌──────────────┐
    │   running     │  ← 正在工作
    │   (执行中)     │
    └──┬───┬───┬───┘
       │   │   │
  完成  │  失败│  被杀│
       ▼   ▼   ▼
    ┌────┐┌────┐┌────┐
    │完成 ││失败 ││终止 │  ← 三种结束状态
    │    ││    ││    │
    └─┬──┘└─┬──┘└─┬──┘
      │     │     │
      └──┬──┴──┬──┘
         │     │
    发送通知    │
    notified=true
         │     │
         ▼     ▼
    ┌──────────────┐
    │   可回收      │  ← 等待被清理
    │   (GC ready)  │
    └──────────────┘
```

### 判断是否终结

```typescript
// src/Task.ts (lines 15-28)
function isTerminalTaskStatus(status: TaskStatus): boolean {
  return status === 'completed'
      || status === 'failed'
      || status === 'killed'
}
```

## 任务存储：一个扁平的字典

所有任务存放在一个**扁平的 Map** 中，没有树形结构：

```typescript
// src/state/AppStateStore.ts (line 160)
type AppState = {
  tasks: { [taskId: string]: TaskState }  // 扁平字典
  foregroundedTaskId?: string              // 当前前台任务
  viewingAgentTaskId?: string              // 正在查看的 Agent
}
```

> **为什么是扁平的？** 因为父子关系是通过**字段引用**而非**嵌套结构**表达的。这样更新一个子任务时，不需要深层修改父任务对象。

## Task ID 设计

```typescript
// src/Task.ts (lines 98-106)
const TASK_ID_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz'

function generateTaskId(prefix: string): string {
  // 前缀 + 8位随机字符
  // 'a' = agent, 'b' = bash, 'r' = remote, 'd' = dream
  return prefix + randomChars(8, TASK_ID_ALPHABET)
}
// 例如: "a8f2x9kq" (agent), "b3m7p2nt" (bash)
```

为什么用 8 位随机字符？**36^8 ≈ 2.8 万亿种组合**，即使是恶意攻击者也几乎不可能猜到一个有效的 task ID（防止符号链接攻击等）。

## 父子关系：三种模式

虽然存储是扁平的，但任务之间有三种父子关系：

### 1. Agent → Bash（生成关系）

```
Agent 任务 (agentId: "a8f2x9kq")
  │
  │ 执行 Bash 命令时
  │
  └──▶ Bash 任务 (agentId: "a8f2x9kq")  ← 记住了父 Agent 的 ID
```

```typescript
// src/tasks/LocalShellTask/guards.ts (line 28)
type LocalShellTaskState = {
  // ...
  agentId?: string  // 标记"谁生成了我"
}
```

当 Agent 被终止时，它生成的所有 Bash 任务也会被一起清理：

```typescript
// src/tasks/LocalShellTask/killShellTasks.ts (lines 59-72)
function killShellTasksForAgent(agentId: string) {
  // 找到所有 agentId 匹配的 Bash 任务
  // 逐个发送 SIGTERM
}
```

### 2. 父 Agent → 子 Agent（中断传播）

```
父 Agent (AbortController A)
  │
  │ createChildAbortController(A)
  │
  └──▶ 子 Agent (AbortController B, 链接到 A)
         │
         │ 当 A.abort() 时，B 也会自动 abort()
```

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx (lines 462-486)
function registerAsyncAgent({ parentAbortController, ... }) {
  const childAbortController = parentAbortController
    ? createChildAbortController(parentAbortController)  // 链接到父级
    : new AbortController()                              // 独立
}
```

> **比喻**：就像一个电话树。总经理挂断电话（abort），经理的电话也会自动断掉，经理下面的员工也一样。

### 3. 队友 → Leader（跨会话引用）

```typescript
// src/tasks/InProcessTeammateTask/types.ts (line 19)
type TeammateIdentity = {
  agentId: string
  agentName: string
  teamName: string
  parentSessionId: string  // 指向 Leader 的 Session ID
}
```

## 任务注册与更新

### 注册（创建）

```typescript
// src/utils/task/framework.ts (lines 77-116)
function registerTask(taskId, initialState, setAppState) {
  setAppState(prev => ({
    ...prev,
    tasks: {
      ...prev.tasks,
      [taskId]: initialState
    }
  }))
  // 发出 SDK 事件："新任务已创建"
  emit('system/task_started', { taskId, type: initialState.type })
}
```

### 更新（状态变化）

```typescript
// src/utils/task/framework.ts (lines 48-72)
function updateTaskState<T>(taskId, updater, setAppState) {
  setAppState(prev => {
    const task = prev.tasks[taskId]
    const updated = updater(task)
    if (updated === task) return prev  // 没变化就不更新（避免无效渲染）
    return {
      ...prev,
      tasks: { ...prev.tasks, [taskId]: updated }
    }
  })
}
```

## 输出收集：磁盘文件 + 增量读取

每个任务的输出写在磁盘上，而不是全放在内存里：

```
~/.anthropic/projects/{项目}/tmp/{sessionId}/tasks/
├── a8f2x9kq.output    ← Agent 任务的输出
├── b3m7p2nt.output    ← Bash 任务的输出
└── ...
```

使用增量读取避免重复读：

```typescript
// src/utils/task/framework.ts (lines 190-196)
function getTaskOutputDelta(taskId, currentOffset) {
  // 只读取 offset 之后的新内容
  const content = readFrom(outputFile, currentOffset)
  return {
    content,
    newOffset: currentOffset + content.length
  }
}
```

```
输出文件:  [AAAAAABBBBBBCCCCC]
             ↑              ↑
         上次读到这      这次从这里开始读
         offset=6        → 返回 "BBBBBCCCCC"
                         → newOffset=17
```

## 通知机制：防止重复

每个任务有一个 `notified` 标志，确保完成通知只发一次：

```typescript
// src/Task.ts (line 56)
type TaskStateBase = {
  // ...
  notified: boolean  // 是否已发送过完成通知
}
```

```
任务完成
    │
    ▼
notified === false?
    │
    ├── Yes → 发送通知 + 设置 notified = true
    │
    └── No  → 跳过（已经通知过了）
```

## 回收机制：两个守门人

任务不会永远留在内存中。回收需要满足两个条件：

```typescript
// src/utils/task/framework.ts (lines 125-144)
function evictTerminalTask(taskId) {
  // 条件 1: 必须是终结状态
  if (!isTerminalTaskStatus(task.status)) return

  // 条件 2: 必须已经通知过
  if (!task.notified) return

  // 条件 3: 如果有宽限期，必须过了宽限期
  if (task.evictAfter && Date.now() < task.evictAfter) return

  // 满足所有条件，从 AppState.tasks 中移除
  delete tasks[taskId]
}
```

### 宽限期

Agent 任务在终止后有 **30 秒**的宽限期，让 UI 有时间显示最终状态：

```typescript
// 30 秒宽限期
const PANEL_GRACE_MS = 30_000

// 任务完成或被杀时设置
task.evictAfter = Date.now() + PANEL_GRACE_MS
```

```
任务完成          30秒后
  │                │
  ▼                ▼
[UI 显示 "已完成"] [可以被回收了]
```

## 前台 vs 后台

一个 Agent 任务可以在前台和后台之间切换：

```
前台运行                    后台运行
──────                    ──────
用户可以看到输出             输出在后台累积
占用主界面                  用户可以干别的事
Ctrl+B → 切到后台          收到 <task-notification> 时
                          可以切回前台查看
```

```typescript
// src/tasks/LocalAgentTask/LocalAgentTask.tsx

// 前台 → 后台
function backgroundAgentTask(taskId) {
  updateTaskState(taskId, task => ({
    ...task,
    isBackgrounded: true  // false → true
  }))
  resolveBackgroundSignal()  // 通知 Agent Loop 不再占用 UI
}

// 后台 → 前台
function foregroundMainSessionTask(taskId) {
  // 恢复之前的前台任务到后台
  // 把新任务拉到前台
}
```

## InProcessTeammate：特殊的内存管理

团队 Agent 有一个精心设计的内存管理策略：

```typescript
// src/tasks/InProcessTeammateTask/types.ts (line 101)
const TEAMMATE_MESSAGES_UI_CAP = 50  // UI 只保留最近 50 条消息
```

为什么只保留 50 条？因为实测发现：**每个 Agent 在 500+ 轮后占用 ~20MB 内存**。一个有 292 个 Agent 的大型会话曾经占用了 **36.8GB** 内存。所以 UI 层只保留最近 50 条，完整对话存在磁盘上。

## 任务终止的多态分发

不同类型的任务有不同的终止方式：

```typescript
// src/Task.ts (lines 72-76)
interface Task {
  name: string
  type: TaskType
  kill(taskId: string, setAppState: SetAppState): Promise<void>
}
```

| 任务类型 | kill() 的实现 |
|----------|--------------|
| LocalShellTask | 发送 SIGTERM → SIGKILL 给进程 |
| LocalAgentTask | 调用 abortController.abort() |
| RemoteAgentTask | 标记超时 + 通知远端取消 |
| DreamTask | abort + 回滚整理锁的时间戳 |

```
用户点击 "停止任务"
    │
    ▼
getTaskByType(task.type)  // 找到对应的实现
    │
    ▼
taskImpl.kill(taskId)     // 调用对应的终止方法
```

## 关键常量

| 常量 | 值 | 含义 |
|------|------|------|
| `POLL_INTERVAL_MS` | 1000 | 输出轮询间隔 |
| `STOPPED_DISPLAY_MS` | 3000 | 终止任务显示时间 |
| `PANEL_GRACE_MS` | 30000 | 回收前的宽限期 |
| `STALL_THRESHOLD_MS` | 45000 | Bash 停滞检测阈值 |
| `TEAMMATE_MESSAGES_UI_CAP` | 50 | UI 消息上限 |

## 小结

任务图的设计遵循几个原则：

1. **扁平存储 + 引用关系**：不用嵌套结构，用字段引用表达父子关系
2. **统一状态机**：所有类型的任务都是 pending → running → terminal
3. **增量输出**：磁盘文件 + offset，避免大量数据在内存中堆积
4. **安全回收**：notified 标志 + 宽限期，防止丢通知或 UI 闪烁
5. **多态终止**：每种任务知道如何优雅地终止自己
6. **中断传播**：父级被终止时，子级自动跟随终止
