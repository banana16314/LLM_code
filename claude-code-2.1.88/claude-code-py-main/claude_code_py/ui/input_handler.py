"""User input handling with prompt_toolkit."""

from __future__ import annotations

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.key_binding import KeyBindings
import os


class InputHandler:
    def __init__(self, history_file: str | None = None):
        if history_file is None:
            history_dir = os.path.expanduser("~/.claude")
            os.makedirs(history_dir, exist_ok=True)
            history_file = os.path.join(history_dir, "python_cli_history")

        self._bindings = KeyBindings()

        @self._bindings.add("escape", "enter")
        def _newline(event):
            event.current_buffer.insert_text("\n")

        self.session = PromptSession(
            history=FileHistory(history_file),
            auto_suggest=AutoSuggestFromHistory(),
            multiline=False,
            key_bindings=self._bindings,
        )

    async def get_input(self, prompt: str = "\n> ") -> str:
        """Get user input (async). Returns /exit on EOF/Ctrl-C."""
        try:
            text = await self.session.prompt_async(prompt)
            return text.strip()
        except (EOFError, KeyboardInterrupt):
            return "/exit"
