from anthropic import Anthropic

# 注意：base_url 需要指向 llama.cpp 的服务地址
# 通常 llama.cpp 的 Anthropic 兼容接口在 没有/v1 或根路径下，直接是端口号，也没有模型名字
client = Anthropic(
    base_url="http://0.0.0.0:8000/", 
    api_key="sk-no-key-required"  # 本地服务通常不需要真实 key
)

import time

start_time = time.perf_counter()  # 使用更高精度的计时器

message = client.messages.create(
    model="local-model",  # 模型名通常会被忽略，但必须传
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Hello, Claude!"}
    ]
)

end_time = time.perf_counter()

print(f"time cost: {end_time - start_time:.2f} seconds")
print("Chat response:", message.content)