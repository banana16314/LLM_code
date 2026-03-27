from openai import OpenAI

# 初始化客户端，指向本地 vLLM 服务
client = OpenAI(
    api_key="MYKEY",  # vLLM 不验证密钥，可随意填写
    base_url="http://0.0.0.0:8888/v1"
)

import time

start_time = time.perf_counter()  # 使用更高精度的计时器

# 发送聊天请求
response = client.chat.completions.create(
    model="Qwen",  # 替换为 vLLM 中加载的模型名称
    messages=[
        {"role": "system", "content": "你是一个有帮助的助手。"},
        {"role": "user", "content": "你好，请介绍一下你自己。100字以内。"}
    ],
    temperature=0.7,
    max_tokens=512
)

end_time = time.perf_counter()

print(f"time cost: {end_time - start_time:.2f} seconds")
print("Chat response:", chat_response)

# vllm 0.18, dgx spark, no thinking
### qwen3.5-27B-fp8, avg 11s, first inference: 69s
### qwen3.5-35B-a3b, avg 1.8s, first inference: 72s