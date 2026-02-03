import os
import requests

import json
from openai import OpenAI
API=os.getenv('DEEPSEEK_API_KEY')
url='https://api.deepseek.com/v1'
model='deepseek-chat'

client=OpenAI(api_key=API, base_url=url)
messages=[{"role":"user","content":"hello"}]

resp=client.chat.completions.create(model=model, messages=messages, temperature=0.7, max_tokens=128)
print(resp)




