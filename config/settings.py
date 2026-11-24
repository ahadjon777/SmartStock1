import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
DEBUG = os.environ.get("DEBUG", "1") == "1"
ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "inventory",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "inventory.middleware.ThreatMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_IDS = [int(i) for i in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if i.strip()]

# Xavfsizlik: faqat bitta ishonchli proksi (nginx, cloudflared, ngrok) orqasida TRUST_X_FORWARDED_FOR=1 qiling
TRUST_X_FORWARDED_FOR = os.environ.get("TRUST_X_FORWARDED_FOR", "0") == "1"
SECURITY_ALLOWLIST_IPS = [i.strip() for i in os.environ.get("SECURITY_ALLOWLIST_IPS", "").split(",") if i.strip()]
SECURITY_FAIL_LIMIT = int(os.environ.get("SECURITY_FAIL_LIMIT", "5"))        # bitta IP: 5 daqiqada
SECURITY_USER_FAIL_LIMIT = int(os.environ.get("SECURITY_USER_FAIL_LIMIT", "8"))  # bitta login: 10 daqiqada
SECURITY_SCAN_LIMIT = int(os.environ.get("SECURITY_SCAN_LIMIT", "30"))       # bitta IP: 1 daqiqada 403/404

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "scan"
LOGOUT_REDIRECT_URL = "login"
