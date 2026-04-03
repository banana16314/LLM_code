"""Core query loop — mirrors Claude Code query.ts with concurrent tool execution."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import AsyncIterator

from ..llm.client import LLMClient
from ..llm.messages import AssistantMessage, StreamChunk, ToolCall, ToolResult, UserMessage
from .tool import ToolContext, ToolRegistry
from .permissions import Permission, PermissionManager
from .state import AppState
from .compact import compact_messages
from ..utils.tokens import estimate_tokens
from ..config import config as default_config

log = logging.getLogger(__name__)

# Max iterations to prevent infinite loops (matches source MAX_TOOL_ITERATIONS)
MAX_TOOL_ITERATIONS = 40
# Max concurrent read-only tools
MAX_CONCURRENCY = 10
# Max output tokens recovery attempts (matches source)
MAX_OTK_RECOVERY = 3
# Recovery message injected when output is truncated
OTK_RECOVERY_MESSAGE = (
    "Output token limit hit. Resume directly from where you stopped — "
    "no apology, no recap, just continue the work seamlessly."
)
# Tool result size cap (chars). Larger results get truncated with preview.
MAX_TOOL_RESULT_CHARS = 50_000
RESULT_PREVIEW_CHARS = 2_000


class QueryLoop:
    def __init__(
        self,
        llm_client: LLMClient,
        tool_registry: ToolRegistry,
        permission_manager: PermissionManager,
        ui=None,
        context_overrides: dict | None = None,
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.perms = permission_manager
        self.ui = ui
        self._context_overrides = context_overrides or {}

    async def run(self, state: AppState) -> AsyncIterator[str]:
        """Run the query loop. Yields text chunks for streaming display."""
        context = ToolContext(
            cwd=state.cwd,
            session_id=state.session_id,
            permissions=self.perms,
            **self._context_overrides,
        )

        otk_recovery_count = 0

        for iteration in range(MAX_TOOL_ITERATIONS):
            # Auto-compact only when approaching context limit
            total_tokens = sum(
                estimate_tokens(m.content if isinstance(m.content, str) else str(m.content))
                for m in state.messages
            )
            max_ctx = default_config.max_context_tokens
            if total_tokens > max_ctx - 13_000:
                state.messages = await compact_messages(
                    state.messages, self.llm,
                    max_tokens=max_ctx,
                    keep_recent=6,
                )

            # Call LLM
            response = await self.llm.chat(
                messages=state.get_api_messages(),
                tools=self.tools.get_schemas() if self.tools.list_tools() else None,
                stream=True,
            )

            # Collect streamed response
            text_parts = []
            tool_calls: list[ToolCall] = []
            finish_reason = ""

            async for chunk in response:
                if chunk.type == "text":
                    text_parts.append(chunk.text)
                    yield chunk.text
                elif chunk.type == "tool_call_start" and chunk.tool_call:
                    tool_calls.append(chunk.tool_call)
                elif chunk.type == "done":
                    finish_reason = chunk.finish_reason
                    break

            # Build assistant message
            full_text = "".join(text_parts)
            assistant_msg = AssistantMessage(
                content=full_text,
                tool_calls=tool_calls,
            )
            state.add_assistant(assistant_msg)

            # ── Handle output truncation (finish_reason=length) ──
            if finish_reason == "length" and not tool_calls:
                if otk_recovery_count < MAX_OTK_RECOVERY:
                    otk_recovery_count += 1
                    log.info(f"OTK recovery attempt {otk_recovery_count}/{MAX_OTK_RECOVERY}")
                    state.add_user(OTK_RECOVERY_MESSAGE)
                    yield "\n"
                    continue  # Retry — LLM will resume from where it stopped
                else:
                    yield "\n[Output truncated — max recovery attempts reached]"
                    break

            if not tool_calls:
                break  # Done — no more tool calls

            # Reset recovery counter on successful tool execution
            otk_recovery_count = 0

            # ── Execute tool calls with concurrency ─────────────────
            read_only_batch = []
            serial_batch = []

            for tc in tool_calls:
                tool = self.tools.get(tc.name)
                if tool is None:
                    serial_batch.append(tc)
                    continue
                try:
                    args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    serial_batch.append(tc)
                    continue

                if tool.is_read_only(args):
                    read_only_batch.append((tc, tool, args))
                else:
                    serial_batch.append(tc)

            # Execute read-only tools concurrently
            if read_only_batch:
                tasks = [
                    self._execute_with_permission(tc, tool, args, context)
                    for tc, tool, args in read_only_batch
                ]
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for (tc, tool, args), result in zip(read_only_batch, results):
                    if isinstance(result, Exception):
                        result = ToolResult(error=str(result), is_error=True)
                    result = _budget_result(result)
                    if self.ui:
                        self.ui.render_tool_result(tc.name, args, result)
                    state.add_tool_result(tc.id, tc.name, result)

            # Execute write tools serially
            for tc in serial_batch:
                tool = self.tools.get(tc.name)
                if tool is None:
                    result = ToolResult(error=f"Unknown tool: {tc.name}", is_error=True)
                    state.add_tool_result(tc.id, tc.name, result)
                    continue

                try:
                    args = json.loads(tc.arguments) if tc.arguments else {}
                except json.JSONDecodeError:
                    result = ToolResult(error=f"Invalid JSON: {tc.arguments[:200]}", is_error=True)
                    state.add_tool_result(tc.id, tc.name, result)
                    continue

                result = await self._execute_with_permission(tc, tool, args, context)
                result = _budget_result(result)
                if self.ui:
                    self.ui.render_tool_result(tc.name, args, result)
                state.add_tool_result(tc.id, tc.name, result)

            # ── Verify tool_use / tool_result pairing ────────────
            self._ensure_tool_result_pairing(state, tool_calls)

        else:
            yield "\n[Max tool iterations reached]"

    async def _execute_with_permission(
        self, tc: ToolCall, tool, args: dict, context: ToolContext
    ) -> ToolResult:
        """Check permissions and execute a tool."""
        perm = self.perms.check(tc.name, args)

        if perm == Permission.DENY:
            return ToolResult(error="Permission denied by policy", is_error=True)

        if perm == Permission.ASK:
            if self.ui:
                display = tool.render_tool_use(args)
                answer = await self.ui.ask_permission(tc.name, display)
                if answer == "persist":
                    # Persist to settings.json — never ask again across sessions
                    self.perms.grant_persistent(tc.name)
                elif answer == "always":
                    # Session-only grant
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

    def _ensure_tool_result_pairing(self, state: AppState, tool_calls: list[ToolCall]):
        """Ensure every tool_use has a matching tool_result. Inject synthetic error if missing."""
        # Collect tool_call_ids that have results
        result_ids = set()
        for m in reversed(state.messages):
            if hasattr(m, "tool_call_id") and m.tool_call_id:
                result_ids.add(m.tool_call_id)
            elif m.role == "assistant":
                break  # Only check results after the last assistant message

        for tc in tool_calls:
            if tc.id not in result_ids:
                log.warning(f"Missing tool_result for tool_use {tc.id} ({tc.name}), injecting error")
                state.add_tool_result(
                    tc.id, tc.name,
                    ToolResult(
                        error=f"Tool {tc.name} was called but did not return a result.",
                        is_error=True,
                    ),
                )


def _budget_result(result: ToolResult) -> ToolResult:
    """Truncate tool results that exceed the size budget."""
    text = result.text
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return result
    # Truncate with preview
    preview = text[:RESULT_PREVIEW_CHARS]
    truncated_msg = (
        f"Output too large ({len(text):,} chars, max {MAX_TOOL_RESULT_CHARS:,}).\n\n"
        f"Preview (first {RESULT_PREVIEW_CHARS:,} chars):\n{preview}\n\n"
        f"... ({len(text) - RESULT_PREVIEW_CHARS:,} more chars truncated)"
    )
    if result.is_error:
        return ToolResult(error=truncated_msg, is_error=True)
    return ToolResult(output=truncated_msg)
