# 子 Agent 设计：分身术与团队协作

## 一句话理解

想象你是一个团队 leader。遇到一个大项目，你不会自己一个人干——你会派出几个队员分头去查资料、写代码、做测试。每个队员带着你给的指令出发，完成后向你汇报结果。

Claude Code 的子 Agent 就是这样的"分身"机制。主 Agent 可以**派出多个子 Agent**，它们各自独立工作，完成后把结果交回来。

## 整体架构

```
┌─────────────────────────────────────────────┐
│            主 Agent (Main Session)            │
│                                              │
│  用户: "调研这个项目的架构，然后写个新模块"       │
│                                              │
│  主 Agent 决定：拆成两步                       │
│                                              │
│  ┌──────────────┐  ┌───────────────────┐     │
│  │ 子Agent A     │  │ 子Agent B          │     │
│  │ (Explore)     │  │ (General Purpose)  │     │
│  │               │  │                    │     │
│  │ 只读工具:     │  │ 全部工具:           │     │
│  │ Read,Grep,   │  │ Read,Write,Edit,  │     │
│  │ Glob,Bash    │  │ Bash,Grep...      │     │
│  │               │  │                    │     │
│  │ 结果："项目用  │  │ 结果："已创建新     │     │
│  │  React+Node" │  │  模块 src/new/"    │     │
│  └──────┬───────┘  └────────┬──────────┘     │
│         │                    │                │
│         └──────┬─────────────┘                │
│                ▼                              │
│         汇总结果，回复用户                      │
└─────────────────────────────────────────────┘
```

## Agent 类型系统

Claude Code 内置了多种"专业角色"的 Agent：

| 类型 | 职责 | 可用工具 | 模型 |
|------|------|----------|------|
| **General Purpose** | 通用任务 | 全部工具 | 继承父级 |
| **Explore** | 快速搜代码 | Read, Grep, Glob, Bash(只读) | Haiku（更快更省） |
| **Plan** | 制定计划 | 只读工具 | 继承父级 |
| **Fork** | 分身（隐式） | 父级完全相同的工具 | 继承父级 |

### Agent 的定义结构

每个 Agent 类型都是一个定义对象：

```typescript
// src/tools/AgentTool/loadAgentsDir.ts (lines 106-165)
type AgentDefinition = {
  agentType: string          // "Explore", "Plan" 等
  whenToUse: string          // 什么时候该用这个 Agent
  tools?: string[]           // 允许使用的工具列表，['*'] 代表全部
  disallowedTools?: string[] // 明确禁止的工具
  model?: string             // 'haiku', 'sonnet', 'opus', 'inherit'
  maxTurns?: number          // 最大执行轮数
  permissionMode?: string    // 'bubble' = 权限弹窗转发给父级
  omitClaudeMd?: boolean     // 是否跳过加载 CLAUDE.md（省 token）
}
```

Explore Agent 的定义示例：

```typescript
// src/tools/AgentTool/built-in/exploreAgent.ts (lines 13-83)
{
  agentType: 'Explore',
  tools: ['Read', 'Glob', 'Grep', 'Bash'],   // 只给只读工具
  disallowedTools: ['Agent', 'Write', 'Edit'], // 禁止写和嵌套
  model: 'haiku',                              // 用最快的小模型
  omitClaudeMd: true,                         // 省掉项目说明（省 token）
}
```

> **比喻**：Explore Agent 就像一个"侦察兵"——只带望远镜（只读工具），跑得快（Haiku 模型），轻装上阵（不带 CLAUDE.md 背包）。

## 子 Agent 的生命周期

### 创建与执行

当主 Agent 决定派出子 Agent 时，调用 `AgentTool`：

```typescript
// 主 Agent 的视角：调用 AgentTool
Agent({
  description: "搜索数据库相关代码",
  prompt: "在项目中找到所有数据库相关的文件和函数",
  subagent_type: "Explore"  // 指定类型
})
```

内部执行流程：

```
AgentTool.call()
    │
    ├─ 解析 agent 定义
    ├─ 筛选可用工具
    ├─ 拼装 system prompt
    │
    ▼
┌──────────────────────────────┐
│ 同步执行？还是后台执行？        │
├──────────┬───────────────────┤
│ 同步     │ 后台              │
│          │                   │
│ runAgent() 直接执行           │
│ 阻塞等待结果  registerAsyncAgent()
│ 立即返回结果  │ 创建后台任务     │
│          │ 返回 task ID     │
│          │ 结果通过通知送达   │
└──────────┴───────────────────┘
```

### runAgent() 详解

```typescript
// src/tools/AgentTool/runAgent.ts (lines 248-329)
async function* runAgent({
  agentDefinition,    // Agent 类型定义
  promptMessages,     // 初始消息
  toolUseContext,     // 父级的上下文
  canUseTool,         // 权限检查函数
  isAsync,            // 是否后台执行
  availableTools,     // 预计算的工具池
  worktreePath?,      // Git worktree 隔离路径
}) {
  // 1. 生成唯一 Agent ID
  const agentId = generateAgentId()

  // 2. 准备上下文（克隆文件缓存、设置工作目录）
  const agentContext = createSubagentContext(parentContext, {
    agentId,
    agentType: agentDefinition.agentType,
    // 同步 Agent 共享父级的 AbortController
    // 异步 Agent 使用独立的 AbortController
    abortController: isAsync ? new AbortController() : parentAbortController,
  })

  // 3. 进入 query() 循环（和主 Agent 一样的循环！）
  for await (const message of query({
    messages: promptMessages,
    systemPrompt: agentSystemPrompt,
    tools: filteredTools,
    // ...
  })) {
    yield message  // 把每条消息传回给调用者
  }
}
```

> **关键发现**：子 Agent 内部跑的也是同一个 `query()` 循环！这是一个递归结构——Agent 调用 Agent Tool，Agent Tool 里面又跑一个完整的 Agent Loop。

## 同步 vs 异步 vs Fork

三种执行模式的对比：

```
同步执行                异步执行                Fork（分身）
────────               ────────               ────────
主Agent                主Agent                主Agent
  │                      │                      │
  ├─ 派出子Agent          ├─ 派出子Agent          ├─ fork 分身
  │  │                   │  │                    │  │  │
  │  │ 执行中...         │  ▼                    │  ▼  ▼
  │  │                   │ 继续干别的事           │ 分身1 分身2
  │  │                   │                       │  │    │
  │  ◄─ 结果返回         │                       │  │    │
  │                      │  ◄─ 收到通知           │  │    │
  ▼                      ▼                       ▼  ▼    ▼
继续后续工作            处理通知中的结果           汇总所有分身的结果
```

### Fork 分身机制

当你调用 `Agent()` 时不指定 `subagent_type`，系统会创建一个 **Fork（分身）**：

```typescript
// src/tools/AgentTool/forkSubagent.ts (lines 42-71)
const FORK_AGENT = {
  agentType: 'fork',
  tools: ['*'],           // 继承父级完全相同的工具
  permissionMode: 'bubble', // 权限弹窗转发给父级终端
  model: 'inherit',        // 使用和父级一样的模型
}
```

Fork 的最大特点是**共享上下文 + 缓存优化**：

```
父 Agent 的消息历史:
[系统提示] [用户消息1] [助手回复1] [工具结果1] ...
─────────────────────────────────────────────
           ↑ 这一段完全相同

Fork A:  [相同前缀...] [占位符...] [Fork A 的指令]
Fork B:  [相同前缀...] [占位符...] [Fork B 的指令]
Fork C:  [相同前缀...] [占位符...] [Fork C 的指令]
                                    ↑ 只有这里不同
```

因为前缀完全一样，API 的**提示词缓存**可以被所有 Fork 共享，大幅节省费用。

```typescript
// src/tools/AgentTool/forkSubagent.ts (lines 107-169)
function buildForkedMessages(directive, parentAssistantMessage) {
  // 为父消息中的每个工具调用创建占位结果
  const placeholders = parentMessage.content
    .filter(block => block.type === 'tool_use')
    .map(block => ({
      type: 'tool_result',
      tool_use_id: block.id,
      content: 'Fork started — processing in background'
    }))

  // 所有 Fork 使用相同的占位符（→ 缓存命中）
  // 只有最后的指令文本不同
  return [parentAssistantMessage, [...placeholders, directive]]
}
```

## Agent 间通信：SendMessage

子 Agent 之间可以通过 `SendMessage` 工具通信：

```typescript
// src/tools/SendMessageTool/SendMessageTool.ts (lines 67-87)
{
  to: string,       // 接收者："agent-名字", "*"（广播）
  summary: string,   // 5-10 字摘要
  message: string,   // 消息内容
}
```

消息路由方式：

```
SendMessage({ to: "researcher", message: "检查 auth 模块" })
    │
    ▼
┌─────────────────────────────────┐
│  to = "agent名字"                │──▶ 写入该 Agent 的邮箱文件
│  to = "*"                        │──▶ 广播给所有团队成员
│  to = "uds:路径"                 │──▶ Unix Socket 直接通信
└─────────────────────────────────┘
```

### 后台 Agent 的结果通知

后台 Agent 完成任务后，会生成一个 XML 格式的通知：

```xml
<task-notification>
  <task-id>a8f2x9kq</task-id>
  <status>completed</status>
  <summary>找到了 15 个数据库相关文件</summary>
  <result>数据库层使用 Prisma ORM...</result>
  <usage>
    <total_tokens>12345</total_tokens>
    <tool_uses>8</tool_uses>
    <duration_ms>5200</duration_ms>
  </usage>
</task-notification>
```

这个通知会被插入到主 Agent 的消息队列中，在下一轮循环时被处理。

## 工具过滤：每种 Agent 能用什么

不同类型的 Agent 有不同的工具访问权限：

```typescript
// src/tools/AgentTool/agentToolUtils.ts (lines 70-116)
function filterToolsForAgent({ tools, isAsync, permissionMode }) {
  // 所有 Agent 都不能用的工具
  const ALWAYS_BLOCKED = ['TaskStop', 'TeamCreate', 'TeamDelete']

  // 后台异步 Agent 只能用这些
  const ASYNC_ALLOWED = [
    'Bash', 'Read', 'Write', 'Glob', 'Grep',
    'FileEdit', 'Agent', 'SendMessage',
    'Skill', 'WebFetch', 'WebSearch',
  ]

  if (isAsync) {
    return tools.filter(t => ASYNC_ALLOWED.includes(t.name))
  }
  return tools.filter(t => !ALWAYS_BLOCKED.includes(t.name))
}
```

> **比喻**：就像一个公司的权限体系。实习生（Explore Agent）只能看文档；正式员工（General Purpose）能编辑文件；但谁都不能删除团队（TeamDelete）。

## Coordinator 模式：多 Agent 编排

当开启 Coordinator 模式时，主 Agent 变成了纯粹的"指挥官"：

```
┌──────────────────────────────────────────┐
│          Coordinator（指挥官）              │
│                                           │
│  不亲自执行任务，只负责：                    │
│  1. 分析用户需求                           │
│  2. 拆分成子任务                           │
│  3. 派出 Worker（工人）                    │
│  4. 汇总 Worker 的结果                     │
│                                           │
│  ┌─────┐  ┌─────┐  ┌─────┐              │
│  │Worker│  │Worker│  │Worker│              │
│  │  A   │  │  B   │  │  C   │              │
│  │      │  │      │  │      │              │
│  │搜代码 │  │改文件 │  │跑测试 │              │
│  └──┬──┘  └──┬──┘  └──┬──┘              │
│     │        │        │                   │
│     └────────┼────────┘                   │
│              ▼                            │
│         汇总+综合                          │
└──────────────────────────────────────────┘
```

## Agent Memory：子 Agent 的记忆

子 Agent 也有自己的持久化记忆系统：

```typescript
// src/tools/AgentTool/agentMemory.ts

// 三个记忆范围
User 级别:   ~/.claude/agent-memory/       // 跨项目通用
Project 级别: .claude/agent-memory/         // 项目共享（可提交到 Git）
Local 级别:   .claude/agent-memory-local/   // 本地私有
```

## 防止递归炸弹

子 Agent 可以再调用 Agent Tool 来创建孙 Agent。为了防止无限递归，系统有几道限制：

1. **Fork 子代不能再 Fork**：检测消息中是否有 Fork 标记
2. **异步 Agent 工具列表受限**：后台 Agent 的工具池更小
3. **maxTurns 限制**：每个 Agent 有最大轮数限制
4. **Token Budget 限制**：每个 Agent 有 token 预算

```typescript
// src/tools/AgentTool/forkSubagent.ts (lines 78-89)
function isInForkChild(messages) {
  // 检查消息中是否有 Fork 标记
  // 如果是 Fork 子代，禁止再次 Fork
  return messages.some(m => hasForkBoilerplateTag(m))
}
```

## 小结

子 Agent 设计的核心思想是**分治 + 隔离**：

1. **分治**：大任务拆成小任务，每个子 Agent 专注一件事
2. **类型化**：不同类型的 Agent 有不同的能力（工具集、模型、权限）
3. **隔离**：每个子 Agent 有独立的消息历史和 AbortController
4. **通信**：通过 SendMessage 和 task-notification 机制传递结果
5. **缓存共享**：Fork 机制通过共享消息前缀来最大化缓存命中
6. **递归保护**：多层限制防止无限嵌套
