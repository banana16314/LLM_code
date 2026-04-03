"""Application state management."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from ..llm.messages import (
    AssistantMessage, Message, SystemMessage, ToolResultMessage, UserMessage,
)


@dataclass
class Task:
    id: str
    subject: str
    description: str = ""
    status: str = "pending"  # pending / in_progress / completed
    owner: str = ""
    blocks: list[str] = field(default_factory=list)
    blocked_by: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AppState:
    cwd: str = ""
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    messages: list[Message] = field(default_factory=list)
    tasks: dict[str, Task] = field(default_factory=dict)
    plan_mode: bool = False
    plan_file: str | None = None
    _task_counter: int = 0

    # File read tracking: file_path -> mtime at read time
    _read_files: dict[str, float] = field(default_factory=dict)

    # ── Message helpers ─────────────────────────────────────────────

    def add_system(self, content: str):
        self.messages.insert(0, SystemMessage(content=content))

    def set_system(self, content: str):
        """Replace system message at index 0 (or insert if none)."""
        if self.messages and self.messages[0].role == "system":
            self.messages[0] = SystemMessage(content=content)
        else:
            self.messages.insert(0, SystemMessage(content=content))

    def add_user(self, content: str):
        self.messages.append(UserMessage(content=content))

    def add_assistant(self, msg: AssistantMessage):
        self.messages.append(msg)

    def add_tool_result(self, tool_call_id: str, name: str, result):
        self.messages.append(ToolResultMessage(
            content=result.text,
            tool_call_id=tool_call_id,
            name=name,
        ))

    def mark_file_read(self, file_path: str, mtime: float):
        """Track that a file was read (for edit validation)."""
        self._read_files[file_path] = mtime

    def was_file_read(self, file_path: str) -> bool:
        """Check if a file was previously read in this session."""
        return file_path in self._read_files

    def get_api_messages(self) -> list[dict]:
        """Convert messages to API format with normalization.

        - Merges consecutive user messages into a single turn
        - Ensures valid message alternation for APIs that require it
        """
        raw = [m.to_api() for m in self.messages]
        return _normalize_messages(raw)

    def clear_conversation(self):
        """Clear all messages except system."""
        sys_msg = None
        if self.messages and self.messages[0].role == "system":
            sys_msg = self.messages[0]
        self.messages.clear()
        if sys_msg:
            self.messages.append(sys_msg)
        self._read_files.clear()

    # ── Task helpers ────────────────────────────────────────────────

    def create_task(self, subject: str, description: str = "") -> Task:
        self._task_counter += 1
        tid = str(self._task_counter)
        task = Task(id=tid, subject=subject, description=description)
        self.tasks[tid] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        return self.tasks.get(task_id)

    def list_tasks(self) -> list[Task]:
        return list(self.tasks.values())


def _normalize_messages(messages: list[dict]) -> list[dict]:
    """Normalize messages for API consumption.

    - Merges consecutive messages with the same role (except tool messages)
    - Preserves system message at position 0
    - Ensures tool_result messages follow assistant messages with tool_calls
    """
    if not messages:
        return messages

    result = []
    for msg in messages:
        role = msg.get("role", "")

        # Tool messages are never merged — they pair with specific tool_call_ids
        if role == "tool":
            result.append(msg)
            continue

        # Merge consecutive user messages into one
        if result and result[-1].get("role") == role and role == "user":
            prev = result[-1]
            prev_content = prev.get("content", "")
            new_content = msg.get("content", "")
            # Both strings: join with newline
            if isinstance(prev_content, str) and isinstance(new_content, str):
                prev["content"] = prev_content + "\n\n" + new_content
            else:
                # Mixed types: convert to string
                prev["content"] = str(prev_content) + "\n\n" + str(new_content)
            continue

        result.append(msg)

    return result
