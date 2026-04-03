# 斜杠命令详解

## 概述

斜杠命令（Slash Commands）提供交互式控制，用户可以在对话过程中输入 `/command` 来执行特定操作。

**文件**: `claude_code_py/commands/builtins.py`

## 可用命令

| 命令 | 描述 |
|------|------|
| `/help` | 显示所有可用命令 |
| `/exit` 或 `/quit` | 退出程序 |
| `/clear` | 清空对话历史（保留系统 Prompt） |
| `/compact` | 压缩消息历史以节省 token |
| `/model [name]` | 显示/切换当前模型 |
| `/provider [name]` | 切换 LLM Provider |
| `/history` | 显示最近的消息历史 |
| `/config` | 显示当前配置 |
| `/cost` | 显示 Token 使用情况 |
| `/permissions` | 显示权限规则 |
| `/tools` | 列出所有可用工具 |

## 命令注册与调用

### 注册机制

```python
# commands/registry.py

class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, Callable] = {}
    
    def register(self, name: str, handler: Callable, description: str):
        self._commands[name] = {
            "handler": handler,
            "description": description,
        }
    
    def get(self, name: str):
        return self._commands.get(name)
    
    def list_commands(self):
        return [(name, info["description"]) for name, info in self._commands.items()]
```

### 内置命令注册

```python
# commands/builtins.py

def register_builtins(registry: CommandRegistry, app_context: dict):
    """注册所有内置命令。"""
    
    async def cmd_help(**kwargs):
        cmds = registry.list_commands()
        lines = ["[bold]Available commands:[/]"]
        for name, desc in cmds:
            lines.append(f"  [cyan]/{name:14s}[/] {desc}")
        lines.append("\n[dim]Escape+Enter for newline, Enter to send[/]")
        return "\n".join(lines)
    
    # 注册命令
    registry.register("help", cmd_help, "Show available commands")
    registry.register("exit", cmd_exit, "Exit the application")
    registry.register("quit", cmd_exit, "Exit the application")
    registry.register("clear", cmd_clear, "Clear conversation and screen")
    # ... 其他命令
```

## 命令处理流程

```
用户输入: /model qwen-max
  │
  ▼
main.py 的 interactive_loop()
  │
  ├─ if user_input.startswith("/"):
  │   │
  │   ├─ first_token = user_input.split()[0]  # "/model"
  │   ├─ cmd_name = first_token.lstrip("/")   # "model"
  │   ├─ if "/" not in cmd_name and cmd_name:  # 确认是命令而非路径
  │   │   │
  │   │   └─ await handle_command(user_input, cmd_registry, renderer)
  │   │       │
  │   │       ├─ parts = cmd_text.strip().split(None, 1)
  │   │       │   # parts = ["/model", "qwen-max"]
  │   │       ├─ cmd_name = parts[0].lstrip("/")
  │   │       │   # cmd_name = "model"
  │   │       ├─ cmd_args = parts[1] if len(parts) > 1 else ""
  │   │       │   # cmd_args = "qwen-max"
  │   │       │
  │   │       ├─ cmd_info = cmd_registry.get(cmd_name)
  │   │       │
  │   │       └─ result = await cmd_info["handler"](args=cmd_args)
  │   │           │
  │   │           └─ cmd_model(args="qwen-max")
  │   │               │
  │   │               └─ config.model = "qwen-max"
  │   │                   return "Model switched to: qwen-max"
  │   │
  │   └─ 显示结果
  │
  └─ 继续循环
```

## 各命令详解

### /help

```python
async def cmd_help(**kwargs):
    cmds = registry.list_commands()
    lines = ["[bold]Available commands:[/]"]
    for name, desc in cmds:
        lines.append(f"  [cyan]/{name:14s}[/] {desc}")
    lines.append("\n[dim]Escape+Enter for newline, Enter to send[/]")
    return "\n".join(lines)
```

**输出示例**：
```
Available commands:
  /help          Show available commands
  /exit          Exit the application
  /clear         Clear conversation and screen
  /compact       Compact message history to save context
  /model         Show/switch model (e.g. /model qwen-max)
  /provider      Switch LLM provider (e.g. /provider openai)
  /history       Show recent message history
  /config        Show current configuration
  /cost          Show estimated token usage
  /permissions   Show permission rules
  /tools         List available tools
```

### /exit 和 /quit

```python
async def cmd_exit(**kwargs):
    renderer = app_context.get("renderer")
    if renderer:
        renderer.info("Goodbye!")
    raise SystemExit(0)
```

### /clear

```python
async def cmd_clear(**kwargs):
    state = app_context.get("state")
    if state:
        state.clear_conversation()
        # 重新应用系统 Prompt
        from ..core.context import build_system_prompt
        system_prompt = build_system_prompt(state.cwd)
        state.set_system(system_prompt)
    
    renderer = app_context.get("renderer")
    if renderer:
        renderer.console.clear()
    
    return "Conversation Cleared."
```

### /compact

```python
async def cmd_compact(**kwargs):
    state = app_context.get("state")
    llm = app_context.get("llm_client")
    
    if state and llm:
        from ..core.compact import compact_messages
        before = len(state.messages)
        state.messages = await compact_messages(state.messages, llm, keep_recent=4)
        after = len(state.messages)
        return f"Compacted: {before} → {after} messages"
    
    return "Nothing to compact."
```

### /model

```python
async def cmd_model(**kwargs):
    """显示/切换模型。"""
    config = app_context.get("config")
    args_str = kwargs.get("args", "").strip()
    
    if args_str:
        config.model = args_str
        return f"Model switched to: {args_str}"
    
    return f"Current model: {config.model} (provider: {config.provider})"
```

**使用示例**：
```
> /model
Current model: qwen-plus-latest (provider: dashscope)

> /model gpt-4o
Model switched to: gpt-4o
```

### /provider

```python
async def cmd_provider(**kwargs):
    """切换 Provider。"""
    config = app_context.get("config")
    from ..config import PROVIDERS
    args_str = kwargs.get("args", "").strip()
    
    if args_str:
        if args_str.lower() not in PROVIDERS:
            return f"Unknown provider: {args_str}. Available: {', '.join(PROVIDERS.keys())}"
        
        # 重置配置，重新应用 provider 默认值
        config.base_url = ""
        config.model = ""
        config.api_key = ""
        config.apply_provider(args_str.lower())
        
        return f"Switched to {config.provider}: model={config.model}, base_url={config.base_url}"
    
    # 显示所有可用的 providers
    lines = [f"Current: {config.provider} (model: {config.model})", "", "Available providers:"]
    for name, info in PROVIDERS.items():
        marker = " ←" if name == config.provider else ""
        lines.append(f"  {name:12s} {info['default_model']:30s} {info['env_key']}{marker}")
    
    return "\n".join(lines)
```

**输出示例**：
```
Available providers:
  dashscope    qwen-plus-latest            DASHSCOPE_API_KEY ←
  openai       gpt-4o                      OPENAI_API_KEY
  anthropic    claude-sonnet-4-20250514    ANTHROPIC_API_KEY
  deepseek     deepseek-chat               DEEPSEEK_API_KEY
  openrouter   anthropic/claude-sonnet-4   OPENROUTER_API_KEY
```

### /history

```python
async def cmd_history(**kwargs):
    state = app_context.get("state")
    if not state:
        return "No state."
    
    lines = []
    for m in state.messages:
        role = m.role
        content = m.content if isinstance(m.content, str) else "(structured)"
        preview = content[:100].replace("\n", " ")
        lines.append(f"[{role:10s}] {preview}")
    
    return "\n".join(lines[-20:])  # 显示最近 20 条
```

### /config

```python
async def cmd_config(**kwargs):
    config = app_context.get("config")
    return (
        f"model:       {config.model}\n"
        f"base_url:    {config.base_url}\n"
        f"max_tokens:  {config.max_tokens}\n"
        f"temperature: {config.temperature}\n"
        f"stream:      {config.stream}\n"
        f"cwd:         {config.cwd}"
    )
```

### /cost

```python
async def cmd_cost(**kwargs):
    """显示 Token 使用情况。"""
    llm = app_context.get("llm_client")
    state = app_context.get("state")
    lines = []
    
    # 实际 API 使用
    if llm and hasattr(llm, "total_usage"):
        u = llm.total_usage
        lines.append(f"API usage (actual):  {u.prompt_tokens:,} in + {u.completion_tokens:,} out = {u.total_tokens:,} total")
    
    # 当前上下文估算
    if state:
        from ..utils.tokens import estimate_tokens
        est = sum(
            estimate_tokens(m.content if isinstance(m.content, str) else str(m.content))
            for m in state.messages
        )
        lines.append(f"Context estimate:    ~{est:,} tokens in {len(state.messages)} messages")
    
    return "\n".join(lines) if lines else "No usage data."
```

### /permissions

```python
async def cmd_permissions(**kwargs):
    """显示当前权限规则。"""
    from ..core.permissions import DEFAULT_RULES
    lines = ["Current permission rules:"]
    for tool, perm in sorted(DEFAULT_RULES.items(), key=lambda x: x[0]):
        lines.append(f"  {tool:20s} {perm.value}")
    return "\n".join(lines)
```

**输出示例**：
```
Current permission rules:
  Agent                allow
  Bash                 ask
  CronCreate           allow
  CronDelete           allow
  CronList             allow
  Edit                 ask
  EnterPlanMode        allow
  ExitPlanMode         allow
  Grep                 allow
  Glob                 allow
  NotebookEdit         ask
  Read                 allow
  TaskCreate           allow
  TaskGet              allow
  TaskList             allow
  TaskUpdate           allow
  WebFetch             allow
  WebSearch            allow
  Write                ask
```

### /tools

```python
async def cmd_tools(**kwargs):
    """列出可用工具。"""
    state = app_context.get("state")
    tools = app_context.get("tool_registry")
    
    if tools:
        lines = [f"Available tools ({len(tools.list_tools()):d}):"]
        for t in tools.list_tools():
            lines.append(f"  {t.name:20s} {t.description[:60]}")
        return "\n".join(lines)
    
    return "No tools loaded."
```

**输出示例**：
```
Available tools (20):
  Bash                 Executes a given bash command and returns its output...
  Read                 Reads a file from the local filesystem. You can access...
  Edit                 Performs exact string replacements in files...
  Write                Writes a file to the local filesystem. Overwrites exi...
  Grep                 A powerful search tool built on ripgrep...
  Glob                 Fast file pattern matching tool that works with a...
  Agent                Launch a sub-agent to handle a complex task autonom...
  TaskCreate           Create a new task to track progress.
  TaskGet              Get details of a task by ID.
  TaskUpdate           Update a task's status or details.
  TaskList             List all tasks.
  AskUser              Ask the user a question and wait for their response.
  WebSearch            Search the web for information.
  WebFetch             Fetch a URL and return its content.
  NotebookEdit         Edit Jupyter Notebook files.
  CronCreate           Create a new cron job.
  CronDelete           Delete a cron job.
  CronList             List all cron jobs.
  EnterPlanMode        Enter plan mode.
  ExitPlanMode         Exit plan mode.
```

## 命令与工具的关系

| 类别 | 命令 | 工具 |
|------|------|------|
| 系统控制 | /help, /exit, /clear | - |
| 上下文管理 | /compact | - |
| 模型管理 | /model | - |
| Provider 管理 | /provider | - |
| 信息查询 | /history, /config, /cost, /permissions, /tools | - |
| 工具调用 | - | Bash, Read, Edit, Write, Grep, Glob, Agent, ... |

**关键区别**：
- **命令**：由用户主动输入，控制程序行为和状态
- **工具**：由 LLM 决定调用，执行具体任务

## 命令输入规则

```python
# main.py 中的判断逻辑
if user_input.startswith("/"):
    first_token = user_input.split()[0]  # "/model" or "/home/user/..."
    cmd_name = first_token.lstrip("/")
    
    # 只有当 token 中不包含路径分隔符时才视为命令
    if "/" not in cmd_name and cmd_name:
        await handle_command(user_input, cmd_registry, renderer)
```

**示例**：
```
> /model qwen-max        # ✅ 是命令
> /help                  # ✅ 是命令
> /home/user/file.txt    # ❌ 不是命令（包含路径分隔符）
> /exit                  # ✅ 是命令
```

## 下一步

- `08_llm_client.md` - LLM 客户端详解
- `09_system_prompt.md` - 系统 Prompt 详解
- `10_utils.md` - 工具函数详解
