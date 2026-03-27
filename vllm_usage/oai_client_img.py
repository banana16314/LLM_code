# openai_client_single_img.py
from openai import OpenAI
# Configured by environment variables
import base64

client = OpenAI(api_key="MYKEY", base_url="http://0.0.0.0:8000/v1")


def image_to_base64(image_path):
    """将单个图片转换为 Base64 字符串"""
    with open(image_path, "rb") as image_file:
        encoded_string = base64.b64encode(image_file.read())
    return encoded_string.decode('utf-8')

img_path = "/home/trimps/mllm/RealWorld-04.png"  
image_b64 = image_to_base64(img_path)
messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "image_url",
                "image_url": {
                    # "url": "https://qianwen-res.oss-accelerate.aliyuncs.com/Qwen3.5/demo/RealWorld/RealWorld-04.png"
                    "url": f"data:image/jpg;base64,{image_b64}",
                }
            },
            {
                "type": "text",
                "text": "描述这张图像。100字以内。"
            }
        ]
    }
]
import time

start_time = time.perf_counter()  # 使用更高精度的计时器

chat_response = client.chat.completions.create(
    model="Qwen",
    messages=messages,
    max_tokens=32768,
    temperature=0.7,
    top_p=0.8,
    presence_penalty=1.5,
    # extra_body={
    #     "top_k": 20,
    #     "chat_template_kwargs": {"enable_thinking": False},
    # }, 
)

end_time = time.perf_counter()

print(f"time cost: {end_time - start_time:.2f} seconds")
print("Chat response:", chat_response)

# vllm 0.18, dgx spark, no thinking
### qwen3.5-27B-fp8, avg 11s, first inference: 69s
### qwen3.5-35B-a3b, avg 1.8s, first inference: 72s