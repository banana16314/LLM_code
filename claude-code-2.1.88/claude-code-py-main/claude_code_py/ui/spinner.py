"""Simple spinner for indicating work in progress."""

from __future__ import annotations

import sys
import contextlib
import asyncio


class Spinner:
    """Text-based spinner using stderr. Clears itself cleanly before stdout output."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, console=None):
        self._running = False
        self._task: asyncio.Task | None = None
        self._message = ""
        self._started = False

    def start(self, message: str = "Thinking..."):
        if self._started:
            return
        self._message = message
        self._running = True
        self._started = True
        sys.stderr.write(f"\r{self.FRAMES[0]} {message}")
        sys.stderr.flush()
        try:
            loop = asyncio.get_running_loop()
            self._task = loop.create_task(self._animate())
        except RuntimeError:
            pass

    async def _animate(self):
        idx = 0
        try:
            while self._running:
                frame = self.FRAMES[idx % len(self.FRAMES)]
                sys.stderr.write(f"\r{frame} {self._message}")
                sys.stderr.flush()
                idx += 1
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            pass  # clean exit

    async def stop_async(self):
        """Async stop — awaits the animation task to fully finish before clearing."""
        if not self._started:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        # Clear spinner line
        clear_len = len(self._message) + 4
        sys.stderr.write("\r" + " " * clear_len + "\r")
        sys.stderr.flush()
        self._started = False

    def stop(self):
        """Sync stop — best effort. Use stop_async() when in async context."""
        if not self._started:
            return
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            self._task = None
        clear_len = len(self._message) + 4
        sys.stderr.write("\r" + " " * clear_len + "\r")
        sys.stderr.flush()
        self._started = False

    def update(self, message: str):
        self._message = message

    @contextlib.contextmanager
    def __call__(self, message: str = "Thinking..."):
        self.start(message)
        try:
            yield
        finally:
            self.stop()
