"""Agent tool — spawn sub-agent for complex tasks."""

from __future__ import annotations

import logging

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

log = logging.getLogger(__name__)


class AgentTool(BaseTool):
    name = "Agent"
    description = "Launch a sub-agent to handle a complex task autonomously. The agent has access to all tools."
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short (3-5 word) description of the task",
            },
            "prompt": {
                "type": "string",
                "description": "The detailed task for the agent to perform",
            },
        },
        "required": ["description", "prompt"],
    }

    def is_read_only(self, args: dict) -> bool:
        return False

    def render_tool_use(self, args: dict) -> str:
        desc = args.get("description", "")
        return f"Sub-agent: {desc}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        prompt = args.get("prompt", "")
        description = args.get("description", "")

        if not prompt:
            return ToolResult(error="prompt is required", is_error=True)

        # Check recursion depth
        if context.agent_depth >= context.max_agent_depth:
            return ToolResult(
                error=f"Max agent recursion depth ({context.max_agent_depth}) reached. "
                      "Cannot spawn more sub-agents.",
                is_error=True,
            )

        # Import here to avoid circular imports
        from ..llm.client import LLMClient
        from ..core.query_loop import QueryLoop
        from ..core.tool import ToolRegistry
        from ..core.permissions import PermissionManager
        from ..core.state import AppState
        from ..core.context import build_system_prompt
        from ..tools import register_all
        from ..config import config

        # Create a fresh sub-agent, inheriting current config
        sub_registry = ToolRegistry()
        register_all(sub_registry)
        sub_perms = PermissionManager(
            auto_approve=context.permissions.auto_approve if context.permissions else False,
        )
        sub_client = LLMClient(config)
        sub_state = AppState(cwd=context.cwd)

        # Build system prompt
        system_prompt = build_system_prompt(context.cwd)
        sub_state.set_system(system_prompt + f"\n\nYou are a sub-agent. Task: {description}")
        sub_state.add_user(prompt)

        # Pass incremented depth via context_overrides
        sub_loop = QueryLoop(
            sub_client, sub_registry, sub_perms,
            context_overrides={
                "agent_depth": context.agent_depth + 1,
                "max_agent_depth": context.max_agent_depth,
            },
        )

        # Collect all output
        output_parts = []
        try:
            async for chunk in sub_loop.run(sub_state):
                output_parts.append(chunk)
        except Exception as e:
            log.exception("Sub-agent failed")
            return ToolResult(error=f"Sub-agent error: {e}", is_error=True)

        result_text = "".join(output_parts)
        if not result_text.strip():
            result_text = "(Agent completed with no text output)"

        return ToolResult(output=result_text)
