"""Cron tools — session-scoped scheduled tasks."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

# In-memory job store (session-scoped)
_jobs: dict[str, dict] = {}
_tasks: dict[str, asyncio.Task] = {}


class CronCreateTool(BaseTool):
    name = "CronCreate"
    description = (
        "Schedule a prompt to run at a future time. Uses 5-field cron syntax. "
        "Jobs only live in the current session. "
        "Recurring tasks auto-expire after 3 days."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "cron": {
                "type": "string",
                "description": "5-field cron expression: 'M H DoM Mon DoW'",
            },
            "prompt": {
                "type": "string",
                "description": "The prompt to enqueue at each fire time",
            },
            "recurring": {
                "type": "boolean",
                "description": "true (default) = recurring, false = one-shot",
            },
        },
        "required": ["cron", "prompt"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        cron = args.get("cron", "")
        recurring = args.get("recurring", True)
        return f"{'Recurring' if recurring else 'One-shot'} job: {cron}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        cron_expr = args.get("cron", "")
        prompt = args.get("prompt", "")
        recurring = args.get("recurring", True)

        if not cron_expr or not prompt:
            return ToolResult(error="cron and prompt are required", is_error=True)

        parts = cron_expr.strip().split()
        if len(parts) != 5:
            return ToolResult(error="cron must be a 5-field expression: M H DoM Mon DoW", is_error=True)

        job_id = uuid.uuid4().hex[:8]
        _jobs[job_id] = {
            "id": job_id,
            "cron": cron_expr,
            "prompt": prompt,
            "recurring": recurring,
            "created": datetime.now().isoformat(),
        }

        mode = "Recurring (auto-expires in 3 days)" if recurring else "One-shot"
        return ToolResult(output=f"Scheduled job {job_id}: {mode}\nCron: {cron_expr}\nPrompt: {prompt[:100]}")


class CronDeleteTool(BaseTool):
    name = "CronDelete"
    description = "Cancel a scheduled cron job."
    input_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "description": "Job ID to cancel"},
        },
        "required": ["id"],
    }

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        job_id = args.get("id", "")
        if job_id in _jobs:
            del _jobs[job_id]
            if job_id in _tasks:
                _tasks[job_id].cancel()
                del _tasks[job_id]
            return ToolResult(output=f"Cancelled job {job_id}")
        return ToolResult(error=f"Job {job_id} not found", is_error=True)


class CronListTool(BaseTool):
    name = "CronList"
    description = "List all scheduled cron jobs in this session."
    input_schema = {"type": "object", "properties": {}}

    def is_read_only(self, args: dict) -> bool:
        return True

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        if not _jobs:
            return ToolResult(output="No scheduled jobs.")
        lines = []
        for job in _jobs.values():
            mode = "recurring" if job["recurring"] else "one-shot"
            lines.append(f"{job['id']}: [{mode}] {job['cron']} → {job['prompt'][:60]}")
        return ToolResult(output="\n".join(lines))
