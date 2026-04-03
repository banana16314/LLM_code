"""BaseTool and ToolRegistry."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from ..llm.messages import ToolResult

log = logging.getLogger(__name__)


@dataclass
class ToolContext:
    cwd: str = ""
    session_id: str = ""
    permissions: Any = None  # PermissionManager (forward ref)
    agent_depth: int = 0     # recursion depth for sub-agents
    max_agent_depth: int = 3 # max recursion depth


class BaseTool(ABC):
    name: str = ""
    description: str = ""
    input_schema: dict = {}  # JSON Schema — always override in subclasses

    @abstractmethod
    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        ...

    def is_read_only(self, args: dict) -> bool:
        return False

    def is_destructive(self, args: dict) -> bool:
        return False

    def get_schema(self) -> dict:
        """Return OpenAI function-calling tool schema."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.input_schema,
            },
        }

    def render_tool_use(self, args: dict) -> str:
        """Human-readable summary of the tool call (for terminal display)."""
        return f"{self.name}({json.dumps(args, ensure_ascii=False)[:200]})"

    def render_result(self, result: ToolResult) -> str:
        """Human-readable summary of the tool result."""
        text = result.text
        if len(text) > 500:
            return text[:500] + "… (truncated)"
        return text


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        return list(self._tools.values())

    def get_schemas(self) -> list[dict]:
        return [t.get_schema() for t in self._tools.values()]

    def __contains__(self, name: str) -> bool:
        return name in self._tools
