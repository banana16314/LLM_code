"""Bash command execution tool — mirrors Claude Code BashTool."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import uuid

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

log = logging.getLogger(__name__)

# Dangerous patterns that always require confirmation
DANGEROUS_PATTERNS = [
    r"rm\s+-rf\s+[/~]", r"rm\s+-rf\s+\.", r"git\s+push\s+--force",
    r"git\s+reset\s+--hard", r"git\s+clean\s+-f", r"git\s+checkout\s+--\s+\.",
    r"git\s+branch\s+-D", r"drop\s+table", r"drop\s+database",
    r">\s*/dev/sd", r"mkfs\.", r"dd\s+if=", r":(){ :\|:& };:",
    r"chmod\s+-R\s+777", r"curl.*\|\s*(bash|sh)",
]

# Patterns that are likely unintended
BLOCKED_SLEEP_PATTERN = re.compile(r"sleep\s+(\d+)")

MAX_OUTPUT_SIZE = 30_000  # chars, truncate beyond this

# Background task registry: task_id -> {proc, stdout_future, ...}
_background_tasks: dict[str, dict] = {}

# Session-level cwd tracking: persists across Bash calls (mirrors source behavior)
_session_cwd: str | None = None


def get_effective_cwd(context_cwd: str) -> str:
    """Return the effective cwd: session override if set, else context default."""
    global _session_cwd
    if _session_cwd and os.path.isdir(_session_cwd):
        return _session_cwd
    return context_cwd


def _detect_cwd_change(command: str, cwd: str) -> str | None:
    """Detect if a command ends with cd and extract the target directory.
    Returns the new cwd or None if no cd detected."""
    # Append pwd after the command to detect final working directory
    # This handles: cd foo && ..., ...; cd bar, etc.
    return None  # Detection done post-execution via pwd trick


class BashTool(BaseTool):
    name = "Bash"
    description = (
        "Executes a given bash command and returns its output. "
        "The working directory persists between commands, but shell state does not. "
        "IMPORTANT: Avoid using this tool for tasks that dedicated tools handle: "
        "use Read instead of cat, Edit instead of sed, Write instead of echo, "
        "Grep instead of grep/rg, Glob instead of find."
    )
    input_schema = {
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

    def is_destructive(self, args: dict) -> bool:
        cmd = args.get("command", "")
        return any(re.search(pat, cmd) for pat in DANGEROUS_PATTERNS)

    def render_tool_use(self, args: dict) -> str:
        cmd = args.get("command", "")
        desc = args.get("description", "")
        if desc:
            return f"{desc}\n  $ {cmd}"
        return f"$ {cmd}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        global _session_cwd
        command = args.get("command", "")
        timeout_ms = min(args.get("timeout", 120_000), 600_000)
        timeout_s = timeout_ms / 1000
        run_bg = args.get("run_in_background", False)

        if not command.strip():
            return ToolResult(error="Empty command", is_error=True)

        # Warn about blocked sleep patterns
        m = BLOCKED_SLEEP_PATTERN.search(command)
        if m and int(m.group(1)) > 10:
            return ToolResult(
                error=f"Detected `sleep {m.group(1)}` — avoid unnecessary sleep. "
                      "Use run_in_background or a different approach.",
                is_error=True,
            )

        # Use session cwd (persists across calls) or fall back to context cwd
        effective_cwd = get_effective_cwd(context.cwd)

        # Append pwd to detect cwd changes after command execution
        # Separator is unique enough to split reliably
        cwd_marker = "__CCPY_CWD_MARKER__"
        wrapped_command = f'{command}\n__exit_code=$?\necho ""\necho "{cwd_marker}"\npwd\nexit $__exit_code'

        try:
            proc = await asyncio.create_subprocess_shell(
                wrapped_command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=effective_cwd or None,
                env={**os.environ},
            )

            if run_bg:
                # Background mode: run original command (without pwd wrapper)
                proc_bg = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=effective_cwd or None,
                    env={**os.environ},
                )
                # Kill the wrapped proc since we launched a clean one
                try:
                    proc.kill()
                except Exception:
                    pass

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
                log.info(f"Background task {task_id} started (pid={proc_bg.pid})")
                return ToolResult(
                    output=f"Background task started (pid={proc_bg.pid}, id={task_id}).\n"
                           f"Command: {command[:100]}"
                )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_s
            )

            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

            # Extract new cwd from wrapped output
            actual_output = stdout_text
            if cwd_marker in stdout_text:
                parts = stdout_text.rsplit(cwd_marker, 1)
                actual_output = parts[0].rstrip()
                new_cwd = parts[1].strip()
                if new_cwd and os.path.isdir(new_cwd):
                    if new_cwd != effective_cwd:
                        _session_cwd = new_cwd
                        log.info(f"Bash cwd changed: {effective_cwd} → {new_cwd}")

            # Truncate large output
            output = _combine_output(actual_output, stderr_text)

            if proc.returncode != 0:
                return ToolResult(
                    output=output,
                    error=output if output else f"Exit code: {proc.returncode}",
                    is_error=True,
                )

            return ToolResult(output=output or "(no output)")

        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return ToolResult(error=f"Command timed out after {timeout_s:.0f}s", is_error=True)
        except Exception as e:
            return ToolResult(error=str(e), is_error=True)


def _combine_output(stdout: str, stderr: str) -> str:
    """Combine stdout/stderr, truncating if needed."""
    parts = []
    if stdout.strip():
        parts.append(stdout.strip())
    if stderr.strip():
        parts.append(stderr.strip())
    output = "\n".join(parts)

    if len(output) > MAX_OUTPUT_SIZE:
        half = MAX_OUTPUT_SIZE // 2
        output = (
            output[:half]
            + f"\n\n... (truncated {len(output) - MAX_OUTPUT_SIZE} chars) ...\n\n"
            + output[-half:]
        )
    return output
