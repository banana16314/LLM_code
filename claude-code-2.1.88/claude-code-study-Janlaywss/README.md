# Cloud Code Study

基于 [Cloud Code](https://github.com/Janlaywss/cloud-code) 源码的深度学习笔记，拆解一个工业级 AI Agent 系统的架构设计。

## 这个项目是什么

这是一个静态文档站点，面向**对 Agent 设计感兴趣但还不熟练**的开发者。通过阅读 Cloud Code 的源码，把核心架构拆解成 9 个模块，用简洁的语言、比喻、架构图和真实代码片段来讲解。

## 内容模块

| # | 模块 | 核心问题 |
|---|------|----------|
| 1 | Agent Loop | 从一个 Prompt 到完成任务，循环是怎么跑的？ |
| 2 | Tool 与沙箱 | 如何定义工具？如何安全执行？如何防逃逸？ |
| 3 | 子 Agent 设计 | 多 Agent 如何分工、通信、协作？ |
| 4 | 任务图 | 状态机、父子关系、回收机制 |
| 5 | System Prompt | 提示词拼装、分层缓存、缓存失效检测 |
| 6 | 上下文压缩 | 三级压缩策略：微压缩 → 自动压缩 → 全量压缩 |
| 7 | Memory 系统 | 四层记忆结构，从会话到跨项目持久化 |
| 8 | 后台任务 | 后台 Agent、Cron 调度、Dream 记忆整理 |
| 9 | Skill 与 MCP | 能力扩展：Prompt 模板 + 外部服务协议 |

## 技术栈

- **框架**：[Rspress](https://rspress.dev/) — 基于 Rsbuild + React 的静态站点生成器
- **内容**：Markdown + MDX
- **源码分析对象**：[Cloud Code](https://github.com/Janlaywss/cloud-code)

## 本地开发

```bash
# 安装依赖
pnpm install

# 启动开发服务器
pnpm dev

# 构建生产版本
pnpm build

# 预览构建结果
pnpm preview
```

## 项目结构

```
cloud-code-study/
├── docs/
│   ├── index.md                  # 首页
│   └── guide/
│       ├── 01-agent-loop.md      # Agent Loop
│       ├── 02-tool-sandbox.md    # Tool 与沙箱
│       ├── 03-sub-agent.md       # 子 Agent 设计
│       ├── 04-task-graph.md      # 任务图
│       ├── 05-system-prompt.md   # System Prompt
│       ├── 06-context-compression.md  # 上下文压缩
│       ├── 07-memory.md          # Memory 系统
│       ├── 08-background-task.md # 后台任务
│       └── 09-skill-mcp.md       # Skill 与 MCP
├── theme/                        # 自定义主题
├── rspress.config.ts             # 站点配置
└── package.json
```

## 部署

本站通过 Vercel 部署，访问地址：https://cloud-code-study.vercel.app/

## License

MIT
