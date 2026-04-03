"""PlanMode tools — EnterPlanMode / ExitPlanMode."""

from __future__ import annotations

import os

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult
from ..tools.task_tools import _app_state


class EnterPlanModeTool(BaseTool):
    name = "EnterPlanMode"
    description = (
        "Transition into plan mode for designing implementation approaches. "
        "Use proactively for non-trivial implementation tasks. "
        "In plan mode, explore the codebase and design a plan for user approval."
    )
    input_schema = {"type": "object", "properties": {}}

    def is_read_only(self, args: dict) -> bool:
        return True

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if state:
            state.plan_mode = True
            # Create plan file
            plan_dir = os.path.join(context.cwd, ".claude", "plans")
            os.makedirs(plan_dir, exist_ok=True)
            import uuid
            plan_file = os.path.join(plan_dir, f"plan-{uuid.uuid4().hex[:8]}.md")
            state.plan_file = plan_file
            return ToolResult(output=f"Entered plan mode. Write your plan to: {plan_file}")
        return ToolResult(output="Entered plan mode.")


class ExitPlanModeTool(BaseTool):
    name = "ExitPlanMode"
    description = (
        "Exit plan mode and request user approval for the plan. "
        "The plan should already be written to the plan file."
    )
    input_schema = {"type": "object", "properties": {}}

    def is_read_only(self, args: dict) -> bool:
        return True

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if state:
            state.plan_mode = False
            plan_file = state.plan_file
            if plan_file and os.path.exists(plan_file):
                with open(plan_file, "r") as f:
                    plan_content = f.read()
                return ToolResult(
                    output=f"Plan submitted for approval.\n\nPlan file: {plan_file}\n\n{plan_content[:2000]}"
                )
            return ToolResult(output="Exited plan mode (no plan file found).")
        return ToolResult(output="Exited plan mode.")
