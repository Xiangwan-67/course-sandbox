import os
from openai import OpenAI

def call_deepseek_api(system_content, user_content):
        # Please install OpenAI SDK first: `pip3 install openai`
    client = OpenAI(
        api_key="sk-65737ebc860a40f89ddb02c1dc0b57af",
        base_url="https://api.deepseek.com")

    response = client.chat.completions.create(
        model="deepseek-reasoner",
        messages=[
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ],
        stream=False
    )
    return response.choices[0].message.content or ""
