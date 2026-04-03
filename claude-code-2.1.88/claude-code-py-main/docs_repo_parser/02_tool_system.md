# 工具系统详解

## 工具架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                     BaseTool (基类)                              │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 属性：                                                       │  │
│  │  - name: str              # 工具名称                        │  │
│  │  - description: str       # 工具描述                        │  │
│  │  - input_schema: dict     # JSON Schema 定义                 │  │
│  │                                                            │  │
│  │ 方法：                                                       │  │
│  │  - call(args, context) → ToolResult                        │  │
│  │  - is_read_only(args) → bool                               │  │
│  │  - is_destructive(args) → bool                             │  │
│  │  - get_schema() → dict              # OpenAI function call  │  │
│  │  - render_tool_use(args) → str              # 显示工具调用  │  │
│  │  - render_result(result) → str              # 显示工具结果  │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
                            │
                            │ 继承
                            ▼
          ┌─────────────────┼─────────────────┐
          │                 │                 │
          ▼                 ▼                 ▼
    ┌──────────┐     ┌──────────┐     ┌──────────┐
    │ BashTool │     │ReadTool  │     │EditTool  │
    └──────────┘     └──────────┘     └──────────┘
          │                 │                 │
          └─────────────────┼─────────────────┘
                            │
                            ▼
          ┌────────────────────────────────────────┐
          │         ToolRegistry (注册表)           │
          │  - register(tool)                       │
          │  - get(name) → BaseTool                │
          │  - list_tools() → list[BaseTool]       │
          │  - get_schemas() → list[dict]          │
          └────────────────────────────────────────┘
```

## 工具基类 (BaseTool)

### 核心方法

```python
class BaseTool(ABC):
    """工具基类，所有工具都继承此类。"""
    
    name: str = ""                  # 工具名称（如 "Bash", "Read"）
    description: str = ""           # 工具描述（用于系统 Prompt）
    input_schema: dict = {}         # JSON Schema 定义输入参数
    
    @abstractmethod
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        """执行工具调用。必须子类实现。"""
        ...
    
    def is_read_only(self, args: dict) -> bool:
        """判断是否为只读工具（可用于并行执行）。"""
        return False
    
    def is_destructive(self, args: dict) -> bool:
        """判断是否为破坏性操作（需额外确认）。"""
        return False
    
    def get_schema(self) -> dict:
        """返回 OpenAI function-calling 格式的 tool schema。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }
    
    def render_tool_use(self, args: dict) -> str:
        """返回工具调用的简洁显示格式。"""
        ...
    
    def render_result(self, result: ToolResult) -> str:
        """返回工具结果的简洁显示格式。"""
        text = result.text
        if len(text) > 500:
            return text[:500] + "… (truncated)"
        return text
```

### ToolContext 上下文

```python
@dataclass
class ToolContext:
    """工具执行时的上下文信息。"""
    cwd: str                     # 工作目录
    session_id: str              # 会话 ID
    permissions: PermissionManager  # 权限管理器
    agent_depth: int = 0         # 当前代理深度（递归层数）
    max_agent_depth: int = 3     # 最大代理深度
```

## 工具列表（共 20 个）

### 核心工具 (6 个)

| 工具 | 文件 | 功能 | 只读 |
|------|------|------|------|
| Bash | `bash_tool.py` | 执行 shell 命令 | No |
| Read | `file_read.py` | 读取文件 | Yes |
| Edit | `file_edit.py` | 编辑文件（精确字符串替换） | No |
| Write | `file_write.py` | 写入文件 | No |
| Grep | `grep_tool.py` | 搜索文件内容 | Yes |
| Glob | `glob_tool.py` | 文件路径匹配 | Yes |

### 代理工具 (1 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| Agent | `agent_tool.py` | 启动子代理执行复杂任务 |

### 任务管理工具 (4 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| TaskCreate | `task_tools.py` | 创建任务 |
| TaskGet | `task_tools.py` | 获取任务详情 |
| TaskUpdate | `task_tools.py` | 更新任务状态 |
| TaskList | `task_tools.py` | 列出任务 |

### 用户交互工具 (1 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| AskUser | `ask_user.py` | 向用户提问 |

### Web 工具 (2 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| WebSearch | `web_search.py` | Web 搜索 |
| WebFetch | `web_fetch.py` | 网页抓取 |

### Notebook 工具 (1 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| NotebookEdit | `notebook_edit.py` | 编辑 Jupyter Notebook |

### Cron 工具 (3 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| CronCreate | `cron_tools.py` | 创建 Cron 任务 |
| CronDelete | `cron_tools.py` | 删除 Cron 任务 |
| CronList | `cron_tools.py` | 列出 Cron 任务 |

### 计划模式工具 (2 个)

| 工具 | 文件 | 功能 |
|------|------|------|
| EnterPlanMode | `plan_tools.py` | 进入计划模式 |
| ExitPlanMode | `plan_tools.py` | 退出计划模式 |

## 注册所有工具

```python
# tools/__init__.py

ALL_TOOLS = [
    # Core tools
    BashTool,
    FileReadTool,
    FileEditTool,
    FileWriteTool,
    GrepTool,
    GlobTool,
    # Agent
    AgentTool,
    # Task management
    TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool,
    # User interaction
    AskUserTool,
    # Web
    WebSearchTool, WebFetchTool,
    # Notebook
    NotebookEditTool,
    # Cron
    CronCreateTool, CronDeleteTool, CronListTool,
    # Plan mode
    EnterPlanModeTool, ExitPlanModeTool,
]

def register_all(registry):
    """注册所有工具到注册表。"""
    for tool_cls in ALL_TOOLS:
        registry.register(tool_cls())
```

## 工具执行流程

```
┌──────────────────────────────────────────────────────────────────┐
│  QueryLoop 收到 LLM 的工具调用请求                                │
└─────────────────────┬────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────┐
│  _execute_with_permission(tc, tool, args, context)              │
│                                                                  │
│  1. 权限检查：perms.check(tool_name, args)                      │
│     - 危险 Bash → ASK                                            │
│     - auto_approve → ALLOW                                       │
│     - persisted rules → ALLOW                                    │
│     - session grants → ALLOW                                     │
│     - 默认规则 → 使用 DEFAULT_RULES                                │
│                                                                  │
│  2. 如果 ASK → 显示请求并等待用户确认                           │
│     - y (yes) → 允许本次                                        │
│     - a (always) → 会话内允许                                   │
│     - ! (persist) → 持久化允许                                  │
│     - n (no) → 拒绝                                             │
│                                                                  │
│  3. await tool.call(args, context)                              │
│     - 调用工具的具体实现                                        │
│     - 返回 ToolResult                                           │
│                                                                  │
│  4. 将工具结果添加到消息历史                                    │
└─────────────────────┬────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────────┐
│  返回 ToolResult，包含 output 或 error                          │
└──────────────────────────────────────────────────────────────────┘
```

## 并发执行策略

```python
# query_loop.py

# 分离工具调用
read_only_batch = []  # 只读工具
serial_batch = []     # 写工具/未知工具

for tc in tool_calls:
    tool = self.tools.get(tc.name)
    if tool is None:
        serial_batch.append(tc)
        continue
    
    args = json.loads(tc.arguments) if tc.arguments else {}
    
    if tool.is_read_only(args):
        read_only_batch.append((tc, tool, args))
    else:
        serial_batch.append(tc)

# 1. 并行执行只读工具
if read_only_batch:
    tasks = [
        self._execute_with_permission(tc, tool, args, context)
        for tc, tool, args in read_only_batch
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

# 2. 串行执行写工具
for tc in serial_batch:
    tool = self.tools.get(tc.name)
    args = json.loads(tc.arguments) if tc.arguments else {}
    result = await self._execute_with_permission(tc, tool, args, context)
```

## 只读工具识别

```python
# BashTool
def is_read_only(self, args: dict) -> bool:
    return False  # Bash 不是只读的

# FileReadTool
def is_read_only(self, args: dict) -> bool:
    return True  # Read 是只读的

# FileEditTool
def is_read_only(self, args: dict) -> bool:
    return False  # Edit 不是只读的
```

## 工具输入 Schema 示例

```python
# BashTool 的输入 Schema
{
    "type": "object",
    "properties": {
        "command": {
            "type": "string",
            "description": "The command to execute",
        },
        "description": {
            "type": "string",
            "description": "Clear, concise description of what this command does",
        },
        "timeout": {
            "type": "number",
            "description": "Optional timeout in milliseconds (max 600000)",
        },
        "run_in_background": {
            "type": "boolean",
            "description": "Set to true to run in background",
        },
    },
    "required": ["command"],
}
```

## 工具结果显示格式

```python
# BaseTool 的默认实现
def render_result(self, result: ToolResult) -> str:
    """Human-readable summary of the tool result."""
    text = result.text
    if len(text) > 500:
        return text[:500] + "… (truncated)"
    return text
```

## 工具错误处理

```python
# 所有工具的 call 方法都应该返回 ToolResult
# 成功：ToolResult(output="结果内容")
# 失败：ToolResult(error="错误信息", is_error=True)

# 示例：FileReadTool 的错误处理
async def call(self, args: dict, context: ToolContext) -> ToolResult:
    file_path = args.get("file_path", "")
    
    if not file_path:
        return ToolResult(error="file_path is required", is_error=True)
    
    if not os.path.exists(file_path):
        return ToolResult(error=f"File not found: {file_path}", is_error=True)
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return ToolResult(output=content)
    except Exception as e:
        return ToolResult(error=str(e), is_error=True)
```

## 扩展新工具

### 步骤 1: 创建工具类

```python
# tools/my_tool.py

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

class MyTool(BaseTool):
    name = "MyTool"
    description = "This is my custom tool"
    input_schema = {
        "type": "object",
        "properties": {
            "param1": {
                "type": "string",
                "description": "First parameter",
            },
        },
        "required": ["param1"],
    }
    
    def is_read_only(self, args: dict) -> bool:
        return True  # 如果是只读工具
    
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        param1 = args.get("param1", "")
        
        if not param1:
            return ToolResult(error="param1 is required", is_error=True)
        
        # 执行工具逻辑
        result = f"Processed: {param1}"
        
        return ToolResult(output=result)
```

### 步骤 2: 注册工具

```python
# tools/__init__.py

from .my_tool import MyTool

ALL_TOOLS = [
    # ... 其他工具 ...
    MyTool,  # 添加新工具
]
```

## 下一步

- `03_bash_tool.md` - Bash 工具详细实现
- `04_file_tools.md` - 文件读写编辑工具详解
- `05_permission_system.md` - 权限系统详解
