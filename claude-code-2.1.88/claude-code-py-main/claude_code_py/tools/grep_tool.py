"""Grep tool — content search using ripgrep, mirrors Claude Code GrepTool."""

from __future__ import annotations

import asyncio
import shutil

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

DEFAULT_HEAD_LIMIT = 250  # match source default
MAX_COLUMN_WIDTH = 500  # truncate long lines


class GrepTool(BaseTool):
    name = "Grep"
    description = (
        "A powerful search tool built on ripgrep. "
        "Supports full regex syntax (e.g., 'log.*Error', 'function\\s+\\w+'). "
        "Filter files with glob parameter (e.g., '*.js') or type parameter (e.g., 'js', 'py'). "
        "Output modes: 'content' shows matching lines, 'files_with_matches' shows only file paths (default), "
        "'count' shows match counts."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in (default: cwd)",
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g. '*.js', '**/*.tsx')",
            },
            "type": {
                "type": "string",
                "description": "File type to search (rg --type). E.g., 'js', 'py', 'rust'",
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": "Output mode (default: files_with_matches)",
            },
            "-i": {
                "type": "boolean",
                "description": "Case insensitive search",
            },
            "-B": {
                "type": "number",
                "description": "Lines to show before each match (requires output_mode: content)",
            },
            "-A": {
                "type": "number",
                "description": "Lines to show after each match (requires output_mode: content)",
            },
            "-C": {
                "type": "number",
                "description": "Context lines around matches (alias for context)",
            },
            "context": {
                "type": "number",
                "description": "Context lines around matches",
            },
            "-n": {
                "type": "boolean",
                "description": "Show line numbers (default true for content mode)",
            },
            "multiline": {
                "type": "boolean",
                "description": "Enable multiline mode where . matches newlines",
            },
            "head_limit": {
                "type": "number",
                "description": "Limit output to first N entries (default 250)",
            },
            "offset": {
                "type": "number",
                "description": "Skip first N entries before applying head_limit",
            },
        },
        "required": ["pattern"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        glob_pat = args.get("glob", "")
        parts = [f"/{pattern}/"]
        if glob_pat:
            parts.append(f"--glob {glob_pat}")
        parts.append(f"in {path}")
        return " ".join(parts)

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "")
        path = args.get("path", context.cwd or ".")
        glob_pat = args.get("glob")
        file_type = args.get("type")
        output_mode = args.get("output_mode", "files_with_matches")
        case_insensitive = args.get("-i", False)
        before = args.get("-B")
        after = args.get("-A")
        context_lines = args.get("-C") or args.get("context")
        show_line_nums = args.get("-n", True)
        multiline = args.get("multiline", False)
        head_limit = int(args.get("head_limit", DEFAULT_HEAD_LIMIT))
        offset = int(args.get("offset", 0))

        if not pattern:
            return ToolResult(error="pattern is required", is_error=True)

        # Build rg command
        use_rg = shutil.which("rg") is not None
        if not use_rg:
            return ToolResult(
                error="ripgrep (rg) not found. Install with: apt install ripgrep",
                is_error=True,
            )

        cmd = ["rg", "--no-heading", f"--max-columns={MAX_COLUMN_WIDTH}"]

        # VCS exclusions
        cmd.append("--hidden")
        cmd.append("--glob=!.git/")

        # Output mode
        if output_mode == "files_with_matches":
            cmd.append("-l")
        elif output_mode == "count":
            cmd.append("-c")
        else:
            # content mode
            if show_line_nums:
                cmd.append("-n")

        # Options
        if case_insensitive:
            cmd.append("-i")
        if multiline:
            cmd.extend(["-U", "--multiline-dotall"])

        # Context (only for content mode)
        if output_mode == "content":
            if context_lines is not None:
                cmd.extend(["-C", str(int(context_lines))])
            else:
                if before is not None:
                    cmd.extend(["-B", str(int(before))])
                if after is not None:
                    cmd.extend(["-A", str(int(after))])

        # File filtering
        if glob_pat:
            cmd.extend(["--glob", glob_pat])
        if file_type:
            cmd.extend(["--type", file_type])

        # Pattern (use -e if starts with -)
        if pattern.startswith("-"):
            cmd.extend(["-e", pattern])
        else:
            cmd.append(pattern)

        cmd.append(path)

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode("utf-8", errors="replace").strip()

            # Convert absolute paths to relative (saves tokens, matches source)
            if output and context.cwd:
                output = _to_relative_paths(output, context.cwd)

            if not output:
                if proc.returncode == 1:
                    return ToolResult(output="No matches found.")
                if stderr:
                    err = stderr.decode("utf-8", errors="replace").strip()
                    return ToolResult(error=err, is_error=True)
                return ToolResult(output="No matches found.")

            # Apply offset and head_limit
            lines = output.split("\n")
            if offset > 0:
                lines = lines[offset:]
            total = len(lines)
            if head_limit and head_limit > 0 and len(lines) > head_limit:
                lines = lines[:head_limit]
                output = "\n".join(lines)
                output += f"\n\n... (truncated, showing {head_limit} of {total} results)"
            else:
                output = "\n".join(lines)

            return ToolResult(output=output)

        except asyncio.TimeoutError:
            return ToolResult(error="Search timed out after 30s", is_error=True)
        except Exception as e:
            return ToolResult(error=str(e), is_error=True)


def _to_relative_paths(output: str, cwd: str) -> str:
    """Replace absolute paths with relative paths to save tokens."""
    if not cwd.endswith("/"):
        cwd_prefix = cwd + "/"
    else:
        cwd_prefix = cwd
    return output.replace(cwd_prefix, "")
