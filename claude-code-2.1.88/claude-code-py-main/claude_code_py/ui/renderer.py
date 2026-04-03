"""Rich-based terminal renderer — improved with diff highlighting and better tool display."""

from __future__ import annotations

import sys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from rich.theme import Theme
from rich.table import Table

from ..llm.messages import ToolResult

custom_theme = Theme({
    "tool.name": "bold cyan",
    "tool.args": "dim",
    "tool.result": "green",
    "tool.error": "bold red",
    "info": "dim cyan",
    "warning": "bold yellow",
    "user.prompt": "bold green",
    "dim": "dim",
})

# Tool display names and icons
TOOL_ICONS = {
    "Bash": "$",
    "Read": "📄",
    "Edit": "✏️",
    "Write": "📝",
    "Grep": "🔍",
    "Glob": "📂",
    "Agent": "🤖",
    "WebSearch": "🌐",
    "WebFetch": "🌐",
    "NotebookEdit": "📓",
    "TaskCreate": "📋",
    "TaskUpdate": "📋",
    "TaskGet": "📋",
    "TaskList": "📋",
    "AskUserQuestion": "❓",
    "EnterPlanMode": "📐",
    "ExitPlanMode": "📐",
}


class Renderer:
    def __init__(self):
        self.console = Console(theme=custom_theme)
        self._streaming = False
        self._stream_buffer = ""

    # ── Streaming text output ───────────────────────────────────────

    def start_stream(self):
        self._streaming = True
        self._stream_buffer = ""

    def stream_text(self, text: str):
        """Print streaming text directly to terminal."""
        print(text, end="", flush=True)
        self._stream_buffer += text

    def end_stream(self):
        if self._streaming:
            print()  # newline after streaming
            self._streaming = False
            self._stream_buffer = ""

    # ── Markdown rendering ──────────────────────────────────────────

    def render_markdown(self, text: str):
        if text.strip():
            self.console.print(Markdown(text))

    # ── Tool call display ───────────────────────────────────────────

    def render_tool_call(self, tool_name: str, display: str):
        """Show a tool being called."""
        icon = TOOL_ICONS.get(tool_name, "⚡")
        self.console.print(f"\n  [tool.name]{icon} {tool_name}[/]  [tool.args]{display}[/]")

    def render_tool_result(self, tool_name: str, args: dict, result: ToolResult):
        """Show tool result — compact display."""
        if result.is_error:
            self.console.print(f"  [tool.error]✗ {tool_name} error:[/] {result.error[:300]}")
            return

        output = result.output
        icon = TOOL_ICONS.get(tool_name, "✓")

        # Special rendering for different tools
        if tool_name == "Bash":
            cmd = args.get("command", "")
            desc = args.get("description", "")
            header = desc if desc else cmd[:80]
            self.console.print(f"  [tool.result]{icon}[/] [dim]{header}[/]")
            if output.strip():
                self._show_compact_output(output, max_lines=10)

        elif tool_name in ("Read", "Grep", "Glob"):
            self.console.print(f"  [tool.result]{icon} {tool_name}[/]")
            if output.strip():
                self._show_compact_output(output, max_lines=8)

        elif tool_name in ("Edit", "Write"):
            self.console.print(f"  [tool.result]{icon} {tool_name}[/]  [dim]{output.split(chr(10))[0]}[/]")

        elif tool_name == "Agent":
            self.console.print(f"  [tool.result]{icon} Agent complete[/]")
            if output.strip():
                self._show_compact_output(output, max_lines=5)

        else:
            self.console.print(f"  [tool.result]✓ {tool_name}[/]")
            if output.strip() and len(output) < 200:
                self.console.print(Text(f"    {output}", style="dim"))

    def _show_compact_output(self, output: str, max_lines: int = 10):
        """Show output truncated to max_lines."""
        lines = output.split("\n")
        if len(lines) > max_lines:
            shown = "\n".join(lines[:max_lines])
            self.console.print(Text(shown, style="dim"))
            self.console.print(f"    [dim]... ({len(lines) - max_lines} more lines)[/]")
        else:
            self.console.print(Text(output, style="dim"))

    # ── Permission prompt ───────────────────────────────────────────

    async def ask_permission(self, tool_name: str, display: str) -> bool | str:
        """Ask user to approve a tool call.

        Returns:
            True       — allow this once
            False      — deny
            "always"   — allow this session (in-memory)
            "persist"  — allow forever (written to settings.json)
        """
        icon = TOOL_ICONS.get(tool_name, "⚠")
        self.console.print(f"\n  [warning]{icon} {tool_name}[/]")
        self.console.print(f"  [tool.args]{display}[/]")
        try:
            answer = input("  Allow? Yes(y) / Always this session(a) / Always forever(!) / No(n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
        if answer in ("!", "p", "persist", "always-persist", "forever"):
            return "persist"
        if answer in ("a", "always"):
            return "always"
        return answer in ("y", "yes")

    # ── Misc ────────────────────────────────────────────────────────

    def info(self, text: str):
        self.console.print(f"[info]{text}[/]")

    def error(self, text: str):
        self.console.print(f"[tool.error]{text}[/]")

    def warning(self, text: str):
        self.console.print(f"[warning]{text}[/]")

    def rule(self, title: str = ""):
        self.console.rule(title)

    def print_welcome(self, model: str, cwd: str):
        self.console.print(Panel(
            f"[bold]Claude Code[/] [dim](Python)[/]\n"
            f"Model: [cyan]{model}[/]\n"
            f"CWD: [dim]{cwd}[/]\n\n"
            f"Type [bold green]/help[/] for commands, [bold green]/exit[/] to quit\n"
            f"[dim]Escape+Enter for newline, Enter to send[/]",
            border_style="cyan",
        ))

    def print_cost(self, prompt_tokens: int, completion_tokens: int, model: str):
        """Display token usage."""
        total = prompt_tokens + completion_tokens
        self.console.print(
            f"[dim]Tokens: {prompt_tokens:,} in + {completion_tokens:,} out = {total:,} total[/]"
        )
