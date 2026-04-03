# """Token estimation utilities.

# Corresponds to TS: services/tokenEstimation.ts.
# """

# from __future__ import annotations

# BYTES_PER_TOKEN = 4
# JSON_BYTES_PER_TOKEN = 2


# def estimate_tokens(text: str, bytes_per_token: int = BYTES_PER_TOKEN) -> int:
#     """Rough token count estimation.

#     Corresponds to TS: services/tokenEstimation.ts roughTokenCountEstimation().

#     Args:
#         text: Input text to estimate.
#         bytes_per_token: Bytes per token ratio (default 4, use 2 for JSON).

#     Returns:
#         Estimated token count.
#     """
#     if not text:
#         return 0
#     return max(1, len(text.encode("utf-8")) // bytes_per_token)


# async def count_tokens_api(
#     client: object,
#     messages: list[dict[str, object]],
#     model: str = "claude-sonnet-4-20250514",
# ) -> int:
#     """Count tokens using the Anthropic API's count_tokens endpoint.

#     Corresponds to TS: services/tokenEstimation.ts countMessagesTokensWithAPI().
#     """
#     import anthropic

#     if not isinstance(client, anthropic.AsyncAnthropic):
#         raise TypeError("client must be an AsyncAnthropic instance")

#     result = await client.messages.count_tokens(
#         model=model,
#         messages=messages,  # type: ignore[arg-type]
#     )
#     return result.input_tokens


# def estimate_messages_tokens(messages: list[dict[str, object]]) -> int:
#     """Estimate token count for a list of API messages.

#     Args:
#         messages: API-formatted messages.

#     Returns:
#         Estimated total token count.
#     """
#     import json

#     total = 0
#     for msg in messages:
#         content = msg.get("content", "")
#         if isinstance(content, str):
#             total += estimate_tokens(content)
#         else:
#             total += estimate_tokens(json.dumps(content), bytes_per_token=JSON_BYTES_PER_TOKEN)
#     return total

"""Token estimation utilities for OpenAI.

Corresponds to TS: services/tokenEstimation.ts.
Adapted for OpenAI compatibility using tiktoken.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

BYTES_PER_TOKEN = 4
JSON_BYTES_PER_TOKEN = 2


def estimate_tokens(text: str, bytes_per_token: int = BYTES_PER_TOKEN) -> int:
    """粗略的 Token 计数估算。"""
    if not text:
        return 0
    # 简单的字节除法估算
    return max(1, len(text.encode("utf-8")) // bytes_per_token)


async def count_tokens_api(
    client: object,
    messages: list[dict[str, Any]],
    model: str = "gpt-4o", # 对应你本地 vLLM 映射的模型名
) -> int:
    """使用 tiktoken 在本地精确计算 Token 数量。
    
    注意：OpenAI API 没有专门的 count_tokens 接口，
    因此这里改为使用本地库 tiktoken 进行离线计算。
    """
    import tiktoken

    try:
        # 尝试获取对应模型的编码器，如果找不到则回退到 cl100k_base (GPT-4 常用)
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.warning(f"Model {model} not found in tiktoken, falling back to cl100k_base.")
            encoding = tiktoken.get_encoding("cl100k_base")

        num_tokens = 0
        for message in messages:
            # 每条消息都有一定的格式开销 (role, name, content)
            # 对于 gpt-4 架构，大约是每条消息 3-4 个 token
            num_tokens += 3 
            for key, value in message.items():
                if isinstance(value, str):
                    num_tokens += len(encoding.encode(value))
                elif value:
                    import json
                    num_tokens += len(encoding.encode(json.dumps(value)))
        
        num_tokens += 3  # 助手回答的预留开销
        return num_tokens

    except Exception as e:
        logger.error(f"Error counting tokens with tiktoken: {e}")
        # 如果 tiktoken 报错，回退到粗略估算
        return estimate_messages_tokens(messages)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """估算一组 API 消息的总 Token 数。"""
    import json

    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        else:
            # 对于非字符串内容（如工具调用结果），假设其密度更高
            total += estimate_tokens(json.dumps(content), bytes_per_token=JSON_BYTES_PER_TOKEN)
    return total