"""Message compaction — mirrors Claude Code autoCompact.ts."""

from __future__ import annotations

import logging
from ..llm.messages import AssistantMessage, Message, SystemMessage, UserMessage
from ..utils.tokens import estimate_tokens

log = logging.getLogger(__name__)

# Circuit breaker: stop after N consecutive failures
MAX_COMPACT_FAILURES = 3


class CompactionState:
    """Tracks compaction state to prevent thrashing."""
    def __init__(self):
        self.consecutive_failures = 0
        self.total_compactions = 0


_state = CompactionState()


async def compact_messages(
    messages: list[Message],
    llm_client,
    max_tokens: int = 120_000,
    keep_recent: int = 6,
) -> list[Message]:
    """Compact messages if total tokens approach context limit.

    Strategy from source: threshold = context_window - 13K tokens.
    Reserve 20K for output, trigger at 80% of remaining.
    Circuit breaker: stop after 3 consecutive failures.
    """
    # Circuit breaker
    if _state.consecutive_failures >= MAX_COMPACT_FAILURES:
        return messages

    total = sum(
        estimate_tokens(m.content if isinstance(m.content, str) else str(m.content))
        for m in messages
    )

    # Threshold: context_window - 13K (matching source)
    threshold = max_tokens - 13_000
    if total < threshold:
        return messages

    log.info(f"Compacting: {total} estimated tokens, threshold {threshold}")

    # Separate system message
    system_msgs = []
    rest = messages
    if messages and messages[0].role == "system":
        system_msgs = [messages[0]]
        rest = messages[1:]

    if len(rest) <= keep_recent:
        return messages  # Nothing to compact

    to_summarize = rest[:-keep_recent]
    recent = rest[-keep_recent:]

    # Build summary of old messages
    summary_text = _build_summary_input(to_summarize)

    try:
        result = await llm_client.chat(
            messages=[
                {"role": "system", "content": (
                    "Summarize this conversation history concisely. "
                    "Focus on: decisions made, code changes performed, current task state, "
                    "and any important context. Be brief but complete."
                )},
                {"role": "user", "content": summary_text},
            ],
            stream=False,
        )
        summary_content = (
            f"[Conversation summary — {len(to_summarize)} messages compacted]\n\n"
            f"{result.content}"
        )
        _state.consecutive_failures = 0
        _state.total_compactions += 1
        log.info(f"Compaction #{_state.total_compactions} successful")

    except Exception as e:
        log.warning(f"Compaction failed: {e}")
        _state.consecutive_failures += 1
        # Fallback: simple truncation summary
        summary_content = (
            f"[{len(to_summarize)} earlier messages were compacted to save context. "
            f"Compaction attempt failed: {e}]"
        )

    summary_msg = UserMessage(content=summary_content)
    return system_msgs + [summary_msg] + recent


def _build_summary_input(messages: list[Message], max_chars: int = 50_000) -> str:
    """Build text for the summarization prompt."""
    parts = []
    total = 0
    for m in messages:
        content = m.content if isinstance(m.content, str) else str(m.content)
        # Truncate individual messages
        if len(content) > 2000:
            content = content[:2000] + "..."
        line = f"[{m.role}]: {content}"
        if total + len(line) > max_chars:
            parts.append(f"... ({len(messages) - len(parts)} more messages truncated)")
            break
        parts.append(line)
        total += len(line)
    return "\n\n".join(parts)
