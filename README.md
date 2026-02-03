# LM_chat (Django + LLM)  + Archive + Noir UI

## 你遇到的错误：no such table: chat_conversation
本项目已内置 chat 的 migrations（chat/migrations/0001_initial.py），按下面步骤执行 migrate 即可自动创建表。

## 运行
1) 启动 Ollama，并开启 Local Server（默认 http://127.0.0.1:1234）
2) 启动 Django
```bash
cd LM_chat
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

## 访问
- 注册:  http://127.0.0.1:8000/register/
- 登录:  http://127.0.0.1:8000/login/
- 会话:  http://127.0.0.1:8000/conversations/
