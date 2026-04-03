# Claude Code Py

[English](./README.md)

这是一个 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 的 Python 实现。它参考了 Anthropic 官方 CLI 的 TypeScript 版本，并使用 Python 重写，保留了完整的工具调用能力。

底层模型支持任意 OpenAI 兼容接口，默认使用 DashScope / Qwen。

## 快速开始

```bash
# 安装
git clone https://github.com/ZackZikaiXiao/claude-code-py.git
cd claude-code-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 设置 API Key
export DASHSCOPE_API_KEY=sk-xxx

# 运行,以本地vllm部署的Qwen3.5为例，端口8000，模型名字Qwen
export DASHSCOPE_API_KEY=gass-wlw-ai110
claudepy --base-url http://0.0.0.0:8000/v1 --model Qwen -y 
```

`-y` 会自动批准工具调用，这样 AI 在读写文件、执行命令时不需要每次都手动确认。

## 它能做什么

和原版 Claude Code 一样，你可以直接用自然语言提出任务，它会自动调用工具完成工作：

```text
> Help me create a Flask app with a /hello endpoint

  Write  app.py (12 lines)
  Write  Created: app.py

  $ pip install flask
  $ python app.py

Done. Flask app running on http://localhost:5000/hello
```

内置 **20 个工具**，包括 Bash、Read、Edit、Write、Grep、Glob、Agent（子代理）、WebSearch、WebFetch、NotebookEdit、任务管理、Plan 模式等。

## 切换模型

支持任意 OpenAI 兼容 API，并内置了常见 provider 预设：

```bash
claudepy -y                            # 默认：DashScope qwen-plus-latest
claudepy -y --provider openai          # OpenAI gpt-4o（需要 OPENAI_API_KEY）
claudepy -y --provider deepseek        # DeepSeek（需要 DEEPSEEK_API_KEY）
claudepy -y --provider anthropic       # Anthropic Claude（需要 ANTHROPIC_API_KEY）
claudepy -y --provider openrouter      # OpenRouter（需要 OPENROUTER_API_KEY）
claudepy -y --model qwen-max           # 指定具体模型
```

运行中也可以通过 `/provider openai` 或 `/model gpt-4o` 动态切换。

## CLI 选项

```bash
claudepy -y                     # 推荐：自动批准工具调用
claudepy -y -p "fix the bug"    # 单次执行模式（非交互）
claudepy --model qwen-max       # 指定模型
claudepy --base-url https://... # 自定义 API 地址
claudepy --max-tokens 16384     # 最大输出 token 数
```

## Slash Commands

在对话中可以直接输入以下命令：

| Command | Description |
|---------|-------------|
| `/help` | 显示全部命令 |
| `/model qwen-max` | 切换模型 |
| `/provider openai` | 切换 provider |
| `/clear` | 清空当前会话 |
| `/compact` | 压缩上下文以节省 token |
| `/cost` | 显示 token 使用情况 |
| `/tools` | 查看可用工具 |
| `/exit` | 退出 |

## 权限系统

第一次调用写入类工具时，你会看到类似这样的提示：

```text
  Bash
  $ npm install
  Allow? Yes(y) / Always this session(a) / Always forever(!) / No(n):
```

- **y**：只允许这一次
- **a**：本次会话中始终允许
- **!**：永久允许（保存到 `~/.claude/settings.json`）
- **n**：拒绝

如果你不想每次确认，可以直接使用 `claudepy -y`。

## 工作原理

这是一个基于 Claude Code TypeScript 源码思路进行重写的 Python 版本，核心架构保持一致：

1. **Query Loop**：向 LLM 发送消息和工具 schema，解析流式响应，执行工具调用，直到任务完成
2. **Tool System**：20 个工具，每个工具都有自己的 JSON schema、权限规则和异步执行逻辑
3. **Concurrent Execution**：只读工具（Grep、Glob、Read）可并行运行；写工具串行运行
4. **Auto-Compact**：当上下文接近上限时，会自动总结旧消息以节省 token
5. **Persistent Permissions**：工具授权会持久化保存，避免重复询问

## 从 GitHub 安装

```bash
pip install git+https://github.com/ZackZikaiXiao/claude-code-py.git
```

## 依赖要求

- Python >= 3.9
- `openai`, `rich`, `prompt_toolkit`, `httpx`
- 可选依赖：`markdownify`, `pypdf`

## 许可证

MIT
