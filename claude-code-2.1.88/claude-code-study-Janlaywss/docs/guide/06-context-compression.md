# 上下文压缩：聊天记录太长了怎么办

## 一句话理解

Claude 的上下文窗口虽然很大（200K token），但如果你和它聊了 200 轮，读了 50 个文件，跑了 100 条命令——上下文就满了。这时候需要把旧的聊天记录"压缩"成摘要，给新内容腾出空间。

> **比喻**：想象你有一本 200 页的笔记本。你写到第 180 页时，把前 150 页的内容**归纳成 10 页摘要**贴在第 1 页，然后把那 150 页撕掉。这样你既保留了关键信息，又有了新的空间。

## 三级压缩策略

Claude Code 的压缩不是一刀切的，而是分**三个级别**，从轻到重：

```
对话增长 ──────────────────────────────────────────────▶

        轻量级                  中量级                  重量级
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Microcompact   │    │   Autocompact   │    │  Full Compact    │
│    (微压缩)       │    │   (自动压缩)     │    │   (全量压缩)      │
│                  │    │                  │    │                  │
│ 策略：清理旧的    │    │ 策略：用 AI 生成  │    │ 策略：用 AI 生成  │
│ 工具输出内容      │    │ 整个对话的摘要    │    │ 整个对话的摘要    │
│                  │    │                  │    │ + 恢复关键文件    │
│ 触发：每次调API前 │    │ 触发：token数超   │    │ 触发：prompt太长  │
│ 代价：几乎为零   │    │ 阈值（~167K）    │    │ 报错后自动触发    │
│ 效果：省几千token │    │ 代价：5-10秒     │    │ 代价：10+秒       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## 第一级：Microcompact（微压缩）

微压缩是**最轻量的清理手段**，每次 API 调用前自动执行。

### 原理

它不生成摘要，只是**删除旧的工具执行结果**。比如你之前读了 30 个文件，微压缩会清掉前 25 个的内容，只保留最近 5 个。

```
压缩前的消息历史：

[用户] 帮我看看这个项目
[助手] 好的，让我先看看 → Read("package.json")
[工具] {package.json 的内容...500行}          ← 会被清理
[助手] 接下来看看 → Read("src/index.ts")
[工具] {index.ts 的内容...300行}              ← 会被清理
[助手] 再看看 → Read("src/app.ts")
[工具] {app.ts 的内容...200行}                ← 会被清理
[助手] 还有 → Read("README.md")
[工具] {README.md 的内容...100行}             ← 保留（最近5个之一）
...
```

### 哪些工具的输出会被清理

```typescript
// src/services/compact/microCompact.ts (lines 41-50)
const COMPACTABLE_TOOLS = [
  'Read',        // 文件读取
  'Bash',        // Shell 命令输出
  'Grep',        // 搜索结果
  'Glob',        // 文件列表
  'WebSearch',   // 网页搜索结果
  'WebFetch',    // 网页内容
  'FileEdit',    // 编辑结果
  'FileWrite',   // 写入结果
]
```

### 时间触发模式

如果你离开了超过 **60 分钟**再回来，微压缩会更激进地清理：

```typescript
// src/services/compact/timeBasedMCConfig.ts (lines 30-34)
{
  enabled: true,
  gapThresholdMinutes: 60,  // 超过60分钟没操作
  keepRecent: 5,             // 只保留最近5个工具结果
}
```

> **比喻**：微压缩就像办公桌清理。你桌上堆了一摞打印出来的文件，微压缩只是把底下的旧文件收进柜子（删除内容），桌上保留最新的几张。

## 第二级：Autocompact（自动压缩）

当上下文接近容量上限时，Autocompact 会**调用 AI 生成一份对话摘要**来替代原始对话。

### 触发条件

```typescript
// src/services/compact/autoCompact.ts (lines 72-91)
const effectiveContextWindow = getContextWindowForModel(model) - 20_000  // 预留20K给输出
const autocompactThreshold = effectiveContextWindow - 13_000  // 再留13K缓冲

// 对于 200K 模型：
// effectiveContextWindow = 200K - 20K = 180K
// threshold = 180K - 13K = 167K
// 当 token 数 > 167K 时，触发自动压缩
```

```
上下文窗口（200K tokens）
┌──────────────────────────────────────────────────────┐
│▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░│
│        已使用的 token (167K)         │  缓冲区(13K)  │ 预留(20K)
│                                      ↑               │
│                                  触发阈值             │
└──────────────────────────────────────────────────────┘
```

### 压缩流程

```
触发自动压缩
    │
    ▼
┌──────────────────────────────┐
│ 1. 把整个对话发给 Claude      │
│    + 压缩指令：               │
│    "请为这段对话写一份摘要"    │
└──────────────┬───────────────┘
               │
    ┌──────────▼──────────┐
    │ 2. Claude 生成摘要    │
    │                      │
    │  摘要内容：            │
    │  - 主要请求和意图      │
    │  - 关键技术概念        │
    │  - 涉及的文件和代码    │
    │  - 遇到的错误和修复    │
    │  - 待办任务            │
    │  - 当前工作进展        │
    └──────────┬──────────┘
               │
    ┌──────────▼──────────┐
    │ 3. 用摘要替换原始对话  │
    │                      │
    │  [摘要]              │
    │  + 恢复最近读过的文件  │
    │  + 恢复使用中的技能    │
    │  + 恢复 hook 消息     │
    └──────────────────────┘
```

### 压缩后恢复的内容

压缩不只是留个摘要就完了。还要恢复一些关键上下文：

```typescript
// src/services/compact/compact.ts (lines 122-130)
const POST_COMPACT_MAX_FILES = 5        // 最多恢复 5 个文件
const PER_FILE_TOKEN_LIMIT = 5_000      // 每个文件最多 5K token
const TOTAL_FILE_BUDGET = 50_000        // 文件总预算 50K token
const PER_SKILL_TOKEN_LIMIT = 5_000     // 每个技能最多 5K token
const TOTAL_SKILL_BUDGET = 25_000       // 技能总预算 25K token
```

> **比喻**：这就像搬家。Autocompact 是把旧房子（原始对话）拆了，在新房子（摘要）里摆上你最常用的家具（最近读过的文件、正在用的技能）。

### 失败保护：断路器

如果连续 3 次压缩失败，系统会停止尝试：

```typescript
// src/services/compact/autoCompact.ts (lines 257-265)
if (consecutiveFailures >= 3) {
  // 停止重试，避免浪费 API 调用
  return
}
```

## 第三级：Reactive Compact（被动全量压缩）

当 API 返回"prompt too long"错误时触发。这时候必须压缩，否则无法继续。

```typescript
// src/query.ts (lines 1119-1166)
if (error.type === 'prompt_too_long') {
  // 必须压缩！
  await compactConversation(messages, context)
  state.messages = compactedMessages
  continue  // 用压缩后的消息重试
}
```

如果第一次压缩后还是太长，会**反复重试**，每次切掉更多旧消息：

```typescript
// src/services/compact/compact.ts (line 227)
const MAX_PTL_RETRIES = 3  // 最多重试3次

// 每次重试切掉最早的一组 API 交互
for (let i = 0; i < MAX_PTL_RETRIES; i++) {
  try {
    return await callClaude(truncatedMessages)
  } catch {
    truncatedMessages = removeOldestRound(truncatedMessages)
  }
}
```

## 压缩摘要的模板

Claude 生成摘要时遵循一个固定模板：

```typescript
// src/services/compact/prompt.ts (lines 61-143)
const COMPACT_PROMPT = `
请写一份详细的摘要，涵盖以下部分：

1. 主要请求和意图
2. 关键技术概念
3. 文件和代码片段（保留关键代码）
4. 遇到的错误和修复方案
5. 解决问题的过程
6. 所有用户消息（直接引用原文）
7. 待办任务
8. 当前工作进展
9. 可选的下一步建议
`
```

## Session Memory Compact（实验性）

这是一种更智能的压缩方式，利用**会话记忆**（Session Memory）作为摘要：

```
传统压缩：                      Session Memory 压缩：
[完整对话] → AI 生成摘要          [完整对话] → 已有的 Session Memory
                                              + 保留最近 N 条消息
```

```typescript
// src/services/compact/sessionMemoryCompact.ts (lines 47-130)
{
  minTokens: 10_000,   // 至少保留 10K token 的近期消息
  minTextBlockMessages: 5,  // 至少保留 5 条有文本的消息
  maxTokens: 40_000,   // 最多保留 40K token
}
```

好处是**不需要额外的 API 调用来生成摘要**（Session Memory 是在之前的对话中就持续更新的），所以速度更快。

## 整体流程图

```
每次 API 调用前
    │
    ├─▶ Microcompact（微压缩）
    │   清理旧工具输出
    │
    ▼
检查 token 数量
    │
    ├── < 167K ──▶ 正常调用 API
    │
    └── >= 167K ──▶ Autocompact（自动压缩）
                     │
                     ├─ 尝试 Session Memory Compact
                     │   （如果可用且足够）
                     │
                     └─ 否则 Full Compact
                         │
                         ├─ 成功 → 继续
                         │
                         └─ 失败3次 → 停止重试
                              │
                              ▼
                         API 调用
                              │
                         ┌────┴────┐
                         │ 成功     │ 失败："prompt too long"
                         │         │
                         ▼         ▼
                      正常继续    Reactive Compact
                                 （强制压缩 + 重试，最多3次）
```

## 什么内容不会被压缩

并非所有内容都会被压缩掉。以下内容会被保留或恢复：

| 内容 | 处理方式 |
|------|----------|
| 最近读过的文件 | 压缩后重新附上（最多5个） |
| 正在使用的技能 | 压缩后重新注入 |
| Hook 消息 | 压缩后重新执行 session-start hooks |
| Plan 文件 | 压缩后重新附上 |
| 工具/Agent 列表变化 | 压缩后重新注入 |
| 图片 | 压缩**前**移除（替换为文字标记） |

## 小结

上下文压缩的设计思路是**渐进式降级**：

1. **微压缩**：最轻量，每次都做，只清理工具输出，几乎无损
2. **自动压缩**：中等代价，AI 生成摘要，保留关键信息
3. **强制压缩**：最后手段，必须成功，否则无法继续

这就像城市的防洪体系：
- **微压缩** = 排水沟（日常疏导）
- **自动压缩** = 蓄水池（水位到警戒线时启动）
- **强制压缩** = 泄洪闸（洪水来了必须开闸放水）
