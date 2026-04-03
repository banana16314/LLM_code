"""LLM client (OpenAI-compatible) — supports DashScope, OpenAI, and other providers."""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from ..config import Config, config as default_config
from .messages import (
    AssistantMessage, Message, StreamChunk, ToolCall, Usage,
)

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or default_config
        self._client = AsyncOpenAI(
            api_key=self.cfg.api_key,
            base_url=self.cfg.base_url,
        )
        # Accumulated usage across all calls in this client
        self.total_usage = Usage()

    # ── public API ──────────────────────────────────────────────────

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AssistantMessage | AsyncIterator[StreamChunk]:
        kwargs: dict = dict(
            model=self.cfg.model,
            messages=messages,
            max_tokens=self.cfg.max_tokens,
            temperature=self.cfg.temperature,
            stream=stream,
        )
        if tools:
            kwargs["tools"] = tools

        if stream:
            return self._stream(kwargs)
        else:
            return await self._complete(kwargs)

    # ── non-streaming ───────────────────────────────────────────────

    async def _complete(self, kwargs: dict) -> AssistantMessage:
        kwargs["stream"] = False
        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message

        # Extract usage
        call_usage = _extract_usage(resp.usage)
        self.total_usage = self.total_usage + call_usage

        tool_calls = []
        if msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=tc.function.arguments,
                ))

        result = AssistantMessage(
            content=msg.content or "",
            tool_calls=tool_calls,
        )
        return result

    # ── streaming ───────────────────────────────────────────────────

    async def _stream(self, kwargs: dict) -> AsyncIterator[StreamChunk]:
        kwargs["stream"] = True
        # Request usage info in streaming mode (OpenAI supports stream_options)
        kwargs["stream_options"] = {"include_usage": True}
        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception:
            # Some providers don't support stream_options — retry without
            kwargs.pop("stream_options", None)
            response = await self._client.chat.completions.create(**kwargs)

        # Accumulators
        tc_map: dict[int, dict] = {}  # index -> {id, name, arguments}
        finish_reason = ""
        call_usage = Usage()

        async for chunk in response:
            if not chunk.choices and hasattr(chunk, "usage") and chunk.usage:
                # Final usage-only chunk (OpenAI stream_options pattern)
                call_usage = _extract_usage(chunk.usage)
                continue

            delta = chunk.choices[0].delta if chunk.choices else None
            finish = chunk.choices[0].finish_reason if chunk.choices else None

            if delta is None:
                if finish:
                    finish_reason = finish
                continue

            # Text content
            if delta.content:
                yield StreamChunk(type="text", text=delta.content)

            # Tool calls (streamed incrementally)
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tc_map:
                        tc_map[idx] = {"id": "", "name": "", "arguments": ""}
                    if tc_delta.id:
                        tc_map[idx]["id"] = tc_delta.id
                    if tc_delta.function:
                        if tc_delta.function.name:
                            tc_map[idx]["name"] = tc_delta.function.name
                        if tc_delta.function.arguments:
                            tc_map[idx]["arguments"] += tc_delta.function.arguments

            if finish:
                finish_reason = finish
                if finish in ("stop", "tool_calls"):
                    break

        # Track usage
        self.total_usage = self.total_usage + call_usage

        # Emit completed tool calls
        for idx in sorted(tc_map):
            tc = tc_map[idx]
            yield StreamChunk(
                type="tool_call_start",
                tool_call=ToolCall(
                    id=tc["id"],
                    name=tc["name"],
                    arguments=tc["arguments"],
                ),
            )

        yield StreamChunk(
            type="done",
            finish_reason=finish_reason,
            usage=call_usage,
        )


def _extract_usage(usage) -> Usage:
    """Extract Usage from API response usage object."""
    if usage is None:
        return Usage()
    return Usage(
        prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
        completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
        total_tokens=getattr(usage, "total_tokens", 0) or 0,
    )
