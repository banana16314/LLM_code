# 架构分析

## 启动流程

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLI 启动                                    │
│                     (claudepy 命令)                               │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: parse_args()                                           │
│ - 解析命令行参数 (--provider, --model, --yes, -p)               │
│ - 返回 argparse.Namespace                                       │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: apply config overrides                                 │
│ - 根据 --provider 应用默认配置                                   │
│ - 根据 --model, --api-key 覆盖                                   │
│ - 自动检测 API Key（如果未显式提供）                             │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: Initialize components                                  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ LLMClient(config)                                           │  │
│ │ - 创建 AsyncOpenAI 客户端                                     │  │
│ │ - 绑定 api_key, base_url, model                             │  │
│ └────────────────────────────────────────────────────────────┘  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ ToolRegistry() + register_all()                            │  │
│ │ - 注册 20 个工具                                              │  │
│ │   - Bash, Read, Edit, Write, Grep, Glob                   │  │
│ │   - Agent, Task*, AskUser, Web*, NotebookEdit             │  │
│ │   - Cron*, PlanMode*                                       │  │
│ └────────────────────────────────────────────────────────────┘  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ PermissionManager(auto_approve=args.yes, cwd=cwd)          │  │
│ │ - 加载 ~/.claude/settings.json 中的持久化规则                │  │
│ │ - 设置默认权限策略                                          │  │
│ └────────────────────────────────────────────────────────────┘  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │ Renderer(), Spinner(), InputHandler()                      │  │
│ │ - Rich 渲染器                                                │  │
│ │ - 加载动画                                                   │  │
│ │ - 输入处理（prompt_toolkit）                                │  │
│ └────────────────────────────────────────────────────────────┘  │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: AppState(cwd=cwd)                                      │
│ - 初始化空消息列表                                              │
│ - 生成 session_id                                               │
│ - 跟踪已读取文件                                                │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: build_system_prompt(cwd)                               │
│ - 组装系统 Prompt（10 个部分）                                    │
│   1. Core Identity                                               │
│   2. System Rules                                                │
│   3. Doing Tasks                                                 │
│   4. Actions with Care                                           │
│   5. Using Tools                                                 │
│   6. Tone and Style                                              │
│   7. Output Efficiency                                           │
│   8. Environment Info (cwd, git, platform)                      │
│   9. CLAUDE.md 内容                                               │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: QueryLoop(llm, tools, perms, ui)                       │
│ - 绑定所有核心组件                                               │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: CommandRegistry + register_builtins()                  │
│ - 注册斜杠命令 (/help, /model, /provider, 等)                   │
│ - 注入 app_context (state, renderer, config, llm, tools)        │
└───────────────────┬──────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────┐
│ main.py: run_query() 或 interactive_loop()                      │
│ - 单次模式：run_query(prompt)                                  │
│ - 交互模式：while True → get_input() → handle_query()          │
└──────────────────────────────────────────────────────────────────┘
```

## 核心数据流

```
┌──────────────────────────────────────────────────────────────────┐
│                    AppState (应用状态)                           │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ messages: [System, User, Assistant, ToolResult, ...]       │  │
│  │ tasks: { id: Task, ... }                                   │  │
│  │ session_id: "abc12345"                                     │  │
│  │ _read_files: { file_path: mtime, ... }                     │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            │ messages
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    QueryLoop (主循环)                            │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  for iteration in range(MAX_TOOL_ITERATIONS=40):           │  │
│  │                                                            │  │
│  │  1. auto_compact()                                         │  │
│  │     - 检查总 token 数                                         │  │
│  │     - > max_ctx - 13K 时触发压缩                            │  │
│  │                                                            │  │
│  │  2. llm.chat(messages, tools=...)                          │  │
│  │     - 流式调用 LLM                                           │  │
│  │     - 返回 StreamChunk iterator                             │  │
│  │                                                            │  │
│  │  3. 收集响应：text_parts + tool_calls                      │  │
│  │     - 文本输出 → yield 给用户                               │  │
│  │     - 工具调用 → 加入 assistant message                     │  │
│  │                                                            │  │
│  │  4. 分离工具调用：read_only_batch + serial_batch           │  │
│  │     - Read, Grep, Glob → 并行执行                          │  │
│  │     - Edit, Write, Bash → 串行执行                         │  │
│  │                                                            │  │
│  │  5. 执行工具：                                               │  │
│  │     - check_permission()                                   │  │
│  │       - 危险 Bash → 强制 ASK                                │  │
│  │       - auto_approve → ALLOW                               │  │
│  │       - persisted rules → ALLOW                            │  │
│  │       - session grants → ALLOW                             │  │
│  │     - await tool.call(args, context)                      │  │
│  │                                                            │  │
│  │  6. 添加 tool_result 到 messages                            │  │
│  │                                                            │  │
│  │  7. 循环直到没有工具调用或达到最大迭代次数                  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            │ 工具调用
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                    ToolRegistry (工具注册表)                     │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ BashTool     → BashTool.call()                            │  │
│  │ FileReadTool → FileReadTool.call()                        │  │
│  │ FileEditTool → FileEditTool.call()                        │  │
│  │ FileWriteTool → FileWriteTool.call()                      │  │
│  │ GrepTool     → GrepTool.call()                            │  │
│  │ GlobTool     → GlobTool.call()                            │  │
│  │ AgentTool    → AgentTool.call() → 递归调用 QueryLoop      │  │
│  │ ... (其他工具)                                               │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 模块依赖图

```
main.py
  │
  ├── config.py (Config 单例)
  ├── llm/client.py (LLMClient)
  │       │
  │       └── llm/messages.py (Message 类型定义)
  │
  ├── core/tool.py (ToolRegistry + BaseTool)
  │       │
  │       └── llm/messages.py
  │
  ├── core/permissions.py (PermissionManager)
  │       └── (写入 ~/.claude/settings.json)
  │
  ├── core/state.py (AppState)
  │       └── llm/messages.py
  │
  ├── core/context.py (build_system_prompt)
  │       └── utils/git.py
  │
  ├── tools/__init__.py (register_all)
  │       ├── bash_tool.py
  │       ├── file_read.py
  │       ├── file_edit.py
  │       ├── file_write.py
  │       ├── grep_tool.py
  │       ├── glob_tool.py
  │       ├── agent_tool.py
  │       ├── ask_user.py
  │       ├── web_search.py
  │       ├── web_fetch.py
  │       ├── notebook_edit.py
  │       ├── task_tools.py
  │       ├── cron_tools.py
  │       └── plan_tools.py
  │
  ├── core/query_loop.py (QueryLoop)
  │       ├── llm/client.py
  │       ├── core/tool.py
  │       ├── core/permissions.py
  │       ├── core/state.py
  │       ├── core/compact.py
  │       └── utils/tokens.py
  │
  ├── commands/registry.py
  │   └── commands/builtins.py
  │           └── (访问 app_context: state, renderer, config, llm, tools)
  │
  ├── ui/renderer.py
  │   └── rich (第三方库)
  │
  └── ui/input_handler.py
      └── prompt_toolkit (第三方库)
```

## 核心数据模型

### 1. Message 类型 (llm/messages.py)

```
Message (基类)
├── SystemMessage (role="system")
├── UserMessage (role="user")
├── AssistantMessage (role="assistant", tool_calls=[])
└── ToolResultMessage (role="tool", tool_call_id, name)

ToolCall
├── id
├── name
└── arguments (JSON 字符串)

ToolResult
├── output
├── error
└── is_error

StreamChunk
├── type: "text" | "tool_call_start" | "done"
├── text
├── tool_call
└── finish_reason
```

### 2. AppState (core/state.py)

```python
@dataclass
class AppState:
    cwd: str                    # 工作目录
    session_id: str             # 会话 ID
    messages: list[Message]     # 消息历史
    tasks: dict[str, Task]      # 任务管理
    plan_mode: bool             # 计划模式标志
    plan_file: str | None       # 计划文件路径
    _read_files: dict[str, float]  # 已读取文件追踪
```

### 3. ToolContext (core/tool.py)

```python
@dataclass
class ToolContext:
    cwd: str                    # 工作目录
    session_id: str             # 会话 ID
    permissions: PermissionManager  # 权限管理器
    agent_depth: int            # 代理深度（递归层数）
    max_agent_depth: int        # 最大代理深度（默认 3）
```

## 关键常量

| 常量 | 值 | 说明 |
|------|-----|------|
| `MAX_TOOL_ITERATIONS` | 40 | 最大工具调用迭代次数 |
| `MAX_CONCURRENCY` | 10 | 只读工具最大并发数 |
| `MAX_OTK_RECOVERY` | 3 | Token 超限恢复尝试次数 |
| `MAX_TOOL_RESULT_CHARS` | 50,000 | 工具结果最大字符数 |
| `RESULT_PREVIEW_CHARS` | 2,000 | 结果预览字符数 |
| `MAX_COMPACT_FAILURES` | 3 | 上下文压缩连续失败断路器 |
| `MAX_FILE_READ_LINES` | 2,000 | 默认文件读取行数 |
| `bash_timeout` | 120 | Bash 命令默认超时（秒） |

## 并发执行策略

```python
# query_loop.py
read_only_batch = []  # 只读工具：Read, Grep, Glob
serial_batch = []     # 写工具/未知工具：Edit, Write, Bash, Agent

# 1. 并行执行只读工具
if read_only_batch:
    tasks = [
        self._execute_with_permission(tc, tool, args, context)
        for tc, tool, args in read_only_batch
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

# 2. 串行执行写工具
for tc in serial_batch:
    result = await self._execute_with_permission(tc, tool, args, context)
```

## 权限决策流程

```
check(tool_name, args)
  │
  ├─ 1. 危险 Bash？ → ASK (不可绕过)
  │
  ├─ 2. auto_approve (--yes 标志)？ → ALLOW
  │
  ├─ 3. 持久化规则 (settings.json)？ → ALLOW
  │
  ├─ 4. 会话内授权？ → ALLOW
  │
  └─ 5. 默认规则 → 使用 DEFAULT_RULES 中的策略
```

## 上下文压缩策略

```python
# compact_messages()
threshold = max_tokens - 13_000  # 触发阈值

if total_tokens < threshold:
    return messages  # 无需压缩

to_summarize = messages[:-keep_recent]  # 需要总结的旧消息
recent = messages[-keep_recent:]        # 保留的最新消息

# 调用 LLM 生成摘要
summary = llm.chat(system="Summarize...", user=to_summarize_text)

return [system] + [summary_msg] + recent
```

## 系统 Prompt 结构

```
# System Prompt Sections

1. CORE_IDENTITY
   - AI 编码助手身份

2. SYSTEM_RULES
   - 输出规则、工具使用规则

3. DOING_TASKS
   - 任务执行原则（先读后改、避免过度工程）

4. ACTIONS_CARE
   - 谨慎执行操作（可逆操作 vs 破坏性操作）

5. USING_TOOLS
   - 工具使用指南（专用工具优先）

6. TONE_STYLE
   - 语气和风格（简洁、无 emoji）

7. OUTPUT_EFFICIENCY
   - 输出效率（直奔主题、避免填充词）

8. Environment Info (动态生成)
   - 工作目录、Git 状态、平台信息

9. CLAUDE.md (可选)
   - 项目级/用户级指令
```

## 下一步建议

1. **工具系统深入**：阅读 `02_tool_system.md` 了解工具基类和注册机制
2. **核心工具详解**：
   - `03_bash_tool.md` - Bash 命令执行工具
   - `04_file_tools.md` - 文件读写编辑工具
3. **权限系统详解**：`05_permission_system.md`
4. **其他模块**：
   - 斜杠命令系统
   - UI 渲染系统
   - Token 估算
