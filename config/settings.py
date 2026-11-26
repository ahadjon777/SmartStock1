import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _env_list(name, default=""):
    return [i.strip() for i in os.environ.get(name, default).split(",") if i.strip()]


DEBUG = os.environ.get("DEBUG", "1") == "1"

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise ImproperlyConfigured("DEBUG=0 bo'lsa .env faylida uzun tasodifiy SECRET_KEY bo'lishi shart.")

# Lokal (DEBUG=1) rejimda hamma host; DEBUG=0 da faqat .env dagi ALLOWED_HOSTS (yoki localhost)
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "*" if DEBUG else "localhost,127.0.0.1")
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS")  # masalan: https://sizning-domen.uz

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
    "whitenoise.middleware.WhiteNoiseMiddleware",  # statik fayllar (QR skaner kutubxonasi, admin CSS) DEBUG=0 da ham ishlaydi
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
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True  # collectstatic qilmasdan ham fayllarni to'g'ridan-to'g'ri topadi
WHITENOISE_AUTOREFRESH = DEBUG
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_IDS = [int(i) for i in os.environ.get("TELEGRAM_ADMIN_IDS", "").split(",") if i.strip()]
SITE_URL = os.environ.get("SITE_URL", "").strip().rstrip("/")  # botdagi "Saytni ochish" tugmasi uchun (ixtiyoriy)

# Xavfsizlik: faqat bitta ishonchli proksi (nginx, cloudflared, ngrok) orqasida TRUST_X_FORWARDED_FOR=1 qiling
TRUST_X_FORWARDED_FOR = os.environ.get("TRUST_X_FORWARDED_FOR", "0") == "1"
SECURITY_ALLOWLIST_IPS = _env_list("SECURITY_ALLOWLIST_IPS")
SECURITY_FAIL_LIMIT = int(os.environ.get("SECURITY_FAIL_LIMIT", "5"))        # bitta IP: 5 daqiqada
SECURITY_USER_FAIL_LIMIT = int(os.environ.get("SECURITY_USER_FAIL_LIMIT", "8"))  # bitta login: 10 daqiqada
SECURITY_SCAN_LIMIT = int(os.environ.get("SECURITY_SCAN_LIMIT", "30"))       # bitta IP: 1 daqiqada 403/404

# HTTPS (cloudflared, ngrok, nginx) orqali ishlayotgan bo'lsangiz .env da HTTPS=1 qo'ying
if os.environ.get("HTTPS", "0") == "1":
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    if TRUST_X_FORWARDED_FOR:
        # Proksi TLS'ni o'zi tugatadi: Django so'rovni HTTPS deb bilishi uchun (aks holda CSRF "Origin" tekshiruvi 403 beradi)
        SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

OVERDUE_DAYS = int(os.environ.get("OVERDUE_DAYS", "7"))  # shundan ko'p kun tadbirda tursa, panelda «uzoq vaqt» deb belgilanadi

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "scan"
LOGOUT_REDIRECT_URL = "login"
