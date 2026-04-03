# Skill 与 MCP：能力扩展体系

## 一句话理解

Claude Code 内置的工具（Read、Bash、Edit 等）是"出厂能力"。但现实世界的需求是无限的——你可能需要它操作数据库、调用 Jira、生成 PPT。**Skill** 和 **MCP** 就是两种"外挂能力"机制：Skill 是"可复用的提示词模板"，MCP 是"连接外部服务的标准协议"。

> **比喻**：如果 Tool 是手机出厂自带的相机、电话、短信，那 Skill 就是你安装的 App（本地运行），MCP 就是通过 API 连接的云服务（远程调用）。

## Skill 系统

### 什么是 Skill

一个 Skill 本质上是一个**带元数据的 Markdown 文件**。当用户或 AI 调用它时，Markdown 内容会被作为 Prompt 注入到对话中。

```
.claude/skills/
└── commit/
    └── SKILL.md      ← 这就是一个 Skill
```

一个 Skill 文件的结构：

```markdown
---
name: commit
description: 提交代码变更
allowedTools: ["Bash", "Read", "Grep"]
userInvocable: true
---

检查当前 git 状态，生成有意义的 commit message，然后提交。

步骤：
1. 运行 git status 查看变更
2. 运行 git diff 理解变更内容
3. 生成简洁的 commit message
4. 执行 git commit
```

### Skill 的来源（5 层）

```
优先级从低到高：

┌─────────────────────────────────────────┐
│ ① Bundled Skills（编译到 CLI 中的内置技能） │
│    如：/commit, /review-pr, /simplify     │
├─────────────────────────────────────────┤
│ ② Project Skills（项目级）                 │
│    .claude/skills/xxx/SKILL.md            │
├─────────────────────────────────────────┤
│ ③ User Skills（用户级）                    │
│    ~/.claude/skills/xxx/SKILL.md          │
├─────────────────────────────────────────┤
│ ④ Plugin Skills（插件提供）                │
│    由安装的插件注册                         │
├─────────────────────────────────────────┤
│ ⑤ MCP Skills（远程 MCP 服务器提供）        │
│    通过 MCP prompts/list 协议获取          │
└─────────────────────────────────────────┘
```

### Skill 定义的完整类型

```typescript
// src/skills/bundledSkills.ts (lines 15-41)
type BundledSkillDefinition = {
  name: string                  // 技能名，如 "commit"
  description: string           // 一行描述
  aliases?: string[]            // 别名
  whenToUse?: string            // 什么时候用（给 AI 看的触发条件）
  argumentHint?: string         // 参数提示，如 "<pr-number>"
  allowedTools?: string[]       // 允许使用的工具
  model?: string                // 模型覆盖
  disableModelInvocation?: bool // 禁止 AI 主动调用（只能用户手动）
  userInvocable?: boolean       // 用户是否可以通过 /xxx 调用
  hooks?: HooksSettings         // 钩子配置
  context?: 'inline' | 'fork'  // 执行方式：内联 or 子 Agent
  agent?: string                // 指定执行 Agent 类型
  files?: Record<string, string>// 附带的参考文件

  // 核心：生成 prompt 内容的函数
  getPromptForCommand: (args: string, context: ToolUseContext)
    => Promise<ContentBlockParam[]>
}
```

### Skill 文件发现流程

```typescript
// src/skills/loadSkillsDir.ts (lines 407-550)
function loadSkillsFromSkillsDir(basePath, source) {
  // 1. 扫描目录下的子目录（不是 .md 文件）
  for (const entry of readdir(basePath)) {
    // 2. 在子目录中寻找 SKILL.md
    const skillFile = path.join(basePath, entry, 'SKILL.md')

    // 3. 解析 frontmatter（YAML 头部）
    const { frontmatter, content } = parseFrontmatter(skillFile)

    // 4. 提取元数据字段
    const metadata = parseSkillFrontmatterFields(frontmatter, content)
    // → name, description, allowedTools, model, hooks, ...

    // 5. 创建 Command 对象
    return createSkillCommand({ metadata, content, basePath })
  }
}
```

### Skill 的两种执行方式

```
用户输入 /commit 或 AI 调用 Skill("commit")
    │
    ▼
┌─────────────────────────────────────┐
│ context === 'fork'?                  │
├──────────┬──────────────────────────┤
│ Yes      │ No (inline，默认)         │
│          │                           │
│ Fork 模式│ 内联模式                   │
│          │                           │
│ 启动子Agent  Prompt 内容直接注入      │
│ 独立执行  │ 到当前对话                 │
│ 独立 token│ 共享上下文                 │
│ 预算      │                           │
└──────────┴──────────────────────────┘
```

Fork 模式适合**独立的大任务**（如生成完整文档），内联模式适合**需要上下文的小任务**（如基于当前对话做 commit）。

### Skill 中的变量替换

Skill 的 Markdown 内容支持变量：

```typescript
// src/skills/loadSkillsDir.ts (lines 344-396)
function getPromptForCommand(args, context) {
  let content = skillMarkdown

  // 替换参数占位符
  content = substituteArguments(content, args)
  // ${ARGUMENTS} → 用户传入的参数

  // 替换技能目录路径
  content = content.replace('${CLAUDE_SKILL_DIR}', skillDir)

  // 替换会话 ID
  content = content.replace('${CLAUDE_SESSION_ID}', sessionId)

  // 执行内嵌 Shell 命令（仅非 MCP 技能）
  if (source !== 'mcp') {
    content = await executeShellCommandsInPrompt(content)
    // !`git status` → 实际执行并替换为输出
  }

  return content
}
```

> **安全设计**：来自 MCP 的技能**永远不会执行内嵌 Shell 命令**（`!`...``）。这防止了恶意 MCP 服务器通过技能注入命令。

### Skill 权限检查

```typescript
// src/tools/SkillTool/SkillTool.ts (lines 432-578)
function checkPermissions(input, context) {
  // 1. 检查 deny 规则（精确匹配 + 前缀匹配）
  //    "commit" → 精确匹配
  //    "review:*" → 匹配 review-pr, review-docs 等

  // 2. 检查 allow 规则

  // 3. 安全属性自动放行
  //    如果技能只有 description/name 没有 hooks/tools → 自动允许

  // 4. 都没匹配 → 弹窗问用户
}
```

## MCP 系统

### 什么是 MCP

MCP（Model Context Protocol）是一个**标准化的协议**，让 Claude Code 能连接外部服务器，获取工具、提示词和资源。

```
┌────────────┐    MCP 协议     ┌──────────────┐
│ Claude Code │◄──────────────▶│  MCP 服务器   │
│  (客户端)   │   JSON-RPC     │ (如 Postgres) │
└────────────┘                 └──────────────┘
```

### 支持的传输方式

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| `stdio` | 本地子进程，通过 stdin/stdout 通信 | 本地工具（如数据库客户端） |
| `sse` | Server-Sent Events + OAuth | 远程 SaaS 服务 |
| `http` | HTTP POST 请求 | RESTful API 服务 |
| `ws` | WebSocket 长连接 | 实时双向通信 |
| `sse-ide` | IDE 扩展的 SSE | VS Code/JetBrains 集成 |
| `sdk` | 进程内 SDK 调用 | 嵌入式服务器 |

### 服务器配置

MCP 服务器在 `.claude/.mcp.json` 中配置：

```json
{
  "mcpServers": {
    "postgres": {
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-postgres"],
      "env": { "DATABASE_URL": "postgresql://..." }
    },
    "slack": {
      "type": "sse",
      "url": "https://mcp.slack.com/sse",
      "oauth": { "clientId": "xxx" }
    }
  }
}
```

### 配置加载顺序

```
优先级从高到低：

1. Managed（企业策略）    /etc/claude-code/managed-mcp.json
2. Local（项目本地）      .claude/.mcp.json
3. User（用户全局）       ~/.claude/.mcp.json
4. Settings（全局设置）   settings.json 中的 mcpServers
5. Plugin（插件提供）     插件注册的服务器
6. Claude.ai（代理）      claude.ai 提供的代理服务器
```

### 连接状态机

每个 MCP 服务器有 5 种状态：

```typescript
// src/services/mcp/types.ts (lines 179-226)
type MCPServerConnection =
  | ConnectedMCPServer     // 已连接，正常工作
  | FailedMCPServer        // 连接失败
  | NeedsAuthMCPServer     // 需要认证（OAuth）
  | PendingMCPServer       // 连接中 / 重连中
  | DisabledMCPServer      // 已禁用
```

```
         connectToServer()
              │
              ▼
┌──────────────────────┐
│      Pending          │
│     (连接中)           │
└──────────┬───────────┘
      ┌────┴────┬────────────┐
      ▼         ▼            ▼
┌──────────┐ ┌──────────┐ ┌───────────┐
│Connected │ │  Failed   │ │NeedsAuth  │
│(已连接)   │ │ (失败)    │ │(需要认证)  │
└──────────┘ └──────────┘ └───────────┘
      │           │             │
      │     重连(最多5次)    OAuth 流程
      │     指数退避          │
      │     1s → 30s         │
      │           │           │
      └───────────┴───────────┘
```

### 连接核心逻辑

```typescript
// src/services/mcp/client.ts (lines 595-677)
// 连接函数使用 memoize，同名服务器只连接一次
const connectToServer = memoize(async (name, serverConfig) => {
  // 根据传输类型创建不同的 Transport
  switch (serverConfig.type) {
    case 'stdio':
      // 启动子进程，通过 stdin/stdout 通信
      transport = new StdioClientTransport({
        command: config.command,
        args: config.args,
        env: config.env,
      })
      break

    case 'sse':
      // 创建 OAuth 认证提供者
      const authProvider = new ClaudeAuthProvider(name, config)
      transport = new SSEClientTransport(url, {
        authProvider,
        requestInit: { headers },
      })
      break

    case 'http':
      transport = new StreamableHTTPClientTransport(url, { headers })
      break

    case 'ws':
      transport = new WebSocketTransport(url)
      break
  }

  // 创建 MCP Client 并连接
  const client = new Client({ name: 'claude-code', version })
  await client.connect(transport)

  return { client, name, type: 'connected', capabilities, cleanup }
})
```

### 工具获取与命名

```typescript
// src/services/mcp/client.ts (lines 1743-1800)
const fetchToolsForClient = memoizeWithLRU(async (server) => {
  // 1. 通过 MCP 协议请求工具列表
  const result = await server.client.listTools()

  // 2. 为每个工具生成标准化名称
  return result.tools.map(tool => ({
    // 格式: mcp__{服务器名}__{工具名}
    name: `mcp__${normalize(server.name)}__${tool.name}`,
    // 例如: mcp__postgres__query, mcp__slack__send_message

    inputSchema: tool.inputSchema,
    isMcp: true,

    // 调用时路由到 MCP 服务器
    call: (input) => callMCPTool({ server, tool: tool.name, args: input }),
  }))
})
```

> **设计思路**：`mcp__` 前缀让系统一眼就能区分内置工具和 MCP 工具。双下划线避免了与工具名中的单下划线冲突。

### 工具调用流程

```
AI 决定调用 mcp__postgres__query
    │
    ▼
┌──────────────────────────────┐
│ MCPTool.call()                │
│                               │
│ 1. 解析服务器名和工具名        │
│ 2. 找到对应的 ConnectedServer │
│ 3. 设置超时（30-60秒）        │
│ 4. 调用 client.callTool()    │
│ 5. 处理返回内容               │
│    - 文本 → 直接返回           │
│    - 图片 → 压缩+格式转换     │
│    - PDF/二进制 → 存磁盘      │
│ 6. 截断过长的响应              │
└──────────────────────────────┘
```

```typescript
// src/services/mcp/client.ts (lines 3029-3247)
async function callMCPTool({ client, tool, args, signal }) {
  // 每 30 秒记录一次进度日志
  const progressInterval = setInterval(() => {
    log(`MCP tool ${tool} still running...`)
  }, 30_000)

  // 带超时的调用
  const result = await Promise.race([
    client.callTool({ name: tool, arguments: args }, { signal }),
    timeoutPromise(getMcpToolTimeoutMs()),
  ])

  // 转换结果
  return transformMCPResult(result, supportedMimeTypes)
}
```

### MCP Prompt → Skill 桥接

MCP 服务器除了提供 Tool，还可以提供 Prompt（提示词模板）。这些 Prompt 会被自动转换为 Skill：

```typescript
// src/services/mcp/client.ts (lines 2033-2107)
const fetchCommandsForClient = memoizeWithLRU(async (server) => {
  const result = await server.client.listPrompts()

  return result.prompts.map(prompt => ({
    // 命名格式和 Tool 一样
    name: `mcp__${normalize(server.name)}__${prompt.name}`,
    type: 'prompt',
    source: 'mcp',
    loadedFrom: 'mcp',
    isMcp: true,

    // 调用时获取 prompt 内容
    getPromptForCommand: async (args) => {
      const result = await server.client.getPrompt({
        name: prompt.name,
        arguments: zipObject(argNames, args.split(' ')),
      })
      return transformResultContent(result.messages)
    },
  }))
})
```

### 认证系统

MCP 支持完整的 OAuth 认证流程：

```typescript
// src/services/mcp/auth.ts (lines 1376-1450)
class ClaudeAuthProvider implements OAuthClientProvider {
  // 支持的认证特性：
  // - 动态客户端注册（Dynamic Client Registration）
  // - URL 作为 client_id（CIMD 标准）
  // - Token 刷新
  // - 权限提升（scope step-up，处理 403）
  // - Keychain 持久化存储 token
}
```

### 连接管理 Hook

```typescript
// src/services/mcp/useManageMCPConnections.ts
function useManageMCPConnections() {
  // 自动重连（指数退避：1s → 2s → 4s → ... → 30s，最多 5 次）
  // 监听工具列表变化通知 → 刷新工具缓存
  // 监听 prompt 列表变化 → 刷新 Skill 缓存
  // 监听资源列表变化 → 刷新资源缓存

  return {
    toolsByServer,     // 每个服务器提供的工具
    commandsByServer,  // 每个服务器提供的 Skill
    resourcesByServer, // 每个服务器提供的资源
    clients,           // 所有连接
    reconnect,         // 手动重连
    setServerDisabled, // 启用/禁用
  }
}
```

## Skill + MCP 的协作全景

```
┌─────────────────────────────────────────────────────┐
│                   Claude Code                         │
│                                                       │
│  用户输入 /commit 或 AI 调用 Skill("commit")           │
│      │                                                │
│      ▼                                                │
│  ┌────────────────────────┐                           │
│  │     SkillTool          │                           │
│  │                        │                           │
│  │  findCommand("commit") │                           │
│  │      │                 │                           │
│  │      ├─ Bundled?  ✓ → 执行内置技能                  │
│  │      ├─ Project?  ✓ → 读取 .claude/skills/         │
│  │      ├─ User?     ✓ → 读取 ~/.claude/skills/       │
│  │      ├─ Plugin?   ✓ → 执行插件技能                  │
│  │      └─ MCP?      ✓ → 调用 MCP getPrompt()         │
│  └────────────────────────┘                           │
│                                                       │
│  AI 调用 mcp__postgres__query(...)                     │
│      │                                                │
│      ▼                                                │
│  ┌────────────────────────┐     ┌──────────────────┐ │
│  │     MCPTool            │────▶│  MCP Server       │ │
│  │                        │     │  (postgres)       │ │
│  │  route to server       │◀────│  tools/call       │ │
│  │  transform result      │     └──────────────────┘ │
│  └────────────────────────┘                           │
└─────────────────────────────────────────────────────┘
```

## 小结

Skill 和 MCP 构成了 Claude Code 的**扩展能力层**：

1. **Skill = 可复用的 Prompt 模板**：Markdown 文件 + frontmatter 元数据，支持变量替换和 Shell 内嵌
2. **MCP = 标准化的外部服务连接**：6 种传输方式，完整的 OAuth 认证，自动重连
3. **统一命名**：MCP 工具和 Skill 都用 `mcp__server__name` 格式，一眼识别来源
4. **安全边界**：MCP 来源的 Skill 不能执行 Shell 命令，MCP 工具受沙箱约束
5. **缓存优化**：工具列表和 Prompt 使用 LRU 缓存 + memoize，避免重复请求
6. **五层 Skill 来源**：从编译内置到远程 MCP，层层叠加，后者覆盖前者
