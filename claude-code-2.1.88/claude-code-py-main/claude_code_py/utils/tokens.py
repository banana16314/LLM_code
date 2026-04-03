"""Token estimation utilities."""

from __future__ import annotations


def estimate_tokens(text: str | None) -> int:
    """Rough token estimation: ~0.3 tokens per character for mixed content."""
    if not text:
        return 0
    # A rough but fast heuristic
    return max(1, int(len(text) * 0.3))
