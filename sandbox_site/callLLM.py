import os
from openai import OpenAI

def call_deepseek_api(system_content, user_content):
        # Please install OpenAI SDK first: `pip3 install openai`
    api_key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未设置：请在服务器环境变量或 .env 中配置 DeepSeek API Key。")
    base_url = (os.environ.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com").strip()
    client = OpenAI(
        api_key=api_key,
        base_url=base_url)

    response = client.chat.completions.create(
        model=(os.environ.get("DEEPSEEK_MODEL") or "deepseek-reasoner").strip(),
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        stream=False
    )
    return response.choices[0].message.content or ""
