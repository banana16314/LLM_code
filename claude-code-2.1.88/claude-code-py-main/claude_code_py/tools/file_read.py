"""File read tool — mirrors Claude Code FileReadTool."""

from __future__ import annotations

import base64
import mimetypes
import os

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult

# Image extensions we support inline display for
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg"}
# Binary extensions we refuse to read
BINARY_EXTS = {
    ".exe", ".dll", ".so", ".dylib", ".o", ".a", ".lib",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".class", ".pyc", ".pyo", ".wasm",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".flac", ".wav",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
}
# Blocked device paths
BLOCKED_PATHS = {"/dev/zero", "/dev/random", "/dev/urandom", "/dev/stdin", "/dev/null"}


class FileReadTool(BaseTool):
    name = "Read"
    description = (
        "Reads a file from the local filesystem. You can access any file directly. "
        "Results are returned with line numbers (cat -n format). "
        "By default reads up to 2000 lines. Use offset/limit for large files. "
        "Can read images (PNG, JPG, etc.) and PDF files."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "The absolute path to the file to read",
            },
            "offset": {
                "type": "number",
                "description": "The line number to start reading from (1-based). Only provide if file is large.",
            },
            "limit": {
                "type": "number",
                "description": "The number of lines to read. Only provide if file is large.",
            },
            "pages": {
                "type": "string",
                "description": "Page range for PDF files (e.g., '1-5'). Max 20 pages per request.",
            },
        },
        "required": ["file_path"],
    }

    def is_read_only(self, args: dict) -> bool:
        return True

    def render_tool_use(self, args: dict) -> str:
        path = args.get("file_path", "")
        parts = [path]
        if args.get("offset"):
            parts.append(f"from line {args['offset']}")
        if args.get("limit"):
            parts.append(f"({args['limit']} lines)")
        return " ".join(parts)

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        file_path = args.get("file_path", "")
        offset = int(args.get("offset", 1))
        limit = int(args.get("limit", 2000))

        if not file_path:
            return ToolResult(error="file_path is required", is_error=True)

        # Resolve relative paths
        if not os.path.isabs(file_path):
            file_path = os.path.join(context.cwd, file_path)
        file_path = os.path.normpath(file_path)

        # Block device paths
        if file_path in BLOCKED_PATHS:
            return ToolResult(error=f"Cannot read device path: {file_path}", is_error=True)

        if not os.path.exists(file_path):
            return ToolResult(error=f"File not found: {file_path}", is_error=True)

        if os.path.isdir(file_path):
            return ToolResult(
                error=f"Path is a directory: {file_path}. Use Bash with 'ls' to list directory contents.",
                is_error=True,
            )

        ext = os.path.splitext(file_path)[1].lower()

        # Refuse binary files — by extension
        if ext in BINARY_EXTS:
            return ToolResult(
                error=f"Cannot read binary file ({ext}): {file_path}",
                is_error=True,
            )

        # Refuse binary files — by content sniffing (no extension match)
        if not ext or ext not in IMAGE_EXTS | {".pdf", ".ipynb"}:
            try:
                with open(file_path, "rb") as f:
                    sample = f.read(8192)
                if b"\x00" in sample:
                    return ToolResult(
                        error=f"Cannot read binary file: {file_path}",
                        is_error=True,
                    )
            except Exception:
                pass

        # Track that this file was read (for edit validation)
        try:
            from ..tools.task_tools import _app_state
            if _app_state:
                mtime = os.path.getmtime(file_path)
                _app_state.mark_file_read(file_path, mtime)
        except Exception:
            pass

        # Image files
        if ext in IMAGE_EXTS:
            return await self._read_image(file_path)

        # PDF files
        if ext == ".pdf":
            return await self._read_pdf(file_path, args.get("pages"))

        # Jupyter notebooks
        if ext == ".ipynb":
            return await self._read_notebook(file_path)

        # Text files
        return await self._read_text(file_path, offset, limit)

    async def _read_text(self, file_path: str, offset: int, limit: int) -> ToolResult:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                all_lines = f.readlines()

            if not all_lines:
                return ToolResult(output="(empty file)")

            # Apply offset (1-based) and limit
            start = max(0, offset - 1)
            end = start + limit
            selected = all_lines[start:end]

            # Format with line numbers (cat -n style)
            numbered = []
            for i, line in enumerate(selected, start=start + 1):
                numbered.append(f"{i:>6}\t{line.rstrip()}")

            output = "\n".join(numbered)

            if end < len(all_lines):
                output += f"\n\n... ({len(all_lines) - end} more lines)"

            return ToolResult(output=output)

        except Exception as e:
            return ToolResult(error=str(e), is_error=True)

    async def _read_image(self, file_path: str) -> ToolResult:
        try:
            size = os.path.getsize(file_path)
            if size > 20 * 1024 * 1024:  # 20MB limit
                return ToolResult(error=f"Image too large: {size} bytes", is_error=True)

            mime = mimetypes.guess_type(file_path)[0] or "image/png"
            with open(file_path, "rb") as f:
                data = base64.b64encode(f.read()).decode()

            # Return base64 data so multimodal LLMs can process the image.
            # For non-multimodal LLMs this will just be metadata.
            return ToolResult(
                output=f"[Image: {file_path} ({size} bytes, {mime})]\n"
                       f"Base64 data (first 200 chars): {data[:200]}...\n"
                       f"To view the full image, the base64 data URI is: data:{mime};base64,{data[:100]}..."
            )
        except Exception as e:
            return ToolResult(error=str(e), is_error=True)

    async def _read_pdf(self, file_path: str, pages: str | None) -> ToolResult:
        try:
            # Try pypdf if available
            import importlib
            pypdf = importlib.import_module("pypdf")
            reader = pypdf.PdfReader(file_path)
            total = len(reader.pages)

            # Parse page range
            start, end = 0, min(total, 20)
            if pages:
                parts = pages.split("-")
                start = max(0, int(parts[0]) - 1)
                end = min(total, int(parts[-1]))

            text_parts = []
            for i in range(start, end):
                text = reader.pages[i].extract_text()
                text_parts.append(f"--- Page {i + 1} ---\n{text}")

            output = "\n\n".join(text_parts)
            if end < total:
                output += f"\n\n... ({total - end} more pages)"
            return ToolResult(output=output)
        except ImportError:
            return ToolResult(error="PDF reading requires 'pypdf' package. Install with: pip install pypdf", is_error=True)
        except Exception as e:
            return ToolResult(error=str(e), is_error=True)

    async def _read_notebook(self, file_path: str) -> ToolResult:
        try:
            import json
            with open(file_path, "r", encoding="utf-8") as f:
                nb = json.load(f)

            cells = nb.get("cells", [])
            parts = []
            for i, cell in enumerate(cells):
                cell_type = cell.get("cell_type", "code")
                source = "".join(cell.get("source", []))
                parts.append(f"--- Cell {i} ({cell_type}) ---\n{source}")

                # Show outputs for code cells
                outputs = cell.get("outputs", [])
                for out in outputs:
                    if "text" in out:
                        parts.append("Output:\n" + "".join(out["text"]))
                    elif "data" in out:
                        for mime, data in out["data"].items():
                            if mime.startswith("text/"):
                                parts.append(f"Output ({mime}):\n" + "".join(data))

            return ToolResult(output="\n\n".join(parts) or "(empty notebook)")
        except Exception as e:
            return ToolResult(error=str(e), is_error=True)
