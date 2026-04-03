# 项目概述：Claude Code Py

## 项目简介

这是一个用 Python 重写的 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 命令行工具。它参考了 Anthropic 官方 CLI 的 TypeScript 版本，使用 Python 重写并保留了完整的工具调用能力。

**底层模型支持任意 OpenAI 兼容接口**，默认使用 DashScope / Qwen。

## 技术栈

| 类别 | 技术/库 | 版本要求 |
|------|---------|----------|
| 编程语言 | Python | >= 3.9 |
| LLM 客户端 | openai | >= 1.0 |
| UI 渲染 | rich | >= 13.0 |
| 输入处理 | prompt_toolkit | >= 3.0 |
| HTTP 客户端 | httpx | >= 0.24 |
| 可选依赖 | markdownify | >= 0.11 |
| 可选依赖 | pypdf | >= 3.0 |

## 目录结构

```
claude-code-py-main/
├── claude_code_py/              # 核心源码目录
│   ├── __init__.py             # 包入口（空）
│   ├── main.py                 # 程序主入口（asyncio + argparse）
│   ├── config.py               # 全局配置管理
│   │
│   ├── core/                   # 核心逻辑模块
│   │   ├── __init__.py
│   │   ├── context.py          # 系统 Prompt 构建
│   │   ├── compact.py          # 上下文压缩
│   │   ├── permissions.py      # 权限管理
│   │   ├── query_loop.py       # 查询循环（主执行引擎）
│   │   ├── state.py            # 应用状态管理
│   │   └── tool.py             # 工具基类和注册表
│   │
│   ├── llm/                    # LLM 客户端
│   │   ├── __init__.py
│   │   ├── client.py           # OpenAI 兼容客户端
│   │   └── messages.py         # 消息类型定义
│   │
│   ├── tools/                  # 20 个工具实现
│   │   ├── __init__.py         # 工具注册
│   │   ├── bash_tool.py        # Bash 命令执行
│   │   ├── file_read.py        # 文件读取
│   │   ├── file_edit.py        # 文件编辑
│   │   ├── file_write.py       # 文件写入
│   │   ├── grep_tool.py        # 文件搜索
│   │   ├── glob_tool.py        # 文件匹配
│   │   ├── agent_tool.py       # 子代理
│   │   ├── ask_user.py         # 用户提问
│   │   ├── web_search.py       # Web 搜索
│   │   ├── web_fetch.py        # Web 抓取
│   │   ├── notebook_edit.py    # Notebook 编辑
│   │   ├── task_tools.py       # 任务管理（4 个工具）
│   │   ├── cron_tools.py       # Cron 管理（3 个工具）
│   │   └── plan_tools.py       # 计划模式（2 个工具）
│   │
│   ├── commands/               # 斜杠命令
│   │   ├── __init__.py
│   │   ├── registry.py         # 命令注册表
│   │   └── builtins.py         # 内置命令实现
│   │
│   ├── ui/                     # 用户界面
│   │   ├── __init__.py
│   │   ├── renderer.py         # 渲染器
│   │   ├── input_handler.py    # 输入处理
│   │   └── spinner.py          # 加载动画
│   │
│   └── utils/                  # 工具函数
│       ├── __init__.py
│       ├── tokens.py           # Token 估算
│       └── git.py              # Git 信息获取
│
├── skills/                     # 技能定义
│   └── repo_parser/            # 仓库解析技能
│       └── skill.md
│
├── docs_repo_parser/           # 文档输出目录（本项目的分析文档）
│   ├── 00_start.md            # 项目概述（本文档）
│   └── ...                    # 其他分析文档
│
├── pyproject.toml              # Python 项目配置
├── README.md                   # 英文 README
├── README.zh-CN.md             # 中文 README
└── requirements.txt            # 依赖列表
```

**文件统计**：
- 核心代码：39 个 Python 文件
- 总行数：约 4220 行
- 工具实现：15 个文件（包含 14 种工具，任务/Cron/计划模式各有多个工具）

## 入口点

| 文件 | 功能 |
|------|------|
| `claude_code_py/main.py` | 主程序入口，提供 CLI 入口 `claudepy` |
| `claude_code_py/config.py` | 全局配置单例 `config` |
| `claude_code_py/tools/__init__.py` | 工具注册入口 `register_all()` |

**命令行入口**（通过 `pyproject.toml` 定义）：
```bash
claudepy [选项] [提示词]
```

示例：
```bash
claudepy -y                              # 自动批准工具调用
claudepy --provider openai -p "fix bug"  # 单次模式
```

## 核心模块概述

### 1. 核心模块 (core/)

| 模块 | 功能 | 关键类/函数 |
|------|------|-------------|
| `tool.py` | 工具基类 + 注册表 | `BaseTool`, `ToolRegistry` |
| `query_loop.py` | 查询循环（主引擎） | `QueryLoop.run()` |
| `state.py` | 应用状态管理 | `AppState` |
| `permissions.py` | 权限管理 | `PermissionManager`, `Permission` |
| `context.py` | 系统 Prompt 构建 | `build_system_prompt()` |
| `compact.py` | 上下文压缩 | `compact_messages()` |

### 2. LLM 模块 (llm/)

| 模块 | 功能 |
|------|------|
| `client.py` | OpenAI 兼容客户端，支持流式/非流式调用 |
| `messages.py` | 定义消息类型（SystemMessage, UserMessage, AssistantMessage, ToolResultMessage） |

### 3. 工具模块 (tools/)

实现 **20 个工具**，分为以下几类：

| 类别 | 工具 | 功能 |
|------|------|------|
| **核心工具** | Bash, Read, Edit, Write, Grep, Glob | 文件操作和命令执行 |
| **代理** | Agent | 子代理，递归执行复杂任务 |
| **任务管理** | TaskCreate, TaskGet, TaskUpdate, TaskList | 任务创建和查询 |
| **用户交互** | AskUser | 向用户提问 |
| **Web** | WebSearch, WebFetch | 网页搜索和抓取 |
| **Notebook** | NotebookEdit | Jupyter Notebook 编辑 |
| **Cron** | CronCreate, CronDelete, CronList | Cron 任务管理 |
| **计划模式** | EnterPlanMode, ExitPlanMode | 计划模式切换 |

### 4. UI 模块 (ui/)

| 模块 | 功能 |
|------|------|
| `renderer.py` | 输出渲染（Rich 库） |
| `input_handler.py` | 交互式输入（prompt_toolkit） |
| `spinner.py` | 加载动画 |

### 5. 命令模块 (commands/)

| 模块 | 功能 |
|------|------|
| `registry.py` | 斜杠命令注册表 |
| `builtins.py` | 内置命令实现（/help, /model, /provider 等） |

## 快速启动

```bash
# 安装
git clone https://github.com/ZackZikaiXiao/claude-code-py.git
cd claude-code-py
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 设置 API Key
export DASHSCOPE_API_KEY=sk-xxx

# 运行
claudepy -y
```

## 支持的 LLM Provider

| Provider | 环境变量 | 默认模型 |
|----------|----------|----------|
| dashscope | DASHSCOPE_API_KEY | qwen-plus-latest |
| openai | OPENAI_API_KEY | gpt-4o |
| anthropic | ANTHROPIC_API_KEY | claude-sonnet-4 |
| deepseek | DEEPSEEK_API_KEY | deepseek-chat |
| openrouter | OPENROUTER_API_KEY | anthropic/claude-sonnet-4 |

## 工作原理概览

```
┌─────────────────────────────────────────────────────────────┐
│                        用户输入                              │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    main.py (入口)                           │
│  - 解析命令行参数                                            │
│  - 初始化组件 (LLM, ToolRegistry, PermissionManager)        │
│  - 创建 QueryLoop                                            │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                  QueryLoop.run() (主循环)                   │
│  1. 检查上下文大小，必要时压缩                               │
│  2. 调用 LLM 获取响应                                         │
│  3. 解析响应（文本 + 工具调用）                              │
│  4. 执行工具（只读工具并行，写工具串行）                     │
│  5. 将工具结果添加回上下文                                   │
│  6. 重复直到没有工具调用                                     │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      工具执行                                │
│  - Bash: 执行 shell 命令                                      │
│  - Read/Edit/Write: 文件操作                                 │
│  - Grep/Glob: 文件搜索                                       │
│  - Agent: 递归调用 QueryLoop                                │
│  ...（共 20 个工具）                                           │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                      输出结果                                │
└─────────────────────────────────────────────────────────────┘
```

## 核心设计特点

1. **Query Loop 架构**：基于 LLM 的查询循环，不断请求 LLM→执行工具→反馈结果
2. **并发执行**：只读工具（Read, Grep, Glob）可并行执行；写工具（Edit, Write）串行执行
3. **权限系统**：三层权限控制（持久化规则、会话内授权、危险命令强制确认）
4. **上下文压缩**：当接近 Token 限制时自动压缩历史消息
5. **工具调用流式解析**：支持流式输出和流式工具调用参数解析
6. **递归 Agent**：支持子代理递归调用（最大深度 3 层）
7. **OpenAI 兼容**：支持任意 OpenAI 兼容 API（DashScope, OpenAI, Anthropic 等）

## 下一步

- **架构分析**：深入了解启动流程、模块依赖关系、数据流
- **模块深入**：逐个分析核心工具和模块的实现细节
- **扩展开发**：如何添加新工具、如何修改系统 Prompt

---

**建议阅读顺序**：
1. 本文档（00_start.md）
2. `01_query_loop.md`（查询循环核心逻辑）
3. `02_tool_system.md`（工具系统架构）
4. `03_bash_tool.md`（Bash 工具实现详解）
5. `04_permission_system.md`（权限系统详解）
