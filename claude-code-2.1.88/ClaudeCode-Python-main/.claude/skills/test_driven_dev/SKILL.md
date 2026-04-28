---
name: tdd
description: |
  Test-Driven Development workflow. When modifying or developing code (Python, Shell, SQL, JavaScript, TypeScript, Vue, HTML, etc.), always write or update tests first, ensure they pass, then implement the code.
  Ensures every change is covered by passing tests before the final output.
---

# Test-Driven Development

当你需要修改或开发代码（Python、Shell、SQL、JavaScript、TypeScript、Vue、HTML 等）时，严格遵循测试驱动开发（TDD）流程。

## 核心原则

1. **测试先行**：先写测试用例，再写实现代码。
2. **测试通过**：所有测试用例必须通过，才能输出最终脚本。
3. **增量开发**：每次只写足够让当前测试通过的代码，不一次性实现所有功能。
4. **不跳过测试**：即使是简单修改，也要确保有对应的测试覆盖。

## 工作流程

### Step 1: 理解需求

- 确认用户要修改或开发什么功能。
- 识别输入、输出、边界条件。

### Step 2: 检查现有测试

- 在 `tests/` 目录下搜索是否已有相关测试文件。
- 如有，先运行确认当前状态（通过还是失败）。

### Step 3: 编写测试用例

根据需求编写测试，覆盖以下场景：

- **正常路径**：典型输入 → 预期输出
- **边界条件**：空输入、极值、None/Null
- **异常路径**：非法输入、错误处理

将测试写入 `tests/test_{模块名}.{扩展名}`（或追加到已有测试文件）。

### Step 4: 运行测试（预期失败）

根据语言选择对应命令运行测试：

| 语言 | 测试命令示例 |
|------|-------------|
| Python | `pytest tests/test_{模块名}.py -v` |
| JavaScript/Node | `npx jest tests/test_{模块名}.test.js` |
| TypeScript | `npx jest tests/test_{模块名}.test.ts` 或 `npx vitest run` |
| Vue | `npx vitest run tests/{模块名}.spec.ts` |
| Shell | `bats tests/test_{模块名}.bats` 或直接用 bash 跑验证脚本 |
| SQL | `pgTap` / `sqllogictest` / 或手写验证查询对比结果 |

确认新测试失败（red 阶段）。如果一开始就通过，说明测试没有覆盖新逻辑。

### Step 5: 实现代码

编写刚好能让测试通过的最少代码。不做多余实现。

### Step 6: 运行测试（确认通过）

用 Step 4 中相同的命令再次运行，确认全部通过（green 阶段）。

### Step 7: 重构（可选）

如果代码有重复或不够清晰，在测试保护下进行重构，然后再次运行测试确认。

### Step 8: 输出最终结果

只有在所有测试通过后，才向用户展示或保存最终代码。

## 各语言测试要点

### Python
- 框架：pytest / unittest
- 测试文件命名：`test_xxx.py` 或 `xxx_test.py`
-  mock 外部依赖（数据库、API 调用）

### Shell
- 框架：bats / 手写验证脚本
- 用 `set -euo pipefail` 确保脚本严格模式
- 测试返回值、stdout 输出、临时文件生成
- 清理临时文件：`trap 'rm -f $tmpfile' EXIT`

### SQL
- 先写验证查询（SELECT 对比预期结果）
- 在事务中执行测试，完成后回滚：`BEGIN ... ROLLBACK`
- 覆盖空表、单行、多行、NULL 值场景

### JavaScript / TypeScript
- 框架：Jest / Vitest / Mocha
- 测试文件命名：`xxx.test.js` / `xxx.spec.ts`
- 测试异步函数时用 `async/await` 或 Promise
- mock 外部 API 调用（`fetch`、`axios`）

### Vue
- 框架：Vitest + Vue Test Utils
- 测试文件命名：`xxx.spec.ts` / `xxx.spec.vue`
- 测试组件渲染、事件触发、props 传递、状态变化
- 用 `mount` / `shallowMount` 挂载组件

### HTML
- 通过浏览器自动化（Playwright / Puppeteer）验证渲染结果
- 或用静态分析检查 DOM 结构、元素存在性
- 测试不同分辨率下的布局（如需响应式）

## 输出格式

完成 TDD 流程后，向用户报告：

```markdown
## TDD 完成

- **测试文件**: `tests/test_xxx.xxx`（X 个用例，全部通过）
- **修改文件**: `path/to/module.xxx`
- **覆盖场景**: 正常路径 / 边界条件 / 异常处理
```

## 注意事项

- 先确认项目已有的测试框架，不要引入不必要的依赖。
- 如果用户明确要求"快速实现不需要测试"，尊重用户意愿，但需提示风险。
- 每种语言都适用 TDD 思路——先定义验证条件，再实现代码。

## 触发条件

当用户说"修改"、"开发"、"实现"、"添加功能"、"改写脚本"等涉及代码变更的请求时，自动启动此流程。
