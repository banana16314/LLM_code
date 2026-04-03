"""Claude Code Python — main entry point."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from claude_code_py.config import Config, config
from claude_code_py.llm.client import LLMClient
from claude_code_py.core.tool import ToolRegistry
from claude_code_py.core.permissions import PermissionManager
from claude_code_py.core.query_loop import QueryLoop
from claude_code_py.core.state import AppState
from claude_code_py.core.context import build_system_prompt
from claude_code_py.tools import register_all
from claude_code_py.tools.task_tools import set_app_state
from claude_code_py.commands.registry import CommandRegistry
from claude_code_py.commands.builtins import register_builtins
from claude_code_py.ui.renderer import Renderer
from claude_code_py.ui.input_handler import InputHandler
from claude_code_py.ui.spinner import Spinner


def parse_args():
    from claude_code_py.config import PROVIDERS
    providers = ", ".join(PROVIDERS.keys())
    parser = argparse.ArgumentParser(description="Claude Code (Python)")
    parser.add_argument("--provider", default=None, help=f"LLM provider ({providers})")
    parser.add_argument("--model", default=None, help="Model name")
    parser.add_argument("--api-key", default=None, help="API key")
    parser.add_argument("--base-url", default=None, help="API base URL")
    parser.add_argument("--max-tokens", type=int, default=None, help="Max tokens")
    parser.add_argument("--temperature", type=float, default=None, help="Temperature")
    parser.add_argument("--no-stream", action="store_true", help="Disable streaming")
    parser.add_argument("-y", "--yes", action="store_true", help="Auto-approve all tool calls (bypass permissions)")
    parser.add_argument("-p", "--prompt", default=None, help="One-shot prompt (non-interactive)")
    return parser.parse_args()


async def handle_command(
    cmd_text: str,
    cmd_registry: CommandRegistry,
    renderer: Renderer,
) -> bool:
    """Handle a slash command. Returns True if handled."""
    parts = cmd_text.strip().split(None, 1)
    cmd_name = parts[0].lstrip("/")
    cmd_args = parts[1] if len(parts) > 1 else ""

    cmd_info = cmd_registry.get(cmd_name)
    if not cmd_info:
        renderer.warning(f"Unknown command: /{cmd_name}. Type /help for available commands.")
        return True

    result = await cmd_info["handler"](args=cmd_args)
    if result:
        renderer.console.print(result)
    return True


async def run_query(
    user_input: str,
    state: AppState,
    query_loop: QueryLoop,
    renderer: Renderer,
    spinner: Spinner,
):
    """Run a single query through the LLM loop."""
    state.add_user(user_input)

    spinner.start("Thinking...")
    first_chunk = True

    try:
        async for chunk in query_loop.run(state):
            if first_chunk:
                await spinner.stop_async()
                sys.stdout.write("\n")
                sys.stdout.flush()
                first_chunk = False
            sys.stdout.write(chunk)
            sys.stdout.flush()
    except KeyboardInterrupt:
        await spinner.stop_async()
        renderer.warning("\nInterrupted.")
    except Exception as e:
        await spinner.stop_async()
        import traceback
        renderer.error(f"\nError: {e}")
        traceback.print_exc()
    finally:
        await spinner.stop_async()
        if not first_chunk:
            sys.stdout.write("\n")
            sys.stdout.flush()


async def interactive_loop(
    state: AppState,
    query_loop: QueryLoop,
    cmd_registry: CommandRegistry,
    renderer: Renderer,
    input_handler: InputHandler,
    spinner: Spinner,
):
    """Main interactive REPL loop."""
    renderer.print_welcome(config.model, state.cwd)

    while True:
        try:
            user_input = await input_handler.get_input()
        except (EOFError, KeyboardInterrupt):
            renderer.info("\nGoodbye!")
            break

        if not user_input:
            continue

        # Handle slash commands: /word pattern only, not filesystem paths like /home/...
        if user_input.startswith("/"):
            # Extract the first "word" after /
            first_token = user_input.split()[0]  # e.g. "/help" or "/home/user/..."
            cmd_name = first_token.lstrip("/")
            # It's a command only if the token has no path separators (no second /)
            if "/" not in cmd_name and cmd_name:
                try:
                    await handle_command(user_input, cmd_registry, renderer)
                except SystemExit:
                    return
                continue

        # Normal query
        await run_query(user_input, state, query_loop, renderer, spinner)


async def one_shot(prompt: str, state: AppState, query_loop: QueryLoop, renderer: Renderer, spinner: Spinner):
    """Run a single prompt and exit."""
    await run_query(prompt, state, query_loop, renderer, spinner)


async def main():
    args = parse_args()

    # Apply CLI overrides — provider first (sets defaults), then explicit overrides
    if args.provider:
        config.provider = args.provider
        config.base_url = ""  # reset so apply_provider fills them
        config.model = ""
        config.api_key = ""
        config.apply_provider(args.provider)
    if args.model:
        config.model = args.model
    if args.api_key:
        config.api_key = args.api_key
    if args.base_url:
        config.base_url = args.base_url
    if args.max_tokens:
        config.max_tokens = args.max_tokens
    if args.temperature is not None:
        config.temperature = args.temperature
    if args.no_stream:
        config.stream = False

    if not config.api_key:
        print("Error: No API key. Set DASHSCOPE_API_KEY or OPENAI_API_KEY env var, or use --api-key.")
        sys.exit(1)

    # Initialize components
    cwd = os.getcwd()
    llm_client = LLMClient(config)
    tool_registry = ToolRegistry()
    register_all(tool_registry)
    perm_manager = PermissionManager(auto_approve=args.yes, cwd=cwd)
    renderer = Renderer()
    spinner = Spinner()
    input_handler = InputHandler()

    # State
    state = AppState(cwd=cwd)
    set_app_state(state)

    # System prompt
    system_prompt = build_system_prompt(cwd)
    state.set_system(system_prompt)

    # Query loop
    query_loop = QueryLoop(llm_client, tool_registry, perm_manager, ui=renderer)

    # Commands
    cmd_registry = CommandRegistry()
    app_context = {
        "state": state,
        "renderer": renderer,
        "config": config,
        "llm_client": llm_client,
        "tool_registry": tool_registry,
    }
    register_builtins(cmd_registry, app_context)

    # Run
    if args.prompt:
        await one_shot(args.prompt, state, query_loop, renderer, spinner)
    else:
        await interactive_loop(state, query_loop, cmd_registry, renderer, input_handler, spinner)


def cli_entry():
    """Synchronous entry point for pip-installed console script."""
    asyncio.run(main())


if __name__ == "__main__":
    cli_entry()
