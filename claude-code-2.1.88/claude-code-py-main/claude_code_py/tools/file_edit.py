"""File edit tool — exact string replacement, mirrors Claude Code FileEditTool."""

from __future__ import annotations

import os
import difflib

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024  # 1 GB


class FileEditTool(BaseTool):
    name = "Edit"
    description = (
        "Performs exact string replacements in files. "
        "You must Read the file before editing. "
        "The edit will FAIL if old_string is not unique. Provide more context to make it unique, "
        "or use replace_all to change every instance."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to modify",
            },
            "old_string": {
                "type": "string",
                "description": "The exact text to replace",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement text (must be different from old_string)",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default false)",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }

    def render_tool_use(self, args: dict) -> str:
        path = args.get("file_path", "")
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        # Show a compact diff
        old_preview = old[:80].replace("\n", "\\n")
        new_preview = new[:80].replace("\n", "\\n")
        return f"{path}\n  - {old_preview!r}\n  + {new_preview!r}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = args.get("file_path", "")
        old_string = args.get("old_string", "")
        new_string = args.get("new_string", "")
        replace_all = args.get("replace_all", False)

        # ── Validation ──────────────────────────────────────────────
        if not file_path:
            return ToolResult(error="file_path is required", is_error=True)
        if not old_string:
            return ToolResult(error="old_string is required", is_error=True)
        if old_string == new_string:
            return ToolResult(error="old_string and new_string are identical", is_error=True)

        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)
        file_path = os.path.normpath(file_path)

        # Reject .ipynb (use NotebookEdit) — check before file existence
        if file_path.endswith(".ipynb"):
            return ToolResult(
                error="Use the NotebookEdit tool for Jupyter notebooks, not Edit.",
                is_error=True,
            )

        if not os.path.exists(file_path):
            return ToolResult(error=f"File not found: {file_path}", is_error=True)

        if os.path.isdir(file_path):
            return ToolResult(error=f"Path is a directory: {file_path}", is_error=True)

        # Enforce: must Read before Edit (mirrors source readFileState check)
        try:
            from ..tools.task_tools import _app_state
            if _app_state and not _app_state.was_file_read(file_path):
                return ToolResult(
                    error=f"File has not been read yet: {file_path}. "
                          "You must use the Read tool before editing a file.",
                    is_error=True,
                )
        except Exception:
            pass

        # Check file size
        size = os.path.getsize(file_path)
        if size > MAX_EDIT_FILE_SIZE:
            return ToolResult(error=f"File too large: {size} bytes (max {MAX_EDIT_FILE_SIZE})", is_error=True)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            return ToolResult(error=f"Cannot read file: {e}", is_error=True)

        # ── Find matches ────────────────────────────────────────────
        count = content.count(old_string)

        if count == 0:
            # Try quote normalization (smart quotes → straight quotes)
            normalized = _normalize_quotes(old_string)
            count = content.count(normalized)
            if count > 0:
                old_string = normalized
            else:
                return ToolResult(
                    error=f"old_string not found in {file_path}. "
                          "Make sure the string matches exactly (including whitespace and indentation).",
                    is_error=True,
                )

        if count > 1 and not replace_all:
            return ToolResult(
                error=f"old_string found {count} times in {file_path}. "
                      "Provide more surrounding context to make it unique, "
                      "or set replace_all=true to replace all occurrences.",
                is_error=True,
            )

        # ── Apply replacement ───────────────────────────────────────
        if replace_all:
            new_content = content.replace(old_string, new_string)
            replaced = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replaced = 1

        # Create parent dirs if needed
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        # Show context around the replacement
        snippet = _get_snippet(new_content, new_string)
        result = f"Replaced {replaced} occurrence(s) in {file_path}"
        if snippet:
            result += f"\n\nContext:\n{snippet}"

        return ToolResult(output=result)


def _normalize_quotes(text: str) -> str:
    """Normalize smart quotes to straight quotes."""
    replacements = {
        "\u2018": "'", "\u2019": "'",  # single smart quotes
        "\u201c": '"', "\u201d": '"',  # double smart quotes
        "\u2013": "-", "\u2014": "--",  # en/em dash
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _get_snippet(content: str, target: str, context_lines: int = 3) -> str:
    """Get a few lines around the replacement for confirmation."""
    lines = content.split("\n")
    # Find line containing start of target
    target_start = content.find(target)
    if target_start == -1:
        return ""
    line_no = content[:target_start].count("\n")
    start = max(0, line_no - context_lines)
    end = min(len(lines), line_no + context_lines + target.count("\n") + 1)
    snippet_lines = []
    for i in range(start, end):
        snippet_lines.append(f"{i + 1:>6}\t{lines[i]}")
    return "\n".join(snippet_lines)
