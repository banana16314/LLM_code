# 项目文档索引

本文档索引提供了 `claude-code-py` 项目的完整文档导航。

## 快速开始

1. **项目概述** - [`00_start.md`](./00_start.md)
   - 项目简介
   - 技术栈
   - 目录结构
   - 核心模块概览

2. **架构分析** - [`01_architecture.md`](./01_architecture.md)
   - 启动流程
   - 核心数据流
   - 模块依赖图
   - 核心数据模型

3. **工具系统** - [`02_tool_system.md`](./02_tool_system.md)
   - 工具架构
   - 工具列表（20 个工具）
   - 并发执行策略
   - 扩展新工具

4. **Bash 工具** - [`03_bash_tool.md`](./03_bash_tool.md)
   - 命令执行
   - 后台执行
   - 危险命令检测
   - 工作目录跟踪

5. **文件工具** - [`04_file_tools.md`](./04_file_tools.md)
   - Read 工具（支持图片、PDF、Notebook）
   - Edit 工具（精确字符串替换）
   - Write 工具（显示 diff）

6. **权限系统** - [`05_permission_system.md`](./05_permission_system.md)
   - 权限等级
   - 危险命令检测
   - 授权方式（持久化、会话、单次）
   - 配置文件

7. **查询循环** - [`06_query_loop.md`](./06_query_loop.md)
   - 核心循环
   - 自动上下文压缩
   - 工具并发执行
   - 错误处理

8. **斜杠命令** - [`07_slash_commands.md`](./07_slash_commands.md)
   - 可用命令列表
   - 命令注册机制
   - 各命令详解

9. **系统 Prompt** - [`08_system_prompt.md`](./08_system_prompt.md)
   - Prompt 结构
   - 各部分详解
   - 构建逻辑

## 核心模块源码位置

| 模块 | 文件路径 | 说明 |
|------|----------|------|
| 主入口 | `claude_code_py/main.py` | 程序入口、启动流程 |
| 配置管理 | `claude_code_py/config.py` | 全局配置、Provider 管理 |
| 核心工具 | `claude_code_py/core/tool.py` | BaseTool、ToolRegistry |
| 查询循环 | `claude_code_py/core/query_loop.py` | 主执行引擎 |
| 状态管理 | `claude_code_py/core/state.py` | AppState |
| 权限管理 | `claude_code_py/core/permissions.py` | PermissionManager |
| 系统 Prompt | `claude_code_py/core/context.py` | build_system_prompt |
| 上下文压缩 | `claude_code_py/core/compact.py` | compact_messages |
| LLM 客户端 | `claude_code_py/llm/client.py` | LLMClient |
| 消息类型 | `claude_code_py/llm/messages.py` | Message、ToolCall、ToolResult |
| 工具注册 | `claude_code_py/tools/__init__.py` | register_all |
| Bash 工具 | `claude_code_py/tools/bash_tool.py` | BashTool |
| 文件读取 | `claude_code_py/tools/file_read.py` | FileReadTool |
| 文件编辑 | `claude_code_py/tools/file_edit.py` | FileEditTool |
| 文件写入 | `claude_code_py/tools/file_write.py` | FileWriteTool |
| 搜索工具 | `claude_code_py/tools/grep_tool.py` | GrepTool |
| 文件匹配 | `claude_code_py/tools/glob_tool.py` | GlobTool |
| 子代理 | `claude_code_py/tools/agent_tool.py` | AgentTool |
| 命令注册 | `claude_code_py/commands/registry.py` | CommandRegistry |
| 斜杠命令 | `claude_code_py/commands/builtins.py` | 内置命令 |
| UI 渲染 | `claude_code_py/ui/renderer.py` | Renderer |

## 学习路径建议

### 入门路径
1. `00_start.md` - 了解项目全貌
2. `01_architecture.md` - 理解整体架构
3. `02_tool_system.md` - 掌握工具系统

### 深入理解
4. `06_query_loop.md` - 学习核心执行引擎
5. `05_permission_system.md` - 理解权限控制
6. `08_system_prompt.md` - 了解系统指令

### 工具细节
7. `03_bash_tool.md` - Bash 工具详解
8. `04_file_tools.md` - 文件工具详解

### 高级特性
9. `07_slash_commands.md` - 斜杠命令系统

## 关键概念速查

| 概念 | 描述 | 相关文档 |
|------|------|----------|
| Query Loop | 主执行循环 | `06_query_loop.md` |
| Tool System | 20 个工具的实现 | `02_tool_system.md` |
| Permission System | 权限控制 | `05_permission_system.md` |
| Auto-Compact | 上下文自动压缩 | `01_architecture.md`, `06_query_loop.md` |
| Slash Commands | 斜杠命令 | `07_slash_commands.md` |
| System Prompt | 系统指令 | `08_system_prompt.md` |
| Concurrent Execution | 工具并发执行 | `02_tool_system.md`, `06_query_loop.md` |
| Agent Recursion | 子代理递归 | `02_tool_system.md` |

## 命令参考

### 运行时命令
- `/help` - 显示所有命令
- `/model [name]` - 切换模型
- `/provider [name]` - 切换 Provider
- `/clear` - 清空对话
- `/compact` - 压缩上下文
- `/cost` - 查看 Token 使用
- `/tools` - 查看可用工具
- `/exit` - 退出

### CLI 参数
- `-y` - 自动批准所有工具调用
- `-p "prompt"` - 单次模式
- `--provider name` - 指定 Provider
- `--model name` - 指定模型
- `--base-url url` - 自定义 API 地址

## 工具列表速查

| 类别 | 工具 | 只读 |
|------|------|------|
| 核心 | Bash | ❌ |
| 核心 | Read | ✅ |
| 核心 | Edit | ❌ |
| 核心 | Write | ❌ |
| 核心 | Grep | ✅ |
| 核心 | Glob | ✅ |
| 代理 | Agent | ❌ |
| 任务 | TaskCreate | ❌ |
| 任务 | TaskGet | ✅ |
| 任务 | TaskUpdate | ❌ |
| 任务 | TaskList | ✅ |
| 交互 | AskUser | ✅ |
| Web | WebSearch | ✅ |
| Web | WebFetch | ✅ |
| Notebook | NotebookEdit | ❌ |
| Cron | CronCreate | ❌ |
| Cron | CronDelete | ❌ |
| Cron | CronList | ✅ |
| Plan | EnterPlanMode | ❌ |
| Plan | ExitPlanMode | ❌ |

## 文件统计

- 核心代码：39 个 Python 文件
- 总行数：约 4220 行
- 工具实现：15 个文件（20 个工具）

## 相关资源

- [项目 README](../README.zh-CN.md) - 项目介绍和快速开始
- [skill.md](../skills/repo_parser/skill.md) - 仓库解析技能定义
- [官方 Claude Code](https://docs.anthropic.com/en/docs/claude-code) - 原始项目文档

---

**最后更新**: 2026-04-03
**文档版本**: 1.0
