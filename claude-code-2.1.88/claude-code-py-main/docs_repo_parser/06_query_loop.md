# 查询循环详解

## 概述

`QueryLoop` 是整个系统的核心执行引擎，负责不断循环：请求 LLM→解析响应→执行工具→反馈结果，直到任务完成。

**文件**: `claude_code_py/core/query_loop.py`

## 核心循环

```
┌──────────────────────────────────────────────────────────────────┐
│                     QueryLoop.run(state)                         │
│                                                                  │
│  for iteration in range(40):  # MAX_TOOL_ITERATIONS             │
│      │                                                           │
│      ▼                                                           │
│  1. auto_compact()                                               │
│     - 检查 token 数                                                │
│     - > 120K - 13K → 压缩消息                                     │
│      │                                                           │
│      ▼                                                           │
│  2. llm.chat(messages, tools=...)                               │
│     - 流式调用 LLM                                                │
│     - 返回 StreamChunk iterator                                  │
│      │                                                           │
│      ▼                                                           │
│  3. 收集响应：                                                     │
│     - 文本 → yield 给用户                                         │
│     - 工具调用 → 加入 assistant msg                               │
│      │                                                           │
│      ▼                                                           │
│  4. 检查是否完成：                                                 │
│     - finish_reason="length" → OTK 恢复                           │
│     - 无工具调用 → 退出循环                                       │
│      │                                                           │
│      ▼                                                           │
│  5. 分离工具调用：                                                 │
│     - read_only_batch (Read, Grep, Glob)                        │
│     - serial_batch (Edit, Write, Bash, Agent)                   │
│      │                                                           │
│      ▼                                                           │
│  6. 并行执行只读工具：                                             │
│     results = await asyncio.gather(*tasks)                      │
│      │                                                           │
│      ▼                                                           │
│  7. 串行执行写工具：                                               │
│     for tc in serial_batch:                                      │
│         result = await _execute_with_permission(...)            │
│      │                                                           │
│      ▼                                                           │
│  8. 添加 tool_result 到 messages                                 │
│      │                                                           │
│      └─→ 下一轮循环                                               │
└──────────────────────────────────────────────────────────────────┘
```

## 实现细节

### 1. 自动上下文压缩

```python
# query_loop.py 中的 run 方法
for iteration in range(MAX_TOOL_ITERATIONS):
    # 计算总 token 数
    total_tokens = sum(
        estimate_tokens(m.content if isinstance(m.content, str) else str(m.content))
        for m in state.messages
    )
    
    max_ctx = default_config.max_context_tokens  # 默认 120,000
    threshold = max_ctx - 13_000  # 触发阈值
    
    if total_tokens > threshold:
        # 压缩消息历史
        state.messages = await compact_messages(
            state.messages, self.llm,
            max_tokens=max_ctx,
            keep_recent=6,  # 保留最近 6 条消息
        )
```

**压缩策略**：
- 触发阈值：上下文窗口的 80% 左右（120K - 13K = 107K）
- 保留最近 6 条消息
- 使用 LLM 生成旧消息的摘要

### 2. LLM 调用与流式响应

```python
# 调用 LLM
response = await self.llm.chat(
    messages=state.get_api_messages(),
    tools=self.tools.get_schemas() if self.tools.list_tools() else None,
    stream=True,
)

# 收集流式响应
text_parts = []
tool_calls: list[ToolCall] = []
finish_reason = ""

async for chunk in response:
    if chunk.type == "text":
        text_parts.append(chunk.text)
        yield chunk.text  # 实时输出文本
    elif chunk.type == "tool_call_start" and chunk.tool_call:
        tool_calls.append(chunk.tool_call)
    elif chunk.type == "done":
        finish_reason = chunk.finish_reason
        break

# 构建 assistant 消息
full_text = "".join(text_parts)
assistant_msg = AssistantMessage(
    content=full_text,
    tool_calls=tool_calls,
)
state.add_assistant(assistant_msg)
```

### 3. Output Token 限制恢复

```python
# 处理 finish_reason="length"
if finish_reason == "length" and not tool_calls:
    if otk_recovery_count < MAX_OTK_RECOVERY:  # 最多 3 次
        otk_recovery_count += 1
        log.info(f"OTK recovery attempt {otk_recovery_count}/{MAX_OTK_RECOVERY}")
        
        # 注入恢复提示
        state.add_user(OTK_RECOVERY_MESSAGE)
        yield "\n"
        continue  # 重试
    
    else:
        yield "\n[Output truncated — max recovery attempts reached]"
        break
```

**恢复消息**：
```
Output token limit hit. Resume directly from where you stopped — 
no apology, no recap, just continue the work seamlessly.
```

### 4. 工具调用分离

```python
# 分离只读和写工具
read_only_batch = []
serial_batch = []

for tc in tool_calls:
    tool = self.tools.get(tc.name)
    if tool is None:
        serial_batch.append(tc)
        continue
    
    try:
        args = json.loads(tc.arguments) if tc.arguments else {}
    except json.JSONDecodeError:
        serial_batch.append(tc)
        continue
    
    if tool.is_read_only(args):
        read_only_batch.append((tc, tool, args))
    else:
        serial_batch.append(tc)
```

### 5. 并发执行只读工具

```python
# 并行执行只读工具
if read_only_batch:
    tasks = [
        self._execute_with_permission(tc, tool, args, context)
        for tc, tool, args in read_only_batch
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for (tc, tool, args), result in zip(read_only_batch, results):
        if isinstance(result, Exception):
            result = ToolResult(error=str(result), is_error=True)
        
        result = _budget_result(result)  # 截断超大结果
        
        if self.ui:
            self.ui.render_tool_result(tc.name, args, result)
        
        state.add_tool_result(tc.id, tc.name, result)
```

### 6. 串行执行写工具

```python
# 串行执行写工具
for tc in serial_batch:
    tool = self.tools.get(tc.name)
    if tool is None:
        result = ToolResult(error=f"Unknown tool: {tc.name}", is_error=True)
        state.add_tool_result(tc.id, tc.name, result)
        continue
    
    try:
        args = json.loads(tc.arguments) if tc.arguments else {}
    except json.JSONDecodeError:
        result = ToolResult(error=f"Invalid JSON: {tc.arguments[:200]}", is_error=True)
        state.add_tool_result(tc.id, tc.name, result)
        continue
    
    result = await self._execute_with_permission(tc, tool, args, context)
    result = _budget_result(result)
    
    if self.ui:
        self.ui.render_tool_result(tc.name, args, result)
    
    state.add_tool_result(tc.id, tc.name, result)
```

### 7. 工具调用/结果配对验证

```python
def _ensure_tool_result_pairing(self, state: AppState, tool_calls: list[ToolCall]):
    """确保每个 tool_use 都有对应的 tool_result。"""
    # 收集已有结果的 tool_call_id
    result_ids = set()
    for m in reversed(state.messages):
        if hasattr(m, "tool_call_id") and m.tool_call_id:
            result_ids.add(m.tool_call_id)
        elif m.role == "assistant":
            break  # 只检查最后一条 assistant 消息之后的结果
    
    # 检查是否有缺失
    for tc in tool_calls:
        if tc.id not in result_ids:
            log.warning(f"Missing tool_result for tool_use {tc.id} ({tc.name})")
            state.add_tool_result(
                tc.id, tc.name,
                ToolResult(
                    error=f"Tool {tc.name} was called but did not return a result.",
                    is_error=True,
                ),
            )
```

### 8. 结果预算限制

```python
MAX_TOOL_RESULT_CHARS = 50_000
RESULT_PREVIEW_CHARS = 2_000

def _budget_result(result: ToolResult) -> ToolResult:
    """截断超出预算的工具结果。"""
    text = result.text
    if len(text) <= MAX_TOOL_RESULT_CHARS:
        return result
    
    preview = text[:RESULT_PREVIEW_CHARS]
    truncated_msg = (
        f"Output too large ({len(text):,} chars, max {MAX_TOOL_RESULT_CHARS:,}).\n\n"
        f"Preview (first {RESULT_PREVIEW_CHARS:,} chars):\n{preview}\n\n"
        f"... ({len(text) - RESULT_PREVIEW_CHARS:,} more chars truncated)"
    )
    
    if result.is_error:
        return ToolResult(error=truncated_msg, is_error=True)
    return ToolResult(output=truncated_msg)
```

## 核心常量

```python
MAX_TOOL_ITERATIONS = 40      # 最大迭代次数（防止无限循环）
MAX_CONCURRENCY = 10          # 只读工具最大并发数
MAX_OTK_RECOVERY = 3          # Token 超限恢复尝试次数
MAX_TOOL_RESULT_CHARS = 50_000  # 工具结果最大字符数
RESULT_PREVIEW_CHARS = 2_000  # 结果预览字符数
```

## 工具执行状态机

```
开始
  │
  ├─ 检查上下文 → 压缩（如果需要）
  │
  ├─ LLM 调用
  │   │
  │   ├─ finish_reason="length" + 无工具调用 → OTK 恢复（最多 3 次）
  │   │   └─ 恢复成功 → 继续循环
  │   │   └─ 恢复失败 → 退出
  │   │
  │   └─ finish_reason != "length" → 继续
  │
  ├─ 无工具调用 → 完成
  │
  ├─ 分离工具：只读（并行）vs 写（串行）
  │
  ├─ 执行工具：
  │   │
  │   ├─ 只读工具：asyncio.gather（并行）
  │   │   ├─ 检查权限
  │   │   ├─ 执行
  │   │   └─ 添加结果
  │   │
  │   └─ 写工具：for 循环（串行）
  │       ├─ 检查权限
  │       ├─ 执行
  │       └─ 添加结果
  │
  ├─ 验证 tool_use/tool_result 配对
  │
  └─ 迭代次数 < 40 → 继续循环
      └─ 达到 40 → 退出（"Max tool iterations reached"）
```

## 并发执行示例

假设 LLM 返回以下工具调用：
```json
{
  "tool_calls": [
    {"name": "Read", "arguments": {"file_path": "app.py"}},
    {"name": "Read", "arguments": {"file_path": "config.py"}},
    {"name": "Grep", "arguments": {"pattern": "TODO"}},
    {"name": "Edit", "arguments": {"file_path": "app.py", "old_string": "old", "new_string": "new"}},
    {"name": "Write", "arguments": {"file_path": "new.py", "content": "..."}}
  ]
}
```

**执行流程**：

```
1. 分离
   read_only_batch = [
       (Read app.py),
       (Read config.py),
       (Grep TODO)
   ]
   serial_batch = [
       (Edit app.py),
       (Write new.py)
   ]

2. 并行执行 read_only_batch
   tasks = [
       execute_with_permission(Read app.py),
       execute_with_permission(Read config.py),
       execute_with_permission(Grep TODO)
   ]
   results = await asyncio.gather(*tasks)
   # 三个工具并发执行，速度取决于最慢的那个

3. 串行执行 serial_batch
   for tc in serial_batch:
       result = await execute_with_permission(tc)
       # Edit 完成后才执行 Write
```

## 错误处理

```python
# 工具执行失败
try:
    return await tool.call(args, context)
except Exception as e:
    log.exception(f"Tool {tool.name} failed")
    return ToolResult(error=str(e), is_error=True)

# 权限被拒绝
if perm == Permission.DENY:
    return ToolResult(error="Permission denied by policy", is_error=True)

# 用户拒绝
if not answer:  # user said "n"
    return ToolResult(error="User denied this action", is_error=True)

# 未知工具
if tool is None:
    result = ToolResult(error=f"Unknown tool: {tc.name}", is_error=True)
```

## 下一步

- `07_system_prompt.md` - 系统 Prompt 详解
- `08_llm_client.md` - LLM 客户端详解
- `09_slash_commands.md` - 斜杠命令详解
