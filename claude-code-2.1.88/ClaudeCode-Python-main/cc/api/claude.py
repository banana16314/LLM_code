# """Streaming API interaction with Claude.

# Corresponds to TS: services/api/claude.ts — queryModelWithStreaming(),
# stream event parsing, and response assembly.
# """

# from __future__ import annotations

# import json
# import logging
# from typing import TYPE_CHECKING, Any

# import anthropic

# from cc.core.events import (
#     ErrorEvent,
#     QueryEvent,
#     TextDelta,
#     ThinkingDelta,
#     ToolUseStart,
#     TurnComplete,
# )
# from cc.models.content_blocks import (
#     AssistantContentBlock,
#     RedactedThinkingBlock,
#     TextBlock,
#     ThinkingBlock,
#     ToolUseBlock,
# )
# from cc.models.messages import Usage

# if TYPE_CHECKING:
#     from collections.abc import AsyncIterator

# logger = logging.getLogger(__name__)


# async def stream_response(
#     client: anthropic.AsyncAnthropic,
#     *,
#     messages: list[dict[str, Any]],
#     system: str | list[dict[str, Any]],
#     tools: list[dict[str, Any]] | None = None,
#     model: str = "claude-sonnet-4-20250514",
#     max_tokens: int = 16384,
#     thinking: dict[str, Any] | None = None,
# ) -> AsyncIterator[QueryEvent]:
#     """Stream a response from the Claude API and yield QueryEvents.

#     Corresponds to TS: services/api/claude.ts queryModelWithStreaming().

#     Uses the raw stream API to process SSE events directly, avoiding
#     type union issues with the high-level stream wrapper.

#     Yields:
#         QueryEvent instances (TextDelta, ToolUseStart, etc.).
#     """
#     # Build request parameters
#     params: dict[str, Any] = {
#         "model": model,
#         "max_tokens": max_tokens,
#         "messages": messages,
#         "system": system,
#     }

#     if tools:
#         params["tools"] = tools

#     if thinking:
#         params["thinking"] = thinking
#     else:
#         params["temperature"] = 1.0

#     # State for accumulating the streaming response
#     content_blocks: dict[int, dict[str, Any]] = {}
#     final_content: list[AssistantContentBlock] = []
#     usage = Usage()
#     stop_reason = "end_turn"

#     try:
#         async with client.messages.stream(**params) as stream:
#             async for event in stream:
#                 event_type = getattr(event, "type", "")

#                 if event_type == "message_start":
#                     msg = getattr(event, "message", None)
#                     if msg:
#                         msg_usage = getattr(msg, "usage", None)
#                         if msg_usage:
#                             usage.input_tokens = getattr(msg_usage, "input_tokens", 0)
#                             usage.cache_creation_input_tokens = getattr(
#                                 msg_usage, "cache_creation_input_tokens", 0
#                             )
#                             usage.cache_read_input_tokens = getattr(
#                                 msg_usage, "cache_read_input_tokens", 0
#                             )

#                 elif event_type == "content_block_start":
#                     idx: int = getattr(event, "index", 0)
#                     cb = getattr(event, "content_block", None)
#                     if cb is None:
#                         continue
#                     block_type: str = getattr(cb, "type", "")

#                     if block_type == "text":
#                         content_blocks[idx] = {"type": "text", "text": ""}
#                     elif block_type == "tool_use":
#                         content_blocks[idx] = {
#                             "type": "tool_use",
#                             "id": getattr(cb, "id", ""),
#                             "name": getattr(cb, "name", ""),
#                             "input_json": "",
#                         }
#                     elif block_type == "thinking":
#                         content_blocks[idx] = {"type": "thinking", "thinking": ""}
#                     elif block_type == "redacted_thinking":
#                         content_blocks[idx] = {
#                             "type": "redacted_thinking",
#                             "data": getattr(cb, "data", ""),
#                         }

#                 elif event_type == "content_block_delta":
#                     idx = getattr(event, "index", 0)
#                     delta = getattr(event, "delta", None)
#                     if delta is None or idx not in content_blocks:
#                         continue

#                     block = content_blocks[idx]
#                     delta_type: str = getattr(delta, "type", "")

#                     if delta_type == "text_delta":
#                         text: str = getattr(delta, "text", "")
#                         block["text"] += text
#                         yield TextDelta(text=text)

#                     elif delta_type == "input_json_delta":
#                         block["input_json"] += getattr(delta, "partial_json", "")

#                     elif delta_type == "thinking_delta":
#                         thinking_text: str = getattr(delta, "thinking", "")
#                         block["thinking"] += thinking_text
#                         yield ThinkingDelta(text=thinking_text)

#                 elif event_type == "content_block_stop":
#                     idx = getattr(event, "index", 0)
#                     if idx not in content_blocks:
#                         continue

#                     block = content_blocks[idx]
#                     finished_block: AssistantContentBlock

#                     if block["type"] == "text":
#                         finished_block = TextBlock(text=block["text"])
#                     elif block["type"] == "tool_use":
#                         try:
#                             parsed_input = json.loads(block["input_json"]) if block["input_json"] else {}
#                         except json.JSONDecodeError:
#                             logger.warning("Failed to parse tool input JSON: %s", block["input_json"][:200])
#                             parsed_input = {}

#                         finished_block = ToolUseBlock(
#                             id=block["id"],
#                             name=block["name"],
#                             input=parsed_input,
#                         )
#                         yield ToolUseStart(
#                             tool_name=block["name"],
#                             tool_id=block["id"],
#                             input=parsed_input,
#                         )
#                     elif block["type"] == "thinking":
#                         finished_block = ThinkingBlock(thinking=block["thinking"])
#                     elif block["type"] == "redacted_thinking":
#                         finished_block = RedactedThinkingBlock(data=block.get("data", ""))
#                     else:
#                         continue

#                     final_content.append(finished_block)

#                 elif event_type == "message_delta":
#                     delta = getattr(event, "delta", None)
#                     if delta:
#                         stop_reason = getattr(delta, "stop_reason", "end_turn") or "end_turn"
#                     evt_usage = getattr(event, "usage", None)
#                     if evt_usage:
#                         usage.output_tokens = getattr(evt_usage, "output_tokens", 0)

#     except anthropic.APIStatusError as e:
#         error_type = ""
#         if hasattr(e, "body") and isinstance(e.body, dict):
#             error_info = e.body.get("error", {})
#             if isinstance(error_info, dict):
#                 error_type = error_info.get("type", "")

#         yield ErrorEvent(
#             message=str(e),
#             is_recoverable=e.status_code in (429, 529) or error_type == "overloaded_error",
#         )
#         return

#     except anthropic.APIConnectionError as e:
#         yield ErrorEvent(message=f"Connection error: {e}", is_recoverable=True)
#         return

#     yield TurnComplete(stop_reason=stop_reason, usage=usage)
"""Streaming API interaction with OpenAI (vLLM/Direct).

Converted from Anthropic event-based stream to OpenAI chunk-based stream.
Includes payload translation from Anthropic schema to OpenAI schema.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

import openai

from cc.core.events import (
    ErrorEvent,
    QueryEvent,
    TextDelta,
    ThinkingDelta,
    ToolUseStart,
    TurnComplete,
)
from cc.models.content_blocks import (
    AssistantContentBlock,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
)
from cc.models.messages import Usage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)


def _convert_tools_to_openai(anthropic_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 Anthropic 的 tools 格式转换为 OpenAI 格式"""
    openai_tools = []
    for t in anthropic_tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "parameters": t.get("input_schema", {}) # 关键转换：input_schema -> parameters
            }
        })
    return openai_tools


def _convert_messages_to_openai(anthropic_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 Anthropic 的多模态/工具调用消息转换为 OpenAI 格式"""
    openai_msgs = []
    for m in anthropic_messages:
        role = m["role"]
        content = m.get("content", "")

        # 1. 纯文本消息
        if isinstance(content, str):
            openai_msgs.append({"role": role, "content": content})
            continue

        # 2. 包含 block 的复杂消息 (如工具调用)
        text_content = ""
        tool_calls = []

        for block in content:
            b_type = block.get("type", "")
            
            if b_type == "text":
                text_content += block.get("text", "") + "\n"
            
            elif b_type == "tool_use":
                # Anthropic 的 Assistant 发起工具调用
                tool_calls.append({
                    "id": block.get("id"),
                    "type": "function",
                    "function": {
                        "name": block.get("name"),
                        "arguments": json.dumps(block.get("input", {}))
                    }
                })
            
            elif b_type == "tool_result":
                # Anthropic 的 User 返回工具结果 -> 拆分为 OpenAI 的 tool 角色消息
                # 注意：OpenAI 要求 tool result 是一条独立的消息
                result_content = block.get("content", "")
                if isinstance(result_content, list):
                    # 如果结果是复杂的 block，简化为字符串
                    result_content = json.dumps(result_content)
                    
                openai_msgs.append({
                    "role": "tool",
                    "tool_call_id": block.get("tool_use_id"),
                    "content": str(result_content)
                })

        # 组装当前的 Assistant 或 User 消息
        text_content = text_content.strip()
        if role == "assistant" and (text_content or tool_calls):
            msg_obj: dict[str, Any] = {"role": "assistant", "content": text_content}
            if tool_calls:
                msg_obj["tool_calls"] = tool_calls
            openai_msgs.append(msg_obj)
        elif role == "user" and text_content:
            openai_msgs.append({"role": "user", "content": text_content})

    return openai_msgs


async def stream_response(
    client: openai.AsyncOpenAI,
    *,
    messages: list[dict[str, Any]],
    system: str | list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    model: str = "qwen3.5-27b-fp8",
    max_tokens: int = 16384,
    thinking: dict[str, Any] | None = None,
) -> AsyncIterator[QueryEvent]:
    """使用 OpenAI SDK 获取流式响应并转换成内部 QueryEvent 格式。"""

    formatted_messages = []
    
    # 1. 适配 System Prompt (Anthropic 的 text block 字段名是 'text' 而不是 'content')
    if system:
        if isinstance(system, str):
            formatted_messages.append({"role": "system", "content": system})
        else:
            for s in system:
                # 修复点：Anthropic 的 system block 通常是 {"type": "text", "text": "..."}
                formatted_messages.append({"role": "system", "content": s.get("text", "")})
                
    # 2. 转换并合并历史消息
    formatted_messages.extend(_convert_messages_to_openai(messages))

    # 3. 构建请求参数
    params: dict[str, Any] = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": formatted_messages,
        "stream": True,
        "stream_options": {"include_usage": True}, 
    }

    # 4. 转换 Tools 格式
    if tools:
        params["tools"] = _convert_tools_to_openai(tools)

    if thinking:
        params["extra_body"] = {"reasoning_format": "parsed"}

    tool_calls_buffer: dict[int, dict[str, Any]] = {}
    usage = Usage()
    stop_reason = "stop"

    try:
        stream = await client.chat.completions.create(**params)

        async for chunk in stream:
            if hasattr(chunk, "usage") and chunk.usage:
                usage.input_tokens = chunk.usage.prompt_tokens
                usage.output_tokens = chunk.usage.completion_tokens
                continue

            if not chunk.choices:
                continue
            
            delta = chunk.choices[0].delta
            
            if chunk.choices[0].finish_reason:
                stop_reason = chunk.choices[0].finish_reason

            reasoning = getattr(delta, "reasoning_content", None)
            if reasoning:
                yield ThinkingDelta(text=reasoning)

            if delta.content:
                yield TextDelta(text=delta.content)

            # 5. 增强的 Tool Calls 解析（防空指针保护）
            if delta.tool_calls:
                for tc_delta in delta.tool_calls:
                    idx = tc_delta.index
                    if idx not in tool_calls_buffer:
                        # 确保 id 存在，有些代理在后续 chunk 中会省略 id 和 name
                        tool_calls_buffer[idx] = {
                            "id": tc_delta.id or f"call_unknown_{idx}",
                            "name": getattr(tc_delta.function, "name", "") if tc_delta.function else "",
                            "arguments": ""
                        }
                    
                    if tc_delta.function and tc_delta.function.arguments:
                        tool_calls_buffer[idx]["arguments"] += tc_delta.function.arguments

    except openai.APIStatusError as e:
        yield ErrorEvent(message=str(e), is_recoverable=e.status_code in (429, 502, 503))
        return
    except Exception as e:
        logger.exception("OpenAI Stream Error")
        yield ErrorEvent(message=f"Unexpected error: {str(e)}", is_recoverable=False)
        return

    # 6. 流结束后结算
    for idx in sorted(tool_calls_buffer.keys()):
        buf = tool_calls_buffer[idx]
        try:
            parsed_input = json.loads(buf["arguments"]) if buf["arguments"] else {}
        except json.JSONDecodeError:
            logger.error("Failed to parse tool JSON: %s", buf["arguments"])
            parsed_input = {}

        yield ToolUseStart(
            tool_name=buf["name"],
            tool_id=buf["id"],
            input=parsed_input,
        )

    yield TurnComplete(stop_reason=stop_reason, usage=usage)