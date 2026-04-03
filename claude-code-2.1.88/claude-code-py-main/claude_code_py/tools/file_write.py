"""File write tool — mirrors Claude Code FileWriteTool."""

from __future__ import annotations

import os
import difflib

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult


class FileWriteTool(BaseTool):
    name = "Write"
    description = (
        "Writes a file to the local filesystem. Overwrites existing file if present. "
        "If the file exists, you MUST Read it first. "
        "Prefer the Edit tool for modifying existing files — it only sends the diff. "
        "Only use Write for new files or complete rewrites."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to write (must be absolute)",
            },
            "content": {
                "type": "string",
                "description": "The content to write to the file",
            },
        },
        "required": ["file_path", "content"],
    }

    def render_tool_use(self, args: dict) -> str:
        path = args.get("file_path", "")
        content = args.get("content", "")
        lines = content.count("\n") + 1
        return f"{path} ({lines} lines, {len(content)} chars)"

    def render_result(self, result: ToolResult) -> str:
        return result.text

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = args.get("file_path", "")
        content = args.get("content", "")

        if not file_path:
            return ToolResult(error="file_path is required", is_error=True)

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)
        file_path = os.path.normpath(file_path)

        # Reject .ipynb
        if file_path.endswith(".ipynb"):
            return ToolResult(
                error="Use the NotebookEdit tool for Jupyter notebooks.",
                is_error=True,
            )

        # Track if this is create vs update
        is_new = not os.path.exists(file_path)
        old_content = None

        if not is_new:
            # Enforce: must Read before overwriting (mirrors source readFileState check)
            try:
                from ..tools.task_tools import _app_state
                if _app_state and not _app_state.was_file_read(file_path):
                    return ToolResult(
                        error=f"File exists but has not been read yet: {file_path}. "
                              "You must use the Read tool before overwriting an existing file.",
                        is_error=True,
                    )
            except Exception:
                pass

            try:
                with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                    old_content = f.read()
            except Exception:
                pass

        try:
            # Create parent directories
            os.makedirs(os.path.dirname(file_path), exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            lines = content.count("\n") + 1
            action = "Created" if is_new else "Updated"
            result_text = f"{action}: {file_path} ({lines} lines)"

            # Show diff for updates
            if old_content is not None and old_content != content:
                diff = _compact_diff(old_content, content, file_path)
                if diff:
                    result_text += f"\n\n{diff}"

            return ToolResult(output=result_text)

        except Exception as e:
            return ToolResult(error=str(e), is_error=True)


def _compact_diff(old: str, new: str, path: str, max_lines: int = 30) -> str:
    """Generate a compact unified diff."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(old_lines, new_lines, fromfile=path, tofile=path, lineterm=""))
    if not diff:
        return ""
    if len(diff) > max_lines:
        return "\n".join(diff[:max_lines]) + f"\n... ({len(diff) - max_lines} more diff lines)"
    return "\n".join(diff)
