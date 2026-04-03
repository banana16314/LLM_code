"""Slash command registry."""

from __future__ import annotations

from typing import Callable, Awaitable


class CommandRegistry:
    def __init__(self):
        self._commands: dict[str, dict] = {}

    def register(self, name: str, handler: Callable[..., Awaitable[str | None]], description: str = ""):
        self._commands[name] = {"handler": handler, "description": description}

    def get(self, name: str):
        return self._commands.get(name)

    def list_commands(self) -> list[tuple[str, str]]:
        return [(name, info["description"]) for name, info in sorted(self._commands.items())]

    def __contains__(self, name: str) -> bool:
        return name in self._commands
