# 权限系统详解

## 概述

权限系统实现了多层次的权限控制，确保工具调用的安全性。它参考了 Claude Code 的权限管理设计，提供持久化授权、会话授权和危险操作拦截功能。

**文件**: `claude_code_py/core/permissions.py`

## 权限等级

```python
class Permission(Enum):
    ALLOW = "allow"    # 自动允许
    DENY = "deny"      # 拒绝
    ASK = "ask"        # 询问用户
```

## 权限决策流程

```
check(tool_name, args)
  │
  ├─ 1. 危险 Bash 检测？
  │   └─ 是 → ASK（不可绕过）
  │   └─ 否 → 继续
  │
  ├─ 2. auto_approve 模式（--yes 标志）？
  │   └─ 是 → ALLOW
  │   └─ 否 → 继续
  │
  ├─ 3. 持久化授权（settings.json）？
  │   └─ 是 → ALLOW
  │   └─ 否 → 继续
  │
  ├─ 4. 会话内授权？
  │   └─ 是 → ALLOW
  │   └─ 否 → 继续
  │
  └─ 5. 默认规则？
      └─ 返回 DEFAULT_RULES 中定义的策略
```

## 默认权限规则

```python
DEFAULT_RULES: dict[str, Permission] = {
    # 只读工具 — 始终允许
    "Read": Permission.ALLOW,
    "Glob": Permission.ALLOW,
    "Grep": Permission.ALLOW,
    "TaskList": Permission.ALLOW,
    "TaskGet": Permission.ALLOW,
    "TaskCreate": Permission.ALLOW,
    "TaskUpdate": Permission.ALLOW,
    "AskUserQuestion": Permission.ALLOW,
    "CronCreate": Permission.ALLOW,
    "CronDelete": Permission.ALLOW,
    "CronList": Permission.ALLOW,
    "EnterPlanMode": Permission.ALLOW,
    "ExitPlanMode": Permission.ALLOW,
    
    # 写工具 — 首次询问，之后记住
    "Bash": Permission.ASK,
    "Edit": Permission.ASK,
    "Write": Permission.ASK,
    "NotebookEdit": Permission.ASK,
    
    # 代理/Web — 允许
    "Agent": Permission.ALLOW,
    "WebSearch": Permission.ALLOW,
    "WebFetch": Permission.ALLOW,
}
```

**设计原则**：
- 只读工具（Read, Grep, Glob）始终允许，无需确认
- 写工具（Edit, Write, Bash）首次询问
- 代理和 Web 工具允许（用户可能期望这些能力）

## 危险命令检测

```python
DANGEROUS_PATTERNS_RE = [
    r"rm\s+-rf\s+[/~]", r"rm\s+-rf\s+\.", r"git\s+push\s+--force",
    r"git\s+reset\s+--hard", r"git\s+clean\s+-f", r"git\s+checkout\s+--\s+\.",
    r"git\s+branch\s+-D", r"drop\s+table", r"drop\s+database",
    r">\s*/dev/sd", r"mkfs\.", r"dd\s+if=", r":()\{\s*:\|:&\s*\};:",
    r"chmod\s+-R\s+777", r"curl.*\|\s*(bash|sh)",
]

def _is_dangerous_bash(cmd: str) -> bool:
    for pat in DANGEROUS_PATTERNS_RE:
        if re.search(pat, cmd):
            return True
    return False
```

**危险命令特点**：
- 删除操作（rm -rf）
- 破坏性 Git 操作（git push --force）
- 数据库删除（drop table）
- 磁盘操作（mkfs, dd）
- 安全漏洞（fork bomb）
- 权限滥用（chmod -R 777）
- 远程代码执行（curl | bash）

**关键特性**：
- 危险 Bash 命令**永远需要确认**，即使在使用 `--yes` 标志时
- 这是唯一的安全硬性边界，不可绕过

## 授权方式

### 1. 持久化授权

```python
def grant_persistent(self, tool_name: str):
    """写入 ~/.claude/settings.json，永久允许。"""
    self._persisted_allows.add(tool_name)
    self._save_persisted_rules()
```

**存储格式** (`~/.claude/settings.json`):
```json
{
  "permissions": {
    "allow": ["Bash", "Edit", "Write"]
  }
}
```

**触发方式**：用户输入 `!` 或 `persist`

### 2. 会话内授权

```python
def grant_session_tool(self, tool_name: str):
    """当前会话允许该工具。"""
    self._session_tool_allows.add(tool_name)

def grant_bash_prefix(self, command: str):
    """允许特定 Bash 命令前缀（如 pip, npm）。"""
    prefix = command.strip().split()[0] if command.strip() else ""
    if prefix:
        self._bash_prefix_allows.add(prefix)
```

**触发方式**：用户输入 `a` 或 `always`

### 3. 单次授权

```
允许本次 — 用户输入 y 或 yes
```

## UI 交互流程

```python
async def ask_permission(self, tool_name: str, display: str) -> bool | str:
    """向用户请求权限。"""
    icon = TOOL_ICONS.get(tool_name, "⚠")
    self.console.print(f"\n  [warning]{icon} {tool_name}[/]")
    self.console.print(f"  [tool.args]{display}[/]")
    
    try:
        answer = input("  Allow? Yes(y) / Always this session(a) / Always forever(!) / No(n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    
    if answer in ("!", "p", "persist", "always-persist", "forever"):
        return "persist"  # 持久化授权
    
    if answer in ("a", "always"):
        return "always"  # 会话授权
    
    return answer in ("y", "yes")  # 单次授权
```

**交互示例**：
```
  ⚠ Bash
  $ npm install
  Allow? Yes(y) / Always this session(a) / Always forever(!) / No(n): a
```

## 权限管理器的内部状态

```python
class PermissionManager:
    def __init__(self, auto_approve: bool = False, cwd: str = ""):
        self._rules: dict[str, Permission] = dict(DEFAULT_RULES)
        self._session_tool_allows: set[str] = set()
        self._bash_prefix_allows: set[str] = set()
        self.auto_approve = auto_approve
        self.cwd = cwd
        self._persisted_allows: set[str] = set()
        self._load_persisted_rules()  # 从 settings.json 加载
```

| 属性 | 类型 | 说明 |
|------|------|------|
| `_rules` | `dict[str, Permission]` | 工具默认权限规则 |
| `_session_tool_allows` | `set[str]` | 会话内授权的工具集合 |
| `_bash_prefix_allows` | `set[str]` | 会话内授权的 Bash 命令前缀 |
| `_persisted_allows` | `set[str]` | 持久化授权的工具集合 |
| `auto_approve` | `bool` | `--yes` 标志启用的自动批准模式 |

## 权限检查实现

```python
def check(self, tool_name: str, args: dict) -> Permission:
    # 1. 危险 Bash → 强制 ASK（不可绕过）
    if tool_name == "Bash":
        cmd = args.get("command", "")
        if _is_dangerous_bash(cmd):
            return Permission.ASK
    
    # 2. 自动批准模式（--yes 标志）
    if self.auto_approve:
        return Permission.ALLOW
    
    # 3. 持久化授权
    if tool_name in self._persisted_allows:
        if tool_name == "Bash":
            # 检查命令前缀授权
            cmd = args.get("command", "").strip()
            prefix = cmd.split()[0] if cmd else ""
            if f"Bash:{prefix}" in self._persisted_allows or "Bash" in self._persisted_allows:
                return Permission.ALLOW
        else:
            return Permission.ALLOW
    
    # 4. 会话授权
    if tool_name in self._session_tool_allows:
        return Permission.ALLOW
    
    if tool_name == "Bash":
        cmd = args.get("command", "").strip()
        prefix = cmd.split()[0] if cmd else ""
        if prefix and prefix in self._bash_prefix_allows:
            return Permission.ALLOW
    
    # 5. 默认规则
    return self._rules.get(tool_name, Permission.ASK)
```

## 配置文件位置

```
~/.claude/settings.json
```

**示例内容**：
```json
{
  "permissions": {
    "allow": ["Bash", "Edit", "Write"]
  }
}
```

**加载逻辑**：
```python
def _load_persisted_rules(self):
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
        rules = data.get("permissions", {}).get("allow", [])
        for rule in rules:
            if isinstance(rule, str):
                self._persisted_allows.add(rule)
            elif isinstance(rule, dict):
                self._persisted_allows.add(rule.get("tool", ""))

def _save_persisted_rules(self):
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    data = {}
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
    
    if "permissions" not in data:
        data["permissions"] = {}
    
    data["permissions"]["allow"] = sorted(self._persisted_allows)
    
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
```

## 权限检查调用链

```
QueryLoop._execute_with_permission()
  │
  ├─ PermissionManager.check(tool_name, args)
  │   │
  │   ├─ 危险 Bash → ASK
  │   ├─ auto_approve → ALLOW
  │   ├─ persisted → ALLOW
  │   ├─ session → ALLOW
  │   └─ default → 返回规则
  │
  ├─ if ASK → ask_permission()
  │   │
  │   ├─ user 输入 "!" → grant_persistent()
  │   ├─ user 输入 "a" → grant_session_tool() / grant_bash_prefix()
  │   ├─ user 输入 "y" → 继续
  │   └─ user 输入 "n" → 返回 DENY
  │
  └─ await tool.call(args, context)
```

## 安全设计要点

1. **分层防御**
   - 第一层：危险命令检测（不可绕过）
   - 第二层：自动批准模式（--yes）
   - 第三层：持久化授权（用户主动设置）
   - 第四层：会话授权（本次会话）
   - 第五层：默认规则

2. **危险命令永久拦截**
   - 即使使用 `--yes` 标志，危险命令仍会询问
   - 这是唯一的安全硬性边界

3. **会话隔离**
   - 会话授权只在当前会话有效
   - 重启后需要重新授权

4. **持久化授权可控**
   - 用户主动选择 `!` 才能持久化
   - 授权内容保存在 `~/.claude/settings.json`

5. **命令前缀细粒度授权**
   - Bash 可授权特定命令（如 `pip`）
   - 而非全部 Bash 命令

## 下一步

- `06_query_loop.md` - 查询循环详解
- `07_system_prompt.md` - 系统 Prompt 详解
