# qwen3.5思考模式的开关
qwen3.5默认开启思考模式，而且，qwen3的/no_think在qwen3.5失效。下面是qwen3.5思考模式的开关。

## 官方模板
官方的chat_template.jinja最后几行如下：
```jinja
{%- if enable_thinking is defined and enable_thinking is false %}
    {{- '<think>\n\n</think>\n\n' }}  {# 情况 A：思考关闭 #}
{%- else %}
    {{- '<think>\n' }}               {# 情况 B：思考开启（默认）#}
{%- endif %}
```
- 情况 B（默认/开启）：模板以 <think>\n 结尾。

    - 模型看到的最后内容是“思考标签已打开，但未关闭”。
    - 模型行为：模型会继续生成内容，直到它自己生成 </think> 为止。这部分生成的内容就是“思考过程”。

- 情况 A（关闭）：模板直接输出了完整的 <think>\n\n</think>\n\n。

    - 模型看到的最后内容是“思考标签已打开且立即关闭”。
    - 模型行为：模型认为思考阶段已经结束，接下来生成的内容直接就是正式回答，不会包含在 <think> 标签内。

## 使用官方模板，开启和关闭思考模式
使用openai client的请求测试如下:
```python 
from openai import OpenAI
# Configured by environment variables


client = OpenAI(api_key="xxx", base_url="xxxx")


messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "解释量子计算。100字以内。"
            }
        ]
    }
]

chat_response = client.chat.completions.create(
    model="Qwen",
    messages=messages,
    max_tokens=32768,
    temperature=0.7,
    top_p=0.8,
    presence_penalty=1.5,
    extra_body={
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }, 
)
print("Chat response:", chat_response)
```

通过请求头添加一个extra_body实现。
```python    
extra_body={
        "top_k": 20,
        "chat_template_kwargs": {"enable_thinking": False},
    }, 
```

## 修改官方模式，直接关闭思考模式

移除了条件判断，强制固定为情况 A：
```jinja
{%- if add_generation_prompt %}
    {{- '<|im_start|>assistant\n' }}
    {{- '<think>\n\n</think>\n\n' }}  {# 强制固定为思考关闭状态 #}
{%- endif %}
```
- 效果：无论外部参数 enable_thinking 是什么，模板发送给模型的前缀永远包含闭合的 </think>。
- 结果：模型在开始生成时，发现思考块已经闭合，因此没有机会也没有必要在 <think> 和 </think> 之间生成任何内容。它只能直接在 </think>\n\n 之后生成最终答案。


严格来说，这并没有移除模型内部的推理能力，而是在输入端禁用了思考格式的触发。

    - 原本：模型生成 <think>...推理内容...</think> 答案。
    - 修改后：模型生成 <think></think> 答案（思考块为空，由模板预填）。
    - 用户感知：看到的输出中没有冗长的思考过程，直接得到了结果，达到了“去除思考模式”的使用效果。
  