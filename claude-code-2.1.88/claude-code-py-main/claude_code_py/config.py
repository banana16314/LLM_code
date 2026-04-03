"""Global configuration."""

import os
from dataclasses import dataclass, field


# Pre-configured providers
PROVIDERS = {
    "dashscope": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "env_key": "DASHSCOPE_API_KEY",
        "default_model": "qwen-plus-latest",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "env_key": "OPENAI_API_KEY",
        "default_model": "gpt-4o",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com/v1",
        "env_key": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-20250514",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "env_key": "DEEPSEEK_API_KEY",
        "default_model": "deepseek-chat",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_key": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-4",
    },
}


@dataclass
class Config:
    # LLM
    provider: str = "dashscope"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    max_tokens: int = 8192
    temperature: float = 0.7

    # Context
    max_context_tokens: int = 120_000
    compact_threshold: float = 0.8

    # Tools
    bash_timeout: int = 120
    max_file_read_lines: int = 2000

    # Permissions
    default_permission: str = "ask"

    # UI
    stream: bool = True

    # Paths
    claude_dir: str = field(default_factory=lambda: os.path.expanduser("~/.claude"))
    cwd: str = field(default_factory=os.getcwd)

    def __post_init__(self):
        self.apply_provider(self.provider)

    def apply_provider(self, provider: str):
        """Apply provider defaults (only fills in blanks, won't override explicit values)."""
        provider = provider.lower()
        if provider not in PROVIDERS:
            return
        info = PROVIDERS[provider]
        self.provider = provider
        if not self.base_url:
            self.base_url = info["base_url"]
        if not self.model:
            self.model = info["default_model"]
        if not self.api_key:
            self.api_key = os.environ.get(info["env_key"], "")
        # Fallback: if no key found for this provider, try to auto-detect provider from env
        if not self.api_key:
            for prov_name, prov_info in PROVIDERS.items():
                val = os.environ.get(prov_info["env_key"], "")
                if val:
                    self.api_key = val
                    # Also switch to that provider's base_url and model if not explicitly set
                    if self.base_url == info["base_url"]:
                        self.base_url = prov_info["base_url"]
                    if self.model == info["default_model"]:
                        self.model = prov_info["default_model"]
                    self.provider = prov_name
                    break


# Global singleton
config = Config()
