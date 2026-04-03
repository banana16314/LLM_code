"""Built-in slash commands — expanded to match Claude Code."""

from __future__ import annotations

import os
import sys
from .registry import CommandRegistry


def register_builtins(registry: CommandRegistry, app_context: dict):
    """Register all built-in commands."""

    async def cmd_help(**kwargs):
        cmds = registry.list_commands()
        lines = ["[bold]Available commands:[/]"]
        for name, desc in cmds:
            lines.append(f"  [cyan]/{name:14s}[/] {desc}")
        lines.append("\n[dim]Escape+Enter for newline, Enter to send[/]")
        return "\n".join(lines)

    async def cmd_exit(**kwargs):
        renderer = app_context.get("renderer")
        if renderer:
            renderer.info("Goodbye!")
        raise SystemExit(0)

    async def cmd_clear(**kwargs):
        state = app_context.get("state")
        if state:
            state.clear_conversation()
            # Re-apply system prompt
            from ..core.context import build_system_prompt
            system_prompt = build_system_prompt(state.cwd)
            state.set_system(system_prompt)
        renderer = app_context.get("renderer")
        if renderer:
            renderer.console.clear()
        return "Conversation Cleared."

    async def cmd_compact(**kwargs):
        state = app_context.get("state")
        llm = app_context.get("llm_client")
        if state and llm:
            from ..core.compact import compact_messages
            before = len(state.messages)
            state.messages = await compact_messages(state.messages, llm, keep_recent=4)
            after = len(state.messages)
            return f"Compacted: {before} → {after} messages"
        return "Nothing to compact."

    async def cmd_model(**kwargs):
        """Show/switch model (e.g. /model qwen-max)."""
        config = app_context.get("config")
        args_str = kwargs.get("args", "").strip()
        if args_str:
            config.model = args_str
            return f"Model switched to: {args_str}"
        return f"Current model: {config.model} (provider: {config.provider})"

    async def cmd_provider(**kwargs):
        """Switch provider (e.g. /provider openai)."""
        config = app_context.get("config")
        from ..config import PROVIDERS
        args_str = kwargs.get("args", "").strip()
        if args_str:
            if args_str.lower() not in PROVIDERS:
                return f"Unknown provider: {args_str}. Available: {', '.join(PROVIDERS.keys())}"
            config.base_url = ""
            config.model = ""
            config.api_key = ""
            config.apply_provider(args_str.lower())
            return f"Switched to {config.provider}: model={config.model}, base_url={config.base_url}"
        lines = [f"Current: {config.provider} (model: {config.model})", "", "Available providers:"]
        for name, info in PROVIDERS.items():
            marker = " ←" if name == config.provider else ""
            lines.append(f"  {name:12s} {info['default_model']:30s} {info['env_key']}{marker}")
        return "\n".join(lines)

    async def cmd_history(**kwargs):
        state = app_context.get("state")
        if not state:
            return "No state."
        lines = []
        for m in state.messages:
            role = m.role
            content = m.content if isinstance(m.content, str) else "(structured)"
            preview = content[:100].replace("\n", " ")
            lines.append(f"[{role:10s}] {preview}")
        return "\n".join(lines[-20:])

    async def cmd_config(**kwargs):
        config = app_context.get("config")
        return (
            f"model:       {config.model}\n"
            f"base_url:    {config.base_url}\n"
            f"max_tokens:  {config.max_tokens}\n"
            f"temperature: {config.temperature}\n"
            f"stream:      {config.stream}\n"
            f"cwd:         {config.cwd}"
        )

    async def cmd_cost(**kwargs):
        """Show token usage from API responses + estimate for current context."""
        llm = app_context.get("llm_client")
        state = app_context.get("state")
        lines = []

        # Real usage from API
        if llm and hasattr(llm, "total_usage"):
            u = llm.total_usage
            lines.append(f"API usage (actual):  {u.prompt_tokens:,} in + {u.completion_tokens:,} out = {u.total_tokens:,} total")

        # Estimate for current context
        if state:
            from ..utils.tokens import estimate_tokens
            est = sum(
                estimate_tokens(m.content if isinstance(m.content, str) else str(m.content))
                for m in state.messages
            )
            lines.append(f"Context estimate:    ~{est:,} tokens in {len(state.messages)} messages")

        return "\n".join(lines) if lines else "No usage data."

    async def cmd_permissions(**kwargs):
        """Show current permission rules."""
        from ..core.permissions import DEFAULT_RULES
        lines = ["Current permission rules:"]
        for tool, perm in sorted(DEFAULT_RULES.items(), key=lambda x: x[0]):
            lines.append(f"  {tool:20s} {perm.value}")
        return "\n".join(lines)

    async def cmd_tools(**kwargs):
        """List available tools."""
        state = app_context.get("state")
        tools = app_context.get("tool_registry")
        if tools:
            lines = [f"Available tools ({len(tools.list_tools()):d}):"]
            for t in tools.list_tools():
                lines.append(f"  {t.name:20s} {t.description[:60]}")
            return "\n".join(lines)
        return "No tools loaded."

    # Register all commands
    registry.register("help", cmd_help, "Show available commands")
    registry.register("exit", cmd_exit, "Exit the application")
    registry.register("quit", cmd_exit, "Exit the application")
    registry.register("clear", cmd_clear, "Clear conversation and screen")
    registry.register("compact", cmd_compact, "Compact message history to save context")
    registry.register("model", cmd_model, "Show/switch model (e.g. /model qwen-max)")
    registry.register("provider", cmd_provider, "Switch LLM provider (e.g. /provider openai)")
    registry.register("history", cmd_history, "Show recent message history")
    registry.register("config", cmd_config, "Show current configuration")
    registry.register("cost", cmd_cost, "Show estimated token usage")
    registry.register("permissions", cmd_permissions, "Show permission rules")
    registry.register("tools", cmd_tools, "List available tools")
