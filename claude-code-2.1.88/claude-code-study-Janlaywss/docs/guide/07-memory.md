# Memory 系统：让 AI 拥有跨会话的记忆

## 一句话理解

每次关闭 Claude Code，对话历史就没了。但如果你告诉它"我们项目用 pnpm 不用 npm"，你当然不想每次都重复一遍。Memory 系统就是解决这个问题的——它让 Claude Code 能**记住**跨会话的信息。

> **比喻**：如果每次对话是一节"课"，那 Memory 就是"课堂笔记本"。上一节课学到的东西写在笔记本里，下一节课翻开就能看到。

## 四层记忆架构

Claude Code 的记忆分为四层，从"个人专属"到"全公司共享"：

```
┌─────────────────────────────────────────────────────┐
│  第4层：Managed Memory（管理员策略）                    │
│  /etc/claude-code/CLAUDE.md                          │
│  全公司所有人都遵守的规则，由管理员维护                    │
│  例如："所有提交必须通过 CI"                             │
├─────────────────────────────────────────────────────┤
│  第3层：User Memory（用户个人）                         │
│  ~/.claude/CLAUDE.md                                 │
│  你个人的偏好，适用于所有项目                             │
│  例如："我喜欢用 TypeScript，不要 JavaScript"            │
├─────────────────────────────────────────────────────┤
│  第2层：Project Memory（项目级）                        │
│  项目根目录/CLAUDE.md  或  .claude/CLAUDE.md           │
│  项目团队共享的规则（可提交到 Git）                       │
│  例如："本项目使用 Prisma ORM"                          │
├─────────────────────────────────────────────────────┤
│  第1层：Local Memory（本地）                            │
│  .claude/CLAUDE.local.md                             │
│  你个人在这个项目里的笔记（gitignored）                   │
│  例如："我负责 auth 模块的重构"                          │
└─────────────────────────────────────────────────────┘
```

**优先级从低到高**：Managed → User → Project → Local

> 后加载的优先级更高。就像 CSS 一样，后面的规则会覆盖前面的。

## CLAUDE.md：最直接的记忆方式

`CLAUDE.md` 是一个特殊的 Markdown 文件，Claude Code 启动时会自动读取。

### 加载顺序

```typescript
// src/utils/claudemd.ts (lines 790-900)
function getMemoryFiles() {
  const files = []

  // 1. 管理员级别（最低优先级）
  files.push(readIf('/etc/claude-code/CLAUDE.md'))
  files.push(readIf('/etc/claude-code/.claude/rules/*.md'))

  // 2. 用户级别
  files.push(readIf('~/.claude/CLAUDE.md'))
  files.push(readIf('~/.claude/rules/*.md'))

  // 3. 项目级别（从根目录到当前目录逐层加载）
  for (dir of walkUp(cwd, projectRoot)) {
    files.push(readIf(dir + '/CLAUDE.md'))
    files.push(readIf(dir + '/.claude/CLAUDE.md'))
    files.push(readIf(dir + '/.claude/rules/*.md'))
  }

  // 4. 本地级别（最高优先级）
  for (dir of walkUp(cwd, projectRoot)) {
    files.push(readIf(dir + '/.claude/CLAUDE.local.md'))
  }

  return files
}
```

### @include 指令

CLAUDE.md 支持引用其他文件：

```markdown
<!-- CLAUDE.md -->
# 项目规范

基本规则见这里：
@./docs/coding-standards.md

API 定义在这里：
@./api/openapi.yaml
```

```typescript
// 支持的路径格式
@path                    // 相对路径
@./relative/path         // 相对路径
@~/home/path            // 用户主目录
@/absolute/path         // 绝对路径
```

系统会递归展开这些引用（有循环引用检测），就像 C 语言的 `#include`。

## Auto Memory：自动提取的记忆

除了手动维护 CLAUDE.md，Claude Code 还有一个**自动记忆系统**。它会在对话结束后，自动提取值得记住的信息。

### 存储结构

```
~/.claude/projects/<项目路径的哈希>/memory/
├── MEMORY.md              ← 索引文件（必须存在）
├── user_preferences.md    ← 用户偏好
├── feedback_testing.md    ← 反馈：测试相关
├── project_auth.md        ← 项目：认证模块
└── reference_linear.md    ← 参考：Linear 项目
```

### 记忆文件格式

每个记忆文件都有固定的前置元数据（frontmatter）：

```markdown
---
name: 测试策略偏好
description: 用户要求集成测试使用真实数据库
type: feedback
---

集成测试必须连接真实数据库，不要用 mock。

**Why:** 上季度 mock 测试全部通过，但生产环境的数据库迁移失败了。
**How to apply:** 在写测试代码时，使用项目的 test DB 配置，不要 mock 数据库层。
```

### 四种记忆类型

```typescript
// src/memdir/memoryTypes.ts (lines 14-19)
type MemoryType = 'user' | 'feedback' | 'project' | 'reference'
```

| 类型 | 用途 | 例子 |
|------|------|------|
| **user** | 用户角色、偏好、知识水平 | "我是后端开发，不太熟 React" |
| **feedback** | 用户纠正过的做法 | "不要在这里用 mock" |
| **project** | 正在进行的工作、截止日期 | "3月5日开始代码冻结" |
| **reference** | 外部系统的地址 | "bug 跟踪在 Linear INGEST 项目" |

### MEMORY.md 索引文件

MEMORY.md 是所有记忆的**入口**，每次对话开始时自动注入到上下文中：

```markdown
- [测试策略](feedback_testing.md) — 集成测试用真实数据库，不要mock
- [Auth重构](project_auth.md) — 认证模块重写中，法务合规驱动
- [Linear项目](reference_linear.md) — pipeline bug 在 Linear INGEST 项目追踪
```

有严格的大小限制：

```typescript
// src/memdir/memdir.ts (lines 35-38)
const MAX_LINES = 200        // 最多 200 行
const MAX_BYTES = 25_000     // 最多 25KB
```

超出限制时，多余的行会被截断，并附上警告信息。

## 记忆自动提取

对话结束后，一个**后台 Agent** 会分析对话内容，自动提取新的记忆：

```
对话结束
    │
    ▼
┌──────────────────────────────┐
│ 检查门控条件：                  │
│ ✓ 是主 Agent（不是子 Agent）   │
│ ✓ 功能开关开启                 │
│ ✓ Auto Memory 已启用           │
│ ✓ 不在远程模式                 │
└──────────────┬───────────────┘
               │ 全部通过
               ▼
┌──────────────────────────────┐
│ 启动 Fork Agent（后台执行）    │
│                               │
│ 给这个 Agent 的工具限制：       │
│ ✅ Read, Grep, Glob（随意用）  │
│ ✅ Edit, Write（仅限记忆目录） │
│ ❌ 其他写入工具                │
│ ❌ Bash rm 等危险命令          │
│                               │
│ 分析对话，提取新记忆            │
│ 最多 5 轮                      │
└──────────────────────────────┘
```

```typescript
// src/services/extractMemories/extractMemories.ts (lines 171-222)
function createAutoMemCanUseTool() {
  return (tool, input) => {
    // 读类工具：随意
    if (['Read', 'Grep', 'Glob'].includes(tool.name)) return 'allow'

    // 写类工具：只允许写入记忆目录
    if (['Edit', 'Write'].includes(tool.name)) {
      return isAutoMemPath(input.filePath) ? 'allow' : 'deny'
    }

    // Bash：只允许只读命令
    if (tool.name === 'Bash') {
      const readOnlyCommands = ['ls', 'find', 'grep', 'cat', 'stat', 'wc', 'head', 'tail']
      return isReadOnly(input.command, readOnlyCommands) ? 'allow' : 'deny'
    }

    return 'deny'
  }
}
```

### 防止重复提取

如果主 Agent 在对话中已经手动写了记忆（比如用户说"帮我记住这个"），后台提取会自动跳过：

```typescript
// src/services/extractMemories/extractMemories.ts (lines 121-148)
function hasMemoryWritesSince(messages, lastCursor) {
  // 检查是否有 Edit/Write 工具调用目标是记忆目录
  // 如果有：跳过自动提取（避免冲突）
}
```

## Session Memory：会话级记忆

除了持久化的 Auto Memory，还有一种**只在当前会话内使用**的记忆：

```
~/.claude/session/<session-id>/memory.md
```

它有 9 个固定区段：

```markdown
## Session Title
_本次会话在做什么_

## Current State
_现在进展到哪了_

## Task Specification
_用户的原始需求是什么_

## Files and Functions
_涉及了哪些文件和函数_

## Workflow
_采用的工作流是什么_

## Errors & Corrections
_遇到了什么错误，怎么修的_

## Codebase Documentation
_代码库的结构笔记_

## Learnings
_学到了什么_

## Key Results
_关键成果_
```

### 触发条件

```typescript
// src/services/SessionMemory/sessionMemory.ts (lines 134-181)
function shouldExtractMemory() {
  // 条件1: 距上次提取已经累积了足够的 token
  // 条件2: 工具调用次数达到阈值 OR 当前轮没有工具调用（自然对话断点）
}
```

Session Memory 的主要用途是为**上下文压缩**服务——当对话被压缩时，Session Memory 可以作为摘要的基础（见第6章）。

## Team Memory：团队共享记忆

当启用团队功能后，记忆可以在团队成员间共享：

```
~/.claude/projects/<项目>/memory/
├── MEMORY.md              ← 个人索引
├── personal_*.md          ← 个人记忆
└── team/                  ← 团队共享目录
    ├── MEMORY.md          ← 团队索引
    └── shared_*.md        ← 团队记忆
```

### 什么记忆该分享

| 类型 | 个人 or 团队 | 原则 |
|------|-------------|------|
| user | 永远个人 | 个人偏好不该强加给团队 |
| feedback | 默认个人 | 除非是项目级规范（如测试策略） |
| project | 倾向团队 | 项目信息大家都该知道 |
| reference | 通常团队 | 外部系统地址大家都需要 |

### 安全防护

团队记忆有**路径遍历防御**，防止恶意文件名逃出记忆目录：

```typescript
// src/memdir/teamMemPaths.ts (lines 265-284)
function validateTeamMemKey(key) {
  // 防御手段：
  // 1. 空字节截断检测
  // 2. URL 编码遍历检测 (%2e%2e%2f = ../)
  // 3. Unicode 归一化检测（全角 ．．／）
  // 4. 反斜杠路径检测（Windows）
  // 5. 符号链接逃逸检测（realpath() 校验）
  // 6. 符号链接循环检测（ELOOP）
}
```

## 记忆的注入时机

```
会话开始
    │
    ├─ 加载 CLAUDE.md 文件们 → 注入到 User Context
    │    (Managed → User → Project → Local)
    │
    ├─ 加载 MEMORY.md 索引 → 注入到 System Prompt
    │    (auto memory 区段)
    │
    └─ 加载 Session Memory → 用于上下文压缩
         (如果有上一次的会话记忆)

对话进行中
    │
    ├─ Session Memory 持续更新
    │    (每隔一定的 token 数和工具调用次数)
    │
    └─ 用户说"记住这个" → 立即写入 Auto Memory

对话结束后
    │
    └─ 后台 Agent 自动提取新记忆 → 写入 Auto Memory
```

## 记忆的验证原则

系统提示词中包含了一条重要规则：**记忆可能过时，使用前要验证**。

```
"记忆记录可能随时间变得陈旧。在使用记忆内容前，
请验证其是否仍然正确。如果记忆与当前观察冲突，
信任你现在看到的——并更新或删除过时的记忆。"
```

具体验证方式：

| 记忆内容 | 验证方法 |
|----------|----------|
| "某个文件在 src/auth/" | 检查文件是否存在 |
| "函数名叫 validateToken" | grep 搜索确认 |
| "项目用 Prisma" | 看 package.json |

## 小结

Memory 系统的设计围绕一个核心问题：**如何在"记住有用信息"和"不被错误信息误导"之间取得平衡**。

1. **四层 CLAUDE.md**：从管理员政策到个人笔记，层层递进
2. **Auto Memory**：自动提取 + 手动维护，持久化到磁盘
3. **Session Memory**：会话内持续更新的"工作笔记"
4. **Team Memory**：团队共享 + 路径安全防护
5. **验证优先**：记忆不是权威来源，使用前要验证

> **比喻**：Memory 系统就像一个经验丰富的员工的"工作习惯"。他记得"上次老板说用 pnpm"，但如果看到 package-lock.json（npm 的文件），他不会盲目坚持记忆，而是会确认一下现在的情况。
