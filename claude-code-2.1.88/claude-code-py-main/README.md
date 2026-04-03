# Claude Code Py

[中文说明](./README.zh-CN.md)

Python implementation of [Claude Code](https://docs.anthropic.com/en/docs/claude-code), Anthropic's official AI coding assistant CLI. Reverse-engineered from the original TypeScript source (~500K lines) and rewritten in Python with full tool-use support.

Uses any OpenAI-compatible API (DashScope/Qwen by default) as the LLM backend.

## Quick Start

```bash
# Install
git clone https://github.com/ZackZikaiXiao/claude-code-py.git
cd claude-code-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# Set your API key
export DASHSCOPE_API_KEY=sk-xxx

# Run
claudepy -y
```

`-y` auto-approves tool calls so the AI can read/write files and run commands without asking every time.

## What It Can Do

Like the original Claude Code, you talk to it in natural language and it uses tools to get things done:

```
> Help me create a Flask app with a /hello endpoint

  📝 Write  app.py (12 lines)
  ✓ Write  Created: app.py

  $ pip install flask
  $ python app.py

Done. Flask app running on http://localhost:5000/hello
```

**20 built-in tools**: Bash, Read, Edit, Write, Grep, Glob, Agent (sub-agents), WebSearch, WebFetch, NotebookEdit, Task management, Plan mode, and more.

## Switching Models

Works with any OpenAI-compatible API. Built-in provider presets:

```bash
claudepy -y                            # Default: DashScope qwen-plus-latest
claudepy -y --provider openai          # OpenAI gpt-4o (needs OPENAI_API_KEY)
claudepy -y --provider deepseek        # DeepSeek (needs DEEPSEEK_API_KEY)
claudepy -y --provider anthropic       # Anthropic Claude (needs ANTHROPIC_API_KEY)
claudepy -y --provider openrouter      # OpenRouter (needs OPENROUTER_API_KEY)
claudepy -y --model qwen-max           # Use a specific model name
```

Switch at runtime with `/provider openai` or `/model gpt-4o`.

## CLI Options

```bash
claudepy -y                     # Recommended: auto-approve tools
claudepy -y -p "fix the bug"   # One-shot mode (non-interactive)
claudepy --model qwen-max       # Specify model
claudepy --base-url https://... # Custom API endpoint
claudepy --max-tokens 16384     # Max output tokens
```

## Slash Commands

Type these during a conversation:

| Command | Description |
|---------|-------------|
| `/help` | Show all commands |
| `/model qwen-max` | Switch model |
| `/provider openai` | Switch provider |
| `/clear` | Clear conversation |
| `/compact` | Compress context to save tokens |
| `/cost` | Show token usage |
| `/tools` | List available tools |
| `/exit` | Quit |

## Permission System

First time a write tool runs, you'll see:

```
  ⚠ Bash
  $ npm install
  Allow? Yes(y) / Always this session(a) / Always forever(!) / No(n):
```

- **y** — allow this once
- **a** — don't ask again this session
- **!** — never ask again (saved to `~/.claude/settings.json`)
- **n** — deny

Or just use `claudepy -y` to skip all of this.

## How It Works

This is a Python rewrite based on the Claude Code TypeScript source. The core architecture is preserved:

1. **Query Loop** — send messages + tool schemas to LLM → parse streaming response → execute tool calls → loop until done
2. **Tool System** — 20 tools, each with JSON schema, permission rules, and async execution
3. **Concurrent Execution** — read-only tools (Grep, Glob, Read) run in parallel; write tools run serially
4. **Auto-Compact** — when conversation approaches context limit, older messages are summarized by the LLM
5. **Persistent Permissions** — tool approvals saved to disk, no repeated prompts

## Install from GitHub

```bash
pip install git+https://github.com/ZackZikaiXiao/claude-code-py.git
```

## Requirements

- Python >= 3.9
- `openai`, `rich`, `prompt_toolkit`, `httpx`
- Optional: `markdownify`, `pypdf`

## License

MIT
