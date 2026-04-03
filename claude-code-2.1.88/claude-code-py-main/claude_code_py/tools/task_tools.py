"""Task management tools."""

from __future__ import annotations

import json
from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult


# We need a reference to AppState — passed via context or a global.
# For simplicity, we use a module-level reference that main.py sets.
_app_state = None


def set_app_state(state):
    global _app_state
    _app_state = state


class TaskCreateTool(BaseTool):
    name = "TaskCreate"
    description = "Create a new task to track work."
    input_schema = {
        "type": "object",
        "properties": {
            "subject": {"type": "string", "description": "Brief task title"},
            "description": {"type": "string", "description": "Detailed description"},
        },
        "required": ["subject", "description"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True  # metadata-only

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if not state:
            return ToolResult(error="No app state available", is_error=True)
        task = state.create_task(args.get("subject", ""), args.get("description", ""))
        return ToolResult(output=f"Created task #{task.id}: {task.subject}")


class TaskGetTool(BaseTool):
    name = "TaskGet"
    description = "Get details of a task by ID."
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string", "description": "The task ID"},
        },
        "required": ["taskId"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if not state:
            return ToolResult(error="No app state available", is_error=True)
        task = state.get_task(args.get("taskId", ""))
        if not task:
            return ToolResult(error="Task not found", is_error=True)
        return ToolResult(output=json.dumps({
            "id": task.id, "subject": task.subject,
            "description": task.description, "status": task.status,
            "blocked_by": task.blocked_by, "blocks": task.blocks,
        }, ensure_ascii=False, indent=2))


class TaskUpdateTool(BaseTool):
    name = "TaskUpdate"
    description = "Update a task's status or details."
    input_schema = {
        "type": "object",
        "properties": {
            "taskId": {"type": "string"},
            "status": {"type": "string", "enum": ["pending", "in_progress", "completed", "deleted"]},
            "subject": {"type": "string"},
            "description": {"type": "string"},
        },
        "required": ["taskId"],
    }

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if not state:
            return ToolResult(error="No app state available", is_error=True)
        task = state.get_task(args.get("taskId", ""))
        if not task:
            return ToolResult(error="Task not found", is_error=True)

        if "status" in args:
            if args["status"] == "deleted":
                del state.tasks[task.id]
                return ToolResult(output=f"Deleted task #{task.id}")
            task.status = args["status"]
        if "subject" in args:
            task.subject = args["subject"]
        if "description" in args:
            task.description = args["description"]

        return ToolResult(output=f"Updated task #{task.id}: status={task.status}")


class TaskListTool(BaseTool):
    name = "TaskList"
    description = "List all tasks."
    input_schema = {"type": "object", "properties": {}}

    def is_read_only(self, args: dict) -> bool:
        return True

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        state = _app_state
        if not state:
            return ToolResult(error="No app state available", is_error=True)
        tasks = state.list_tasks()
        if not tasks:
            return ToolResult(output="No tasks.")
        lines = []
        for t in tasks:
            blocked = f" (blocked by: {','.join(t.blocked_by)})" if t.blocked_by else ""
            lines.append(f"#{t.id} [{t.status}] {t.subject}{blocked}")
        return ToolResult(output="\n".join(lines))
