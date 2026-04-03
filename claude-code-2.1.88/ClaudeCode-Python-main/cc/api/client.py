# """Anthropic API client factory.

# Corresponds to TS: services/api/client.ts.
# """

# from __future__ import annotations

# import os

# import anthropic

# from cc.utils.errors import ConfigError


# def create_client(
#     api_key: str | None = None,
#     base_url: str | None = None,
# ) -> anthropic.AsyncAnthropic:
#     """Create an async Anthropic client.

#     Corresponds to TS: services/api/client.ts client creation.

#     Args:
#         api_key: API key. Falls back to ANTHROPIC_API_KEY env var.
#         base_url: Optional base URL override.

#     Returns:
#         Configured AsyncAnthropic client.

#     Raises:
#         ConfigError: If no API key is available.
#     """
#     resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
#     if not resolved_key:
#         raise ConfigError(
#             "No API key found. Set ANTHROPIC_API_KEY environment variable or pass api_key parameter."
#         )

#     if base_url:
#         return anthropic.AsyncAnthropic(api_key=resolved_key, base_url=base_url)
#     return anthropic.AsyncAnthropic(api_key=resolved_key)

"""OpenAI API client factory (OpenAI-compatible for vLLM).

Corresponds to TS: services/api/client.ts.
"""

from __future__ import annotations

import os

import openai

from cc.utils.errors import ConfigError


def create_client(
    api_key: str | None = None,
    base_url: str | None = None,
) -> openai.AsyncOpenAI:
    """Create an async OpenAI-compatible client.

    Corresponds to TS: services/api/client.ts client creation.

    Args:
        api_key: API key. Falls back to OPENAI_API_KEY or ANTHROPIC_API_KEY env var.
        base_url: Optional base URL override (e.g., http://localhost:8000/v1).

    Returns:
        Configured AsyncOpenAI client.

    Raises:
        ConfigError: If no API key is available.
    """
    # 兼容性处理：优先寻找 OPENAI_API_KEY，若无则回退到 ANTHROPIC_API_KEY
    resolved_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    
    # 对于本地 vLLM，如果未设置 Key，通常可以使用 "dummy-key"
    if not resolved_key:
        resolved_key = "sk-no-key-required"

    # 优先使用传入的 base_url，否则尝试从环境变量获取
    resolved_base_url = base_url or os.environ.get("OPENAI_BASE_URL") or os.environ.get("ANTHROPIC_BASE_URL")

    return openai.AsyncOpenAI(
        api_key=resolved_key,
        base_url=resolved_base_url,
    )