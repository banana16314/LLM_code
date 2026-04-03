"""Message types for LLM communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


# ── Conversation messages ──────────────────────────────────────────

@dataclass
class Message:
    role: str
    content: str | list[dict] = ""

    def to_api(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class SystemMessage(Message):
    role: str = "system"


@dataclass
class UserMessage(Message):
    role: str = "user"


@dataclass
class AssistantMessage(Message):
    role: str = "assistant"
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_api(self) -> dict:
        d: dict[str, Any] = {"role": "assistant", "content": self.content or None}
        if self.tool_calls:
            d["tool_calls"] = [tc.to_api() for tc in self.tool_calls]
        return d


@dataclass
class ToolResultMessage(Message):
    """Carries a tool result back to the API."""
    role: str = "tool"
    tool_call_id: str = ""
    name: str = ""

    def to_api(self) -> dict:
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "name": self.name,
            "content": self.content if isinstance(self.content, str) else str(self.content),
        }


# ── Tool call / result ─────────────────────────────────────────────

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: str  # raw JSON string from API

    def to_api(self) -> dict:
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass
class ToolResult:
    output: str = ""
    error: str = ""
    is_error: bool = False

    @property
    def text(self) -> str:
        return self.error if self.is_error else self.output


# ── Usage tracking ────────────────────────────────────────────────

@dataclass
class Usage:
    """Token usage from a single API call."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
        )


# ── Streaming ──────────────────────────────────────────────────────

@dataclass
class StreamChunk:
    type: Literal["text", "tool_call_start", "tool_call_delta", "done"]
    text: str = ""
    tool_call: ToolCall | None = None
    # For incremental tool call argument streaming
    tool_call_index: int = 0
    tool_call_id: str = ""
    tool_call_name: str = ""
    tool_call_arguments_delta: str = ""
    # Finish reason: "stop", "tool_calls", "length", etc.
    finish_reason: str = ""
    # Usage (populated on "done" chunk)
    usage: Usage | None = None
