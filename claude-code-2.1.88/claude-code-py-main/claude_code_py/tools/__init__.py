"""Tool registration — all tools."""

from .bash_tool import BashTool
from .file_read import FileReadTool
from .file_edit import FileEditTool
from .file_write import FileWriteTool
from .grep_tool import GrepTool
from .glob_tool import GlobTool
from .agent_tool import AgentTool
from .task_tools import TaskCreateTool, TaskGetTool, TaskUpdateTool, TaskListTool
from .ask_user import AskUserTool
from .web_search import WebSearchTool
from .web_fetch import WebFetchTool
from .notebook_edit import NotebookEditTool
from .cron_tools import CronCreateTool, CronDeleteTool, CronListTool
from .plan_tools import EnterPlanModeTool, ExitPlanModeTool


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
    TaskCreateTool,
    TaskGetTool,
    TaskUpdateTool,
    TaskListTool,
    # User interaction
    AskUserTool,
    # Web
    WebSearchTool,
    WebFetchTool,
    # Notebook
    NotebookEditTool,
    # Cron
    CronCreateTool,
    CronDeleteTool,
    CronListTool,
    # Plan mode
    EnterPlanModeTool,
    ExitPlanModeTool,
]


def register_all(registry):
    """Register all tools."""
    for tool_cls in ALL_TOOLS:
        registry.register(tool_cls())
