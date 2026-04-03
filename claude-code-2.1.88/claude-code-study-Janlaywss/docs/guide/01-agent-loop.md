# Agent Loop：从一句话到完成任务

## 一句话理解

想象你雇了一个非常能干的助手。你说"帮我整理一下房间"，这个助手不是听完就干完了——他会**反复循环**：先看看房间什么样，再决定先收拾哪里，收拾完一个地方再看看下一步该干什么，直到整个房间干净为止。

Claude Code 的 Agent Loop 就是这样一个**"观察 → 思考 → 行动 → 再观察"的循环**。

## 整体架构

```
用户输入 Prompt
      │
      ▼
┌─────────────────────────────┐
│     QueryEngine.submitMessage()   │  ← 每轮对话的入口
│                                   │
│  1. 解析用户输入                    │
│  2. 拼装 System Prompt             │
│  3. 进入 query() 主循环  ──────────┼──┐
└─────────────────────────────┘     │
                                     │
┌────────────────────────────────────┘
│
▼
┌─────────────────────────────────────────────┐
│              query() —— 无限循环              │
│                                              │
│  ┌──────────┐    ┌──────────┐    ┌────────┐ │
│  │  调用 API  │───▶│ 解析响应  │───▶│执行工具 │ │
│  │ (Claude)  │    │(流式处理) │    │(Bash等)│ │
│  └──────────┘    └──────────┘    └────────┘ │
│       ▲                              │       │
│       │          工具结果             │       │
│       └──────────────────────────────┘       │
│                                              │
│  直到：模型不再调用工具 / 达到上限 / 用户中断    │
└─────────────────────────────────────────────┘
```

## 核心文件导航

| 文件 | 职责 | 大小 |
|------|------|------|
| `src/entrypoints/cli.tsx` | CLI 入口，启动 REPL | 302 行 |
| `src/bootstrap/state.ts` | 会话状态初始化 | 1758 行 |
| `src/QueryEngine.ts` | 每轮对话的控制器 | 1295 行 |
| `src/query.ts` | 核心无限循环 | 1729 行 |

## 第一步：启动（cli.tsx）

当你在终端输入 `claude` 时，一切从这里开始：

```typescript
// src/entrypoints/cli.tsx
async function main() {
  // 快速路径：--version, --help 等不需要完整启动
  if (args.version) { /* 直接输出版本号，退出 */ }
  if (args.dumpSystemPrompt) { /* 输出 system prompt，退出 */ }

  // 完整启动：加载主模块
  const { cliMain } = await import('../main.js')
  await cliMain(/* ... */)
}
```

> **比喻**：这就像一个餐厅的前台。如果你只是问"几点关门"，前台直接告诉你；如果你要吃饭，前台才会把你领到座位上，启动完整的服务流程。

## 第二步：初始化会话状态（state.ts）

每次启动 Claude Code，都会创建一个**全新的会话状态**。这个状态就像一个"黑板"，整个运行过程中所有信息都写在上面：

```typescript
// src/bootstrap/state.ts (lines 44-256)
type State = {
  // 你在哪个目录工作
  originalCwd: string
  cwd: string
  projectRoot: string

  // 这次对话花了多少钱
  totalCostUSD: number

  // 每一轮用了多少工具
  turnToolCount: number

  // 会话唯一标识
  sessionId: SessionId

  // 上一次 API 请求的缓存（用于续传）
  lastAPIRequest: /* ... */ | null
  lastAPIRequestMessages: /* ... */ | null

  // 定时任务
  sessionCronTasks: SessionCronTask[]

  // ...更多字段
}
```

初始化函数会生成唯一的 session ID：

```typescript
// src/bootstrap/state.ts (line 330)
sessionId: randomUUID() as SessionId
```

## 第三步：QueryEngine —— 每轮对话的控制器

`QueryEngine` 是**一轮对话的总指挥**。它负责：接收用户输入 → 组装上下文 → 调用核心循环 → 返回结果。

```typescript
// src/QueryEngine.ts (lines 184-198)
export class QueryEngine {
  private mutableMessages: Message[]       // 所有历史消息
  private abortController: AbortController // 中断控制
  private permissionDenials: SDKPermissionDenial[] // 权限拒绝记录
  private totalUsage: NonNullableUsage     // 累计用量
}
```

关键方法是 `submitMessage()`，它是一个**异步生成器**（可以持续产出消息）：

```typescript
// src/QueryEngine.ts (lines 209+)
async *submitMessage(
  prompt: string | ContentBlockParam[],
  options?: { uuid?: string; isMeta?: boolean },
): AsyncGenerator<SDKMessage, void, unknown> {

  // 1. 解析用户输入，处理斜杠命令
  const { shouldQuery } = await processUserInput(prompt)

  // 2. 如果是本地命令（如 /help），直接返回
  if (!shouldQuery) { yield localResult; return }

  // 3. 进入核心循环
  for await (const message of query({
    messages,
    systemPrompt,
    canUseTool: wrappedCanUseTool,
    maxTurns,
    taskBudget,
    // ...
  })) {
    // 4. 处理循环产出的每条消息
    switch (message.type) {
      case 'assistant': yield message; break
      case 'progress': yield message; break
      case 'stream_event': updateUsage(message); break
      // ...
    }
  }
}
```

> **比喻**：`QueryEngine` 就像一个项目经理。客户（用户）提了需求，项目经理先判断是不是简单问题（斜杠命令），如果是就直接答复。如果是复杂需求，就启动完整的项目流程（`query()` 循环）。

## 第四步：query() —— 核心无限循环

这是整个 Agent 系统最核心的部分。它是一个 `while(true)` 无限循环：

```typescript
// src/query.ts (lines 218-238)
export async function* query(params: QueryParams) {
  // 循环状态
  let state = {
    messages: [],
    turnCount: 0,
    hasAttemptedReactiveCompact: false,
    maxOutputTokensRecoveryCount: 0,
    // ...
  }

  while (true) {
    // ====== 阶段 1：调用 Claude API ======
    for await (const message of callModel({
      messages: state.messages,
      systemPrompt,
      tools: availableTools,
      // ...
    })) {
      yield message  // 流式输出给用户
    }

    // ====== 阶段 2：错误恢复 ======
    // 如果 prompt 太长，尝试压缩后重试
    // 如果输出被截断，提高 max_tokens 重试

    // ====== 阶段 3：执行工具 ======
    for await (const update of runTools(toolUseBlocks)) {
      yield update.message
    }

    // ====== 阶段 4：决定是否继续 ======
    if (noMoreToolCalls) break  // 模型没有调用工具 → 任务完成
    if (turnCount >= maxTurns) break  // 达到轮次上限
    if (aborted) break  // 用户中断

    // 否则：把工具结果加入消息，继续下一轮
    state.messages.push(...toolResults)
    state.turnCount++
    continue  // 回到 while(true) 顶部
  }
}
```

用一张图来表示这个循环：

```
                    ┌───────────────────┐
                    │    while (true)    │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   调用 Claude API   │
                    │  （发送消息+工具列表）│
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │   流式接收响应      │
                    │  （文字 + 工具调用） │
                    └─────────┬─────────┘
                              │
                    ┌─────────▼─────────┐
                    │  有工具调用吗？      │
                    └────┬─────────┬────┘
                    No   │         │ Yes
                    ┌────▼───┐ ┌───▼──────────┐
                    │ 结束循环 │ │ 并行执行工具   │
                    │ 返回结果 │ │ (Bash/Read等) │
                    └────────┘ └───┬──────────┘
                                   │
                         ┌─────────▼─────────┐
                         │ 把工具结果加入消息   │
                         │ turnCount++         │
                         └─────────┬─────────┘
                                   │
                                   │ continue
                                   └──────────▶ 回到循环顶部
```

## 关键设计：流式处理 + 并行工具执行

Claude Code 不是等 API 完全响应后才执行工具。它使用了一个叫 `StreamingToolExecutor` 的组件，**边接收 API 响应边开始执行工具**：

```
时间线 ──────────────────────────────────────▶

API 响应流:  [文字..] [工具A的参数..] [工具B的参数..] [结束]
                          │                │
工具执行:              开始执行A          开始执行B
                          │                │
                       A完成             B完成
```

这样做的好处是：当模型还在输出工具 B 的参数时，工具 A 可能已经跑完了。**节省的时间 = 工具 A 的执行时间**。

## 关键设计：错误恢复

循环中有多种自动恢复机制：

### Prompt 太长 → 自动压缩

```typescript
// src/query.ts (lines 1119-1166)
// 如果 API 返回 "prompt too long" 错误
if (withheldError?.type === 'prompt_too_long') {
  // 尝试压缩上下文（详见第6章）
  await compactConversation(messages, context)
  // 压缩成功 → 用新消息重试
  state.messages = compactedMessages
  continue  // 回到循环顶部
}
```

### 输出被截断 → 提高限制重试

```typescript
// src/query.ts (lines 1188-1256)
// 如果输出超过了 max_output_tokens
if (withheldError?.type === 'max_output_tokens') {
  // 从 8K 升级到 64K
  state.maxOutputTokensOverride = 64_000
  // 注入恢复消息："你的输出被截断了，请继续"
  state.messages.push(recoveryMessage)
  state.maxOutputTokensRecoveryCount++
  continue  // 重试（最多 3 次）
}
```

> **比喻**：这就像考试时发现答题纸不够用了。第一次给你一张小纸，写不下就自动换一张大纸，最多换 3 次。

## 关键设计：两级生成器嵌套

整个消息流使用了**两层异步生成器**的设计：

```
外层：QueryEngine.submitMessage()
  │
  │  消费内层生成器的消息
  │  → 规范化格式
  │  → 记录到会话历史
  │  → 产出给外部（UI/SDK）
  │
  └── 内层：query()
        │
        │  产出原始消息
        │  → stream_event（token 用量）
        │  → assistant（模型回复）
        │  → user（工具结果）
        │  → attachment（附件信息）
```

这种设计的好处：**内层专注于"循环执行"，外层专注于"对外呈现"**，职责分离非常清晰。

## 一次完整执行的时序

让我们跟踪一个真实场景："帮我修复 bug.ts 文件中的类型错误"

```
时间 ──────────────────────────────────────────────────▶

用户: "帮我修复 bug.ts 中的类型错误"
  │
  ▼
QueryEngine.submitMessage()
  │
  ├─ 解析输入（不是斜杠命令）
  ├─ 拼装 System Prompt
  │
  ▼
query() 循环 - 第 1 轮
  │
  ├─ 调用 Claude API
  ├─ Claude 回复: "让我先看看这个文件" + 调用 Read("bug.ts")
  ├─ 执行 Read 工具 → 返回文件内容
  ├─ 把结果加入消息
  │
  ▼
query() 循环 - 第 2 轮
  │
  ├─ 调用 Claude API（带上文件内容）
  ├─ Claude 回复: "我发现了问题" + 调用 Edit("bug.ts", ...)
  ├─ 执行 Edit 工具 → 修改文件
  ├─ 把结果加入消息
  │
  ▼
query() 循环 - 第 3 轮
  │
  ├─ 调用 Claude API
  ├─ Claude 回复: "已修复，类型错误是因为..."（没有工具调用）
  ├─ 没有工具调用 → 跳出循环
  │
  ▼
返回最终结果给用户
```

## 小结

Agent Loop 的核心思想可以归结为三个字：**"循环调用"**。

1. **不是一次性完成**：模型可以反复调用工具，逐步推进任务
2. **流式处理**：边接收响应边执行工具，减少等待时间
3. **自动恢复**：遇到上下文超长、输出截断等问题，自动压缩或重试
4. **生成器架构**：两层嵌套的异步生成器，干净地分离了执行逻辑和对外接口

下一章我们来看：循环中执行的那些"工具"到底是怎么定义的？它们是怎么做到安全执行的？
