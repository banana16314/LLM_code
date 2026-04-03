# Bash 工具详解

## 概述

`BashTool` 是执行 shell 命令的核心工具，提供安全的命令执行能力。它参考了 Claude Code 的 `BashTool` 实现，增加了多种安全特性。

**文件**: `claude_code_py/tools/bash_tool.py`

## 核心功能

| 功能 | 说明 |
|------|------|
| 命令执行 | 执行任意 bash 命令 |
| 超时控制 | 默认 120 秒，最大 600 秒 |
| 后台执行 | 支持 `run_in_background` 参数 |
| 工作目录跟踪 | 自动检测 `cd` 命令并更新会话工作目录 |
| 输出截断 | 最大 30,000 字符，超过则截断 |
| 危险命令检测 | 识别危险操作并强制确认 |

## 输入 Schema

```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "The command to execute"
    },
    "description": {
      "type": "string",
      "description": "Clear, concise description of what this command does"
    },
    "timeout": {
      "type": "number",
      "description": "Optional timeout in milliseconds (max 600000)"
    },
    "run_in_background": {
      "type": "boolean",
      "description": "Set to true to run in background"
    }
  },
  "required": ["command"]
}
```

## 实现核心逻辑

### 1. 命令包装与目录检测

```python
async def call(self, args: dict, context: ToolContext) -> ToolResult:
    command = args.get("command", "")
    
    # 使用唯一的 CWD 标记来检测工作目录变化
    cwd_marker = "__CCPY_CWD_MARKER__"
    
    # 包装命令：执行原命令 + 输出退出码 + pwd
    wrapped_command = f'''
        {command}
        __exit_code=$?
        echo ""
        echo "{cwd_marker}"
        pwd
        exit $__exit_code
    '''
    
    # 执行包装后的命令
    proc = await asyncio.create_subprocess_shell(
        wrapped_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=effective_cwd or None,
        env={**os.environ},
    )
    
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=timeout_s
    )
    
    # 解析输出，提取新的工作目录
    actual_output = stdout_text
    if cwd_marker in stdout_text:
        parts = stdout_text.rsplit(cwd_marker, 1)
        actual_output = parts[0].rstrip()
        new_cwd = parts[1].strip()
        
        # 更新会话级工作目录
        if new_cwd and os.path.isdir(new_cwd):
            if new_cwd != effective_cwd:
                _session_cwd = new_cwd
                log.info(f"Bash cwd changed: {effective_cwd} → {new_cwd}")
```

**关键点**：
- 通过包装命令捕获原命令的输出和退出码
- 同时执行 `pwd` 检测工作目录变化
- 更新会话级 `_session_cwd` 变量，使后续命令在同一目录执行

### 2. 后台执行

```python
if run_bg:
    # 后台模式：执行原始命令（不包装）
    proc_bg = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=effective_cwd or None,
        env={**os.environ},
    )
    
    # 终止包装进程
    try:
        proc.kill()
    except Exception:
        pass
    
    # 注册后台任务
    task_id = uuid.uuid4().hex[:8]
    
    async def _wait_bg(p):
        return await p.communicate()
    
    bg_future = asyncio.ensure_future(_wait_bg(proc_bg))
    _background_tasks[task_id] = {
        "proc": proc_bg,
        "future": bg_future,
        "command": command[:200],
        "pid": proc_bg.pid,
    }
    
    return ToolResult(
        output=f"Background task started (pid={proc_bg.pid}, id={task_id}).\n"
               f"Command: {command[:100]}"
    )
```

**关键点**：
- 后台模式下，终止包装进程，直接执行原始命令
- 使用 `asyncio.ensure_future` 创建任务
- 将任务注册到 `_background_tasks` 字典中供后续查询

### 3. 危险命令检测

```python
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+[/~]", r"rm\s+-rf\s+\.", r"git\s+push\s+--force",
    r"git\s+reset\s+--hard", r"git\s+clean\s+-f", r"git\s+checkout\s+--\s+\.",
    r"git\s+branch\s+-D", r"drop\s+table", r"drop\s+database",
    r">\s*/dev/sd", r"mkfs\.", r"dd\s+if=", r":(){ :\|:& };:",
    r"chmod\s+-R\s+777", r"curl.*\|\s*(bash|sh)",
]

def is_destructive(self, args: dict) -> bool:
    cmd = args.get("command", "")
    return any(re.search(pat, cmd) for pat in DANGEROUS_PATTERNS)
```

**检测的危险操作**：
- `rm -rf /` - 删除根目录
- `git push --force` - 强制推送（可能覆盖远程分支）
- `git reset --hard` - 硬重置（丢失未提交更改）
- `drop table/database` - 删除数据库
- `/dev/sd 重定向` - 磁盘写入
- `mkfs`, `dd` - 磁盘格式化
- `fork bomb` - 进程爆炸攻击
- `chmod -R 777` - 全权限设置
- `curl | bash` - 远程脚本执行

### 4. 睡眠检测

```python
BLOCKED_SLEEP_PATTERN = re.compile(r"sleep\s+(\d+)")

# 在 call 方法中
m = BLOCKED_SLEEP_PATTERN.search(command)
if m and int(m.group(1)) > 10:
    return ToolResult(
        error=f"Detected `sleep {m.group(1)}` — avoid unnecessary sleep. "
              "Use run_in_background or a different approach.",
        is_error=True,
    )
```

**设计考虑**：
- 检测到超过 10 秒的 `sleep` 时返回错误
- 建议使用 `run_in_background` 代替

## 输出处理

```python
def _combine_output(stdout: str, stderr: str) -> str:
    """Combine stdout/stderr, truncating if needed."""
    parts = []
    if stdout.strip():
        parts.append(stdout.strip())
    if stderr.strip():
        parts.append(stderr.strip())
    output = "\n".join(parts)
    
    # 截断超大输出
    if len(output) > MAX_OUTPUT_SIZE:
        half = MAX_OUTPUT_SIZE // 2
        output = (
            output[:half]
            + f"\n\n... (truncated {len(output) - MAX_OUTPUT_SIZE} chars) ...\n\n"
            + output[-half:]
        )
    return output
```

**特点**：
- 合并 stdout 和 stderr
- 最大 30,000 字符，超过则在中间截断并显示省略号

## 权限系统交互

```python
# query_loop.py 中的 _execute_with_permission
async def _execute_with_permission(
    self, tc: ToolCall, tool, args: dict, context: ToolContext
) -> ToolResult:
    perm = self.perms.check(tc.name, args)
    
    if perm == Permission.DENY:
        return ToolResult(error="Permission denied by policy", is_error=True)
    
    if perm == Permission.ASK:
        if self.ui:
            display = tool.render_tool_use(args)
            answer = await self.ui.ask_permission(tc.name, display)
            if answer == "persist":
                self.perms.grant_persistent(tc.name)
            elif answer == "always":
                if tc.name == "Bash":
                    self.perms.grant_bash_prefix(args.get("command", ""))
                else:
                    self.perms.grant_session_tool(tc.name)
            elif not answer:
                return ToolResult(error="User denied this action", is_error=True)
    
    try:
        return await tool.call(args, context)
    except Exception as e:
        log.exception(f"Tool {tool.name} failed")
        return ToolResult(error=str(e), is_error=True)
```

## 显示格式

```python
def render_tool_use(self, args: dict) -> str:
    cmd = args.get("command", "")
    desc = args.get("description", "")
    if desc:
        return f"{desc}\n  $ {cmd}"
    return f"$ {cmd}"
```

**输出示例**：
```
安装依赖
  $ pip install flask
```

## 与权限系统的配合

1. **默认权限**：`ASK`（首次调用时需要用户确认）
2. **危险命令**：即使是 `--yes` 模式也会强制 ASK
3. **持久化授权**：用户可选择 `!` 永久允许该工具
4. **命令前缀授权**：对于 Bash，可授权特定命令前缀（如 `pip`、`npm`）

## 使用建议

### ✅ 推荐用法

```python
# 带描述的简洁命令
await bash_tool.call({
    "command": "pip install flask",
    "description": "安装 Flask 依赖"
})

# 后台执行长时间任务
await bash_tool.call({
    "command": "python server.py",
    "run_in_background": True
})
```

### ❌ 避免的用法

```python
# 不必要的 sleep
await bash_tool.call({
    "command": "sleep 30"  # 会返回错误
})

# 危险操作（会被阻止或强制确认）
await bash_tool.call({
    "command": "rm -rf /"
})
```

## 相关工具

- `GrepTool` - 使用 ripgrep 进行搜索
- `GlobTool` - 使用 glob 模式匹配文件
- `ReadTool` - 读取文件内容
- `EditTool` - 编辑文件内容
- `WriteTool` - 写入文件内容

**注意**: 优先使用专用工具（Read/Edit/Write/Grep/Glob）而不是 Bash 命令（cat/sed/echo/grep/find）。

## 下一步

- `04_file_tools.md` - 文件读写编辑工具详解
- `05_permission_system.md` - 权限系统详解
