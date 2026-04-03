"""Jupyter Notebook edit tool."""

from __future__ import annotations

import json
import os

from ..core.tool import BaseTool, ToolContext
from ..llm.messages import ToolResult


class NotebookEditTool(BaseTool):
    name = "NotebookEdit"
    description = (
        "Replaces, inserts, or deletes a cell in a Jupyter notebook (.ipynb file). "
        "The notebook_path must be absolute. cell_number is 0-indexed. "
        "Use edit_mode=insert to add a new cell, edit_mode=delete to remove one."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "notebook_path": {
                "type": "string",
                "description": "Absolute path to the .ipynb file",
            },
            "cell_number": {
                "type": "number",
                "description": "0-indexed cell number to edit (default: last cell)",
            },
            "new_source": {
                "type": "string",
                "description": "The new source content for the cell",
            },
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown"],
                "description": "Cell type (required for insert mode)",
            },
            "edit_mode": {
                "type": "string",
                "enum": ["replace", "insert", "delete"],
                "description": "Edit mode (default: replace)",
            },
        },
        "required": ["notebook_path", "new_source"],
    }

    def render_tool_use(self, args: dict) -> str:
        path = args.get("notebook_path", "")
        mode = args.get("edit_mode", "replace")
        cell = args.get("cell_number", "last")
        return f"{mode} cell {cell} in {path}"

    async def call(self, args: dict, context: ToolContext) -> ToolResult:
        nb_path = args.get("notebook_path", "")
        new_source = args.get("new_source", "")
        cell_type = args.get("cell_type", None)
        edit_mode = args.get("edit_mode", "replace")

        if not nb_path:
            return ToolResult(error="notebook_path is required", is_error=True)

        if not os.path.isabs(nb_path):
            nb_path = os.path.join(context.cwd, nb_path)

        if not os.path.exists(nb_path):
            return ToolResult(error=f"Notebook not found: {nb_path}", is_error=True)

        try:
            with open(nb_path, "r", encoding="utf-8") as f:
                notebook = json.load(f)
        except Exception as e:
            return ToolResult(error=f"Cannot parse notebook: {e}", is_error=True)

        cells = notebook.get("cells", [])
        cell_number = args.get("cell_number")
        if cell_number is None:
            cell_number = len(cells) - 1 if cells else 0
        cell_number = int(cell_number)

        if edit_mode == "insert":
            if not cell_type:
                return ToolResult(error="cell_type is required for insert mode", is_error=True)
            new_cell = {
                "cell_type": cell_type,
                "source": new_source.splitlines(True) if new_source else [],
                "metadata": {},
            }
            if cell_type == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            # Insert after cell_number (or at beginning if -1)
            insert_at = min(cell_number + 1, len(cells))
            cells.insert(insert_at, new_cell)
            result_msg = f"Inserted {cell_type} cell at position {insert_at}"

        elif edit_mode == "delete":
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(error=f"Cell {cell_number} out of range (0-{len(cells)-1})", is_error=True)
            deleted = cells.pop(cell_number)
            result_msg = f"Deleted cell {cell_number} ({deleted.get('cell_type', 'unknown')})"

        else:  # replace
            if cell_number < 0 or cell_number >= len(cells):
                return ToolResult(error=f"Cell {cell_number} out of range (0-{len(cells)-1})", is_error=True)
            cells[cell_number]["source"] = new_source.splitlines(True) if new_source else []
            if cell_type:
                cells[cell_number]["cell_type"] = cell_type
            result_msg = f"Replaced cell {cell_number}"

        notebook["cells"] = cells

        try:
            with open(nb_path, "w", encoding="utf-8") as f:
                json.dump(notebook, f, indent=1, ensure_ascii=False)
                f.write("\n")
            return ToolResult(output=f"{result_msg} in {nb_path}")
        except Exception as e:
            return ToolResult(error=f"Write failed: {e}", is_error=True)
