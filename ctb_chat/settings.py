from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-only-unsafe-key")
'''
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("DJANGO_SECRET_KEY is required")
'''
DEBUG = os.getenv("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ctb_chat_rate_limit",
    }
}

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "chat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "ctb_chat.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "ctb_chat.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = []

LANGUAGE_CODE = "zh-hans"
TIME_ZONE = "Asia/Shanghai"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/conversations/"
LOGOUT_REDIRECT_URL = "/login/"

LM_PROVIDER = os.getenv("LM_PROVIDER", "deepseek")

# DeepSeek (OpenAI-compatible) defaults
LM_BASE_URL = os.getenv("LM_BASE_URL", "https://api.deepseek.com/v1")
LM_API_KEY = os.getenv("LM_API_KEY", os.getenv("DEEPSEEK_API_KEY", "sk-2e86fa08baf7430aa0e695a4a359c551"))

# Default model: DeepSeek Chat (override via env LM_MODEL)
LM_MODEL = os.getenv("LM_MODEL", "deepseek-chat")

LM_TIMEOUT = int(os.getenv("LM_TIMEOUT", "120"))
LM_MAX_TOKENS = int(os.getenv("LM_MAX_TOKENS", "512"))

MAX_CONTEXT_BUDGET = int(os.getenv("MAX_CONTEXT_BUDGET", "2500"))
KEEP_LAST_TURNS = int(os.getenv("KEEP_LAST_TURNS", "10"))

SUMMARY_ENABLED = os.getenv("SUMMARY_ENABLED", "1") == "1"
SUMMARY_EVERY_TURNS = int(os.getenv("SUMMARY_EVERY_TURNS", "8"))
SUMMARY_CONTEXT_TURNS = int(os.getenv("SUMMARY_CONTEXT_TURNS", "6"))
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "220"))

SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 10
MAX_INPUT_CHARS = int(os.getenv("MAX_INPUT_CHARS", "1000"))
