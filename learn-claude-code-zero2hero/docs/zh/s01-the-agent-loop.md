# s01: The Agent Loop (智能体循环)

`[ s01 ] s02 > s03 > s04 > s05 > s06 | s07 > s08 > s09 > s10 > s11 > s12`

> *"One loop & Bash is all you need"* -- 一个工具 + 一个循环 = 一个智能体。
>
> **Harness 层**: 循环 -- 模型与真实世界的第一道连接。

## 问题

语言模型能推理代码, 但碰不到真实世界 -- 不能读文件、跑测试、看报错。没有循环, 每次工具调用你都得手动把结果粘回去。你自己就是那个循环。

## 解决方案

```
+--------+      +-------+      +---------+
|  User  | ---> |  LLM  | ---> |  Tool   |
| prompt |      |       |      | execute |
+--------+      +---+---+      +----+----+
                    ^                |
                    |   tool_result  |
                    +----------------+
                    (loop until stop_reason != "tool_use")
```

一个退出条件控制整个流程。循环持续运行, 直到模型不再调用工具。

## 工作原理

1. 用户 prompt 作为第一条消息。

```python
messages.append({"role": "user", "content": query})
```

2. 将消息和工具定义一起发给 LLM。

```python
response = client.messages.create(
    model=MODEL, system=SYSTEM, messages=messages,
    tools=TOOLS, max_tokens=8000,
)
```

3. 追加助手响应。检查 `stop_reason` -- 如果模型没有调用工具, 结束。

```python
messages.append({"role": "assistant", "content": response.content})
if response.stop_reason != "tool_use":
    return
```

4. 执行每个工具调用, 收集结果, 作为 user 消息追加。回到第 2 步。

```python
results = []
for block in response.content:
    if block.type == "tool_use":
        output = run_bash(block.input["command"])
        results.append({
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
        })
messages.append({"role": "user", "content": results})
```

组装为一个完整函数:

```python
def agent_loop(query):
    messages = [{"role": "user", "content": query}]
    while True:
        response = client.messages.create(
            model=MODEL, system=SYSTEM, messages=messages,
            tools=TOOLS, max_tokens=8000,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return

        results = []
        for block in response.content:
            if block.type == "tool_use":
                output = run_bash(block.input["command"])
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        messages.append({"role": "user", "content": results})
```

不到 30 行, 这就是整个智能体。后面 11 个章节都在这个循环上叠加机制 -- 循环本身始终不变。

## 变更内容

| 组件          | 之前       | 之后                           |
|---------------|------------|--------------------------------|
| Agent loop    | (无)       | `while True` + stop_reason     |
| Tools         | (无)       | `bash` (单一工具)              |
| Messages      | (无)       | 累积式消息列表                 |
| Control flow  | (无)       | `stop_reason != "tool_use"`    |

## 试一试

```sh
cd learn-claude-code
python agents/s01_agent_loop.py
```

试试这些 prompt (英文 prompt 对 LLM 效果更好, 也可以用中文):

1. `Create a file called hello.py that prints "Hello, World!"`
2. `List all Python files in this directory`
3. `What is the current git branch?`
4. `Create a directory called test_output and write 3 files in it`



## 例子说明

例子:bash工具调用:
```txt
***************
[ThinkingBlock(signature='', thinking='The user wants me to run the `ls -l` command to view all files. I need to execute this command using the bash tool.\n', type='thinking'), ToolUseBlock(id='fqlIG9tR4WeKiOFvimDOjT5DfUfLO1nE', caller=None, input={'command': 'ls -l'}, name='bash', type='tool_use')]
***************
bash command: 
$ ls -l
to run cmd:
ret of cmd:
total 104
drwxrwxr-x 2 hcq hcq  4096 Mar 29 08:43 agents
drwxrwxr-x 5 hcq hcq  4096 Mar 29 08:43 docs
-rw-rw-r-- 1 hcq hcq    23 Mar 29 21:13 hello.py
-rw-rw-r-- 1 hcq hcq  1068 Mar 29 08:43 LICENSE
-rw-rw-r-- 1 hcq hcq 28151 Mar 29 08:43 README-ja.md
-rw-rw-r-- 1 hcq hcq 23811 Mar 29 08:43 README.md
-rw-rw-r-- 1 hcq hcq 22054 Mar 29 08:43 README-zh.md
-rw-rw-r-- 1 hcq hcq    39 Mar 29 08:43 requirements.txt
drwxrwxr-x 6 hcq hcq  4096 Mar 29 08:43 skills
drwxrwxr-x 5 hcq hcq  4096 Mar 29 08:43 web
***************
[ThinkingBlock(signature='', thinking='The ls -l command has been executed successfully. 
The output shows the files and directories in the current directory with detailed information including permissions, owner, size, and modification date.\n\n
Files found:\n- agents/ - directory\n- docs/ - directory\n- hello.py - Python file (23 bytes)\n- LICENSE - license file\n- README-ja.md - Japanese README\n- 
README.md - main README\n- README-zh.md - Chinese README\n- requirements.txt - Python dependencies\n- skills/ - directory\n- web/ -
 directory\n\nI should present this information clearly to the user.\n', type='thinking'), 
 TextBlock(citations=None, text='命令执行成功！当前目录内容如下：\n\n| 类型 | 名称 | 大小 | 修改时间 |\n|------|------|------|----------|\n| 
 目录 | agents/ | 4096 | Mar 29 08:43 |\n| 目录 | docs/ | 4096 | Mar 29 08:43 |\n| 文件 | hello.py | 23 | Mar 29 21:13 |\n| 文件 | LICENSE | 
 1068 | Mar 29 08:43 |\n| 文件 | README-ja.md | 28151 | Mar 29 08:43 |\n| 文件 | README.md | 23811 | Mar 29 08:43 |\n| 文件 | README-zh.md | 22054 |
  Mar 29 08:43 |\n| 文件 | requirements.txt | 39 | Mar 29 08:43 |\n| 目录 | skills/ | 4096 | Mar 29 08:43 |\n| 目录 | web/ | 4096 | Mar 29 08:43 |\n\n共 4 个目录，6 个文件。', 
  type='text')]
***************
命令执行成功！当前目录内容如下：

| 类型 | 名称 | 大小 | 修改时间 |
|------|------|------|----------|
| 目录 | agents/ | 4096 | Mar 29 08:43 |
| 目录 | docs/ | 4096 | Mar 29 08:43 |
| 文件 | hello.py | 23 | Mar 29 21:13 |
| 文件 | LICENSE | 1068 | Mar 29 08:43 |
| 文件 | README-ja.md | 28151 | Mar 29 08:43 |
| 文件 | README.md | 23811 | Mar 29 08:43 |
| 文件 | README-zh.md | 22054 | Mar 29 08:43 |
| 文件 | requirements.txt | 39 | Mar 29 08:43 |
| 目录 | skills/ | 4096 | Mar 29 08:43 |
| 目录 | web/ | 4096 | Mar 29 08:43 |

共 4 个目录，6 个文件。

```

第一次请求，解析返回的结果，type是**type='tool_use'**。所以agent_loop()继续执行；第二次请求，解析返回的结果，type是**type='text'**，那么不是tool_use，满足stop条件，当前会话结束。

