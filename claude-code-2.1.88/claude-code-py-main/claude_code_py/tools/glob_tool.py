"""Glob tool — file name search, mirrors Claude Code GlobTool."""

from __future__ import annotations

import os
import time
import pathlib

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

MAX_RESULTS = 100


class GlobTool(BaseTool):
    name = "Glob"
    description = (
        "Fast file pattern matching tool that works with any codebase size. "
        "Supports glob patterns like '**/*.js' or 'src/**/*.ts'. "
        "Returns matching file paths sorted by modification time."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "The glob pattern to match files against",
            },
            "path": {
                "type": "string",
                "description": "The directory to search in (default: cwd)",
            },
        },
        "required": ["pattern"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        pattern = args.get("pattern", "")
        path = args.get("path", ".")
        return f"{pattern} in {path}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        pattern = args.get("pattern", "")
        path = args.get("path", context.cwd or ".")

        if not pattern:
            return ToolResult(error="pattern is required", is_error=True)

        # Handle absolute patterns: split into base path + relative pattern
        if os.path.isabs(pattern):
            # e.g. pattern="/home/user/project/**/*.py"
            # Find the longest existing directory prefix
            parts = pattern.split("/")
            for i in range(len(parts), 0, -1):
                candidate = "/".join(parts[:i])
                if os.path.isdir(candidate):
                    path = candidate
                    remaining = "/".join(parts[i:])
                    pattern = remaining if remaining else "**/*"
                    break
            else:
                # Fallback: use pattern parent as path
                import pathlib as _pl
                p = _pl.PurePosixPath(pattern)
                path = str(p.parent)
                pattern = p.name

        start = time.monotonic()

        try:
            base = pathlib.Path(path)
            if not base.exists():
                return ToolResult(error=f"Path does not exist: {path}", is_error=True)
            if not base.is_dir():
                return ToolResult(error=f"Path is not a directory: {path}", is_error=True)

            # Collect matches, skipping .git directories
            matches = []
            for p in base.glob(pattern):
                # Skip .git internals
                parts = p.parts
                if ".git" in parts:
                    continue
                if p.is_file():
                    try:
                        mtime = p.stat().st_mtime
                    except OSError:
                        mtime = 0
                    matches.append((p, mtime))

            # Sort by modification time (newest first)
            matches.sort(key=lambda x: x[1], reverse=True)

            duration_ms = int((time.monotonic() - start) * 1000)
            total = len(matches)
            truncated = total > MAX_RESULTS

            shown = matches[:MAX_RESULTS]
            lines = [str(p) for p, _ in shown]
            output = "\n".join(lines)

            if not lines:
                output = "No files matched."
            elif truncated:
                output += f"\n\n... and {total - MAX_RESULTS} more files (showing first {MAX_RESULTS})"

            # Add metadata
            output = f"Found {total} file(s) in {duration_ms}ms\n{output}"

            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(error=str(e), is_error=True)
