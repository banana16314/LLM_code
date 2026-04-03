# Tool 与沙箱：安全地让 AI 操作你的电脑

## 一句话理解

如果 Agent Loop 是"大脑"，那 Tool 就是"手脚"。Claude 通过调用 Tool 来读文件、写代码、执行命令。但你不会让一个新员工第一天就拿到服务器的 root 权限——所以需要**沙箱**来限制它能做什么。

## Tool 的定义：一个工具长什么样

Claude Code 里有 **49 个内置工具**，每个工具都遵循同一个接口：

```typescript
// src/Tool.ts (lines 362-695)
interface Tool<Input, Output> {
  // 基本信息
  name: string                    // 工具名，如 "Bash", "Read"
  inputSchema: ZodSchema<Input>   // 输入参数的校验规则

  // 安全属性
  isReadOnly(input): boolean      // 是否只读？默认 false（假设有写操作）
  isConcurrencySafe(input): boolean // 能并发执行吗？默认 false
  isDestructive?(input): boolean  // 是否不可逆？如删除文件

  // 权限检查
  checkPermissions(input, context): Promise<PermissionResult>

  // 真正的执行逻辑
  call(input, context): Promise<Output>
}
```

> **比喻**：每个 Tool 就像一个"工位上的工具"。剪刀（Bash）能剪东西也能伤人，所以标记为"非只读、不可并发"；放大镜（Read）只能看不能改，标记为"只读"。

### 默认值设计：安全第一

```typescript
// src/Tool.ts (lines 757-791)
const TOOL_DEFAULTS = {
  isConcurrencySafe: () => false,   // 默认不能并发（怕冲突）
  isReadOnly: () => false,           // 默认假设会写（最严格）
  isDestructive: () => false,
}
```

这是**失败安全（fail-safe）**设计：如果开发者忘了设置某个属性，系统会用最严格的默认值。就像电梯断电时默认停在最近楼层，而不是继续运行。

## Tool 的注册：怎么把工具交给 AI

所有工具通过一个中心注册表管理：

```typescript
// src/tools.ts (lines 193-251)
function getAllBaseTools(): Tool[] {
  return [
    BashTool,
    FileReadTool,
    FileEditTool,
    FileWriteTool,
    GlobTool,       // 文件模式匹配
    GrepTool,       // 内容搜索
    AgentTool,      // 创建子 Agent
    WebFetchTool,   // HTTP 请求
    WebSearchTool,  // 网络搜索
    LSPTool,        // 语言服务器
    // ...共 49 个
  ]
}
```

工具在到达模型之前，会经过**三层过滤**：

```
全部工具 (49个)
    │
    ▼ 第1层：Feature Flag 过滤
    │  （某些工具只在特定条件下可用）
    │
    ▼ 第2层：权限 Deny 规则过滤
    │  （settings.json 中禁用的工具直接移除）
    │
    ▼ 第3层：MCP 工具合并
    │  （外部 MCP 服务器提供的工具加入池中）
    │
    ▼
  最终工具池
  （这才是模型实际能"看到"的工具）
```

```typescript
// src/tools.ts (lines 262-269)
function filterToolsByDenyRules(tools, permissionContext) {
  return tools.filter(tool =>
    !getDenyRuleForTool(permissionContext, tool)
  )
}
```

## 权限模型：谁能用什么工具

Claude Code 有 6 种权限模式：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `default` | 危险操作需要确认 | 日常交互 |
| `acceptEdits` | 自动批准文件编辑 | 信任的编辑任务 |
| `bypassPermissions` | 跳过所有权限检查 | CI/CD 环境 |
| `plan` | 只读模式 | 规划阶段 |
| `auto` | AI 自动判断 | 自动化流水线 |
| `dontAsk` | 不提示，直接拒绝 | 后台子 Agent |

每次工具调用都会走一个**权限决策链**：

```
工具调用请求
    │
    ▼
┌────────────────────────┐
│ 1. 有没有 Deny 规则？    │──Yes──▶ 直接拒绝
└────────────┬───────────┘
             │ No
    ┌────────▼────────────┐
    │ 2. 有没有 Allow 规则？ │──Yes──▶ 直接放行
    └────────┬────────────┘
             │ No
    ┌────────▼────────────┐
    │ 3. 沙箱模式下？       │──Yes──▶ 自动放行
    └────────┬────────────┘          （沙箱会限制）
             │ No
    ┌────────▼────────────┐
    │ 4. 弹窗问用户        │
    └─────────────────────┘
```

## 沙箱机制：给 AI 画一个安全圈

沙箱是 Claude Code 安全策略的核心。它利用**操作系统级别**的安全机制来限制工具能做什么。

### 原理

```
┌─────────────────────────────────────────┐
│              Claude Code 进程             │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │           沙箱边界                 │   │
│  │                                   │   │
│  │  Bash 命令在这里面执行             │   │
│  │  ✅ 可以读写 ./项目目录            │   │
│  │  ✅ 可以读写 /tmp                 │   │
│  │  ❌ 不能读写 ~/.ssh               │   │
│  │  ❌ 不能读写 /etc                 │   │
│  │  ❌ 不能修改 .claude/settings     │   │
│  │  ❌ 不能访问大部分网络             │   │
│  │                                   │   │
│  └──────────────────────────────────┘   │
│                                          │
└─────────────────────────────────────────┘
```

### 平台实现

| 平台 | 技术 | 说明 |
|------|------|------|
| macOS | **Seatbelt** | Apple 内置的强制访问控制框架 |
| Linux | **Landlock** | 内核级文件系统沙箱（5.13+） |
| Linux (备选) | **Bubblewrap (bwrap)** | 容器化方案 |

### 沙箱配置转换

用户在 `settings.json` 中的权限规则会被转换为沙箱配置：

```typescript
// src/utils/sandbox/sandbox-adapter.ts (lines 172-381)
function convertToSandboxRuntimeConfig(settings) {
  return {
    network: {
      allowedDomains: [...],  // 允许访问的域名
      deniedDomains: [...],   // 禁止访问的域名
      allowUnixSockets: true, // Unix socket（LSP 等需要）
    },
    filesystem: {
      allowRead: ['.', '/tmp', ...],      // 可读路径
      allowWrite: ['.', '/tmp', ...],     // 可写路径
      denyRead: ['~/.ssh', ...],          // 禁读路径
      denyWrite: ['.claude/settings.json', // 禁写路径
                  '.claude/skills', ...],
    },
  }
}
```

## 反逃逸设计：三重防线

### 第一重：设置文件保护

沙箱**永远不允许写入自身的配置文件**：

```typescript
// src/utils/sandbox/sandbox-adapter.ts (lines 230-255)
// 永远禁止写入 settings.json（防止 AI 修改自己的权限）
denyWrite.push('.claude/settings.json')

// 永远禁止写入 skills 目录（防止 AI 注入恶意 Skill）
denyWrite.push('.claude/skills')
```

> **比喻**：这就像一个保险箱的钥匙不能放在保险箱里面。AI 不能修改自己的安全策略。

### 第二重：裸 Git 仓库防御

这是一个精巧的安全设计。攻击者可能通过在项目中放置特殊文件（`HEAD`、`objects/`、`refs/`），让 Git 误以为这是一个"裸仓库"，从而在沙箱外执行 Git 操作时访问到恶意内容。

```typescript
// src/utils/sandbox/sandbox-adapter.ts (lines 257-280)
// 检测是否有人植入了"裸 Git 仓库"文件
if (statSync('HEAD') && statSync('objects') && statSync('refs')) {
  // 发现可疑文件！禁止写入这些路径
  denyWrite.push('HEAD', 'objects', 'refs')
}

// 命令执行后，清理可能被植入的文件
function scrubBareGitRepoFiles() {
  // 删除在命令执行期间新创建的裸仓库文件
}
```

### 第三重：命令注入检测（AST 级别）

对于 Bash 命令，系统使用 **tree-sitter**（一个语法解析器）来分析命令结构，而不是简单地匹配字符串：

```typescript
// src/tools/BashTool/ (权限检查逻辑)
async function bashToolHasPermission(input, context) {
  // 1. 用 tree-sitter 解析命令为语法树
  const ast = parseWithTreeSitter(input.command)

  // 2. 检测危险模式
  if (hasCommandSubstitution(ast))  return { behavior: 'ask' }  // $(...)
  if (hasProcessSubstitution(ast))  return { behavior: 'ask' }  // <(...)
  if (hasEvalOrSource(ast))         return { behavior: 'ask' }  // eval, source
  if (hasPipeToShell(ast))          return { behavior: 'ask' }  // | bash

  // 3. 如果在沙箱内且配置允许，自动放行
  if (sandboxEnabled && autoAllowBashIfSandboxed) {
    return { behavior: 'allow' }
  }

  // 4. 否则需要用户确认
  return { behavior: 'ask' }
}
```

为什么要用 AST 而不是正则表达式？看这个例子：

```bash
# 看起来无害，但实际上会执行注入的命令
echo "hello $(rm -rf /)"

# 正则表达式很难可靠地检测所有变体
# 但 AST 解析器能准确识别 command_substitution 节点
```

## Bash Tool：最复杂的工具

Bash 是所有工具中最复杂的，因为它能执行**任意命令**。它的目录有 20 个文件：

```
src/tools/BashTool/
├── BashTool.ts           # 主工具定义
├── prompt.ts             # 给模型看的使用说明
├── bashPermissions.ts    # 权限决策（1800+ 行）
├── shouldUseSandbox.ts   # 沙箱开关判断
├── bashExec.ts           # 实际执行逻辑
├── bashState.ts          # Shell 状态管理
├── processCommand.ts     # 命令预处理
├── treeParser.ts         # tree-sitter AST 解析
└── ...
```

## 权限检查的完整流程

一个 Bash 命令从 AI 发起到实际执行，要经过 5 层检查：

```
AI 发出命令: "npm install express"
    │
    ▼
┌─────────────────────────────────────┐
│ 第1层：AST 注入检测                   │
│ tree-sitter 解析命令结构              │
│ 发现命令替换/eval? → 需要确认          │
└─────────────────┬───────────────────┘
                  │ 通过
    ┌─────────────▼───────────────────┐
    │ 第2层：沙箱自动放行                │
    │ 如果沙箱开启 + 配置允许自动放行     │
    │ → 自动允许（沙箱会兜底）            │
    └─────────────┬───────────────────┘
                  │ 不适用
    ┌─────────────▼───────────────────┐
    │ 第3层：精确规则匹配                │
    │ deny 规则 → 拒绝                  │
    │ allow 规则 → 允许                 │
    │ ask 规则 → 需要确认               │
    └─────────────┬───────────────────┘
                  │ 无匹配
    ┌─────────────▼───────────────────┐
    │ 第4层：AI 分类器                  │
    │ 用小模型(Haiku)判断命令安全性       │
    └─────────────┬───────────────────┘
                  │ 无法判断
    ┌─────────────▼───────────────────┐
    │ 第5层：弹窗问用户                  │
    │ "允许执行 npm install express?"   │
    └─────────────────────────────────┘
```

## 小结

Tool 和沙箱的设计体现了**纵深防御**的思想：

1. **Tool 层**：默认值全部选最严格的（fail-safe）
2. **权限层**：多级规则，deny 优先级最高
3. **沙箱层**：操作系统级别的强制限制
4. **AST 层**：语法级别的命令注入检测
5. **配置保护层**：AI 永远不能修改自己的安全规则

这就像一个银行的安保系统：有门禁（权限检查）、有保险箱（沙箱）、有监控（AST 分析），还有一条铁律——保安不能自己改密码（配置保护）。
