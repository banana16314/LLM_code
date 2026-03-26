from openai import OpenAI

# 初始化客户端，指向本地 vLLM 服务
client = OpenAI(
    api_key="gass-wlw-ai110",  # vLLM 不验证密钥，可随意填写
    base_url="http://0.0.0.0:8888/v1"
)

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

# 输出响应内容
print(response.choices[0].message.content)