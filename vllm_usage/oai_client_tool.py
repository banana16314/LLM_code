import os
import json
import subprocess
import time
from pathlib import Path
from openai import OpenAI

# --- 配置区 ---
# 初始化客户端，指向本地 vLLM 服务
client = OpenAI(
    api_key="MYKEY",  # vLLM 不验证密钥
    base_url="http://0.0.0.0:8000/v1"
)
MODEL_ID = "Qwen"  # 替换为 vLLM 中加载的具体模型名称
WORKDIR = Path.cwd()
SYSTEM_PROMPT = f"You are a coding agent at {WORKDIR}. Use tools to solve tasks. Act, don't explain."

# --- 工具函数定义 (保留脚本2逻辑) ---

def safe_path(p: str) -> Path:
    path = (WORKDIR / p).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError(f"Path escapes workspace: {p}")
    return path

def run_bash(command: str) -> str:
    dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
    if any(d in command for d in dangerous):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(command, shell=True, cwd=WORKDIR,
                           capture_output=True, text=True, timeout=120)
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: Timeout (120s)"

def run_read(path: str, limit: int = None) -> str:
    try:
        text = safe_path(path).read_text()
        lines = text.splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more lines)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"

def run_write(path: str, content: str) -> str:
    try:
        fp = safe_path(path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"

# --- OpenAI 格式的工具定义 ---

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": "Run a shell command.",
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write content to file.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"}
                },
                "required": ["path", "content"]
            }
        }
    }
]

TOOL_HANDLERS = {
    "bash": lambda kw: run_bash(kw["command"]),
    "read_file": lambda kw: run_read(kw["path"], kw.get("limit")),
    "write_file": lambda kw: run_write(kw["path"], kw["content"]),
}

# --- 核心 Agent 循环 ---

def agent_loop(messages: list):
    while True:
        start_time = time.perf_counter()
        
        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + messages,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.7
        )
        
        end_time = time.perf_counter()
        print(f"  [Time cost: {end_time - start_time:.2f}s]")

        response_message = response.choices[0].message
        messages.append(response_message) # 必须将 Assistant 的回复（含 tool_calls）加入历史

        # 检查是否需要调用工具
        if not response_message.tool_calls:
            print(f"Assistant: {response_message.content}")
            break

        # 处理并执行工具调用
        for tool_call in response_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            print(f"\033[94m> Executing tool: {function_name}({function_args})\033[0m")
            
            handler = TOOL_HANDLERS.get(function_name)
            if handler:
                result = handler(function_args)
            else:
                result = f"Error: Tool {function_name} not found"
            
            print(f"  Result: {str(result)[:100]}...")

            # 将工具执行结果存入消息历史
            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(result),
            })

if __name__ == "__main__":
    history = []
    print("\033[32m--- vLLM Tool Calling Client Started ---\033[0m")
    while True:
        try:
            query = input("\n\033[36mUser >> \033[0m")
        except (EOFError, KeyboardInterrupt):
            break
            
        if query.strip().lower() in ("q", "exit", "quit"):
            break
            
        history.append({"role": "user", "content": query})
        agent_loop(history)