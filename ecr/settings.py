from pathlib import Path
import os
from dotenv import load_dotenv
from datetime import timedelta

# -----------------------------------------------------------------------------
# المسارات الأساسية للمشروع
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# ✅ حمّل .env من جذر المشروع بشكل صريح (مهم على ويندوز)
load_dotenv(BASE_DIR / ".env")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def env_bool(name: str, default: bool = False) -> bool:
    """
    قراءة boolean من Environment بشكل آمن.
    يقبل: 1/0, true/false, yes/no, on/off
    """
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or not str(v).strip():
        return default
    try:
        return int(v)
    except ValueError:
        return default


# -----------------------------------------------------------------------------
# إعدادات التطوير (غير مناسبة للإنتاج)
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-this-in-production")

# ✅ DEBUG يقرأ من .env (DJANGO_DEBUG=True/False)
DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "192.168.8.41",
    "ecrzone.com",
    "www.ecrzone.com",
    ".onrender.com",
]


# -----------------------------------------------------------------------------
# التطبيقات المثبتة
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # REST API
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",

    # تطبيقات ECR
    "accounts.apps.AccountsConfig",
    "usergroups.apps.UsergroupsConfig",
    "regions.apps.RegionsConfig",
    "organizations.apps.OrganizationsConfig",
    "ecr_reports.apps.EcrReportsConfig",
    "cad_reports.apps.CadReportsConfig",
    "notifications.apps.NotificationsConfig",
    "responders.apps.RespondersConfig",
    "support_tickets.apps.SupportTicketsConfig",
]


# -----------------------------------------------------------------------------
# الوسطاء (Middleware)
# -----------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",

    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",

    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # ✅ منع الكاش لصفحات المستخدم المسجّل (يحل الرجوع للخلف بعد logout)
    "accounts.middleware.NoCacheForAuthenticatedMiddleware",
]


# -----------------------------------------------------------------------------
# إعداد الروابط والقوالب
# -----------------------------------------------------------------------------
ROOT_URLCONF = "ecr.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "ecr.wsgi.application"


# -----------------------------------------------------------------------------
# قاعدة البيانات (Dev: SQLite) (Prod: Postgres via DATABASE_URL)
# -----------------------------------------------------------------------------
# ✅ ملاحظة: يحتاج تثبيت dj-database-url و psycopg
import dj_database_url  # noqa: E402

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # ✅ إنتاج (Render غالبًا يمرر DATABASE_URL)
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=env_int("DB_CONN_MAX_AGE", 600),
            ssl_require=env_bool("DB_SSL_REQUIRE", True),
        )
    }
else:
    # ✅ تطوير محلي (SQLite)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# -----------------------------------------------------------------------------
# سياسة كلمات المرور (أمن سيبراني)
# -----------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# -----------------------------------------------------------------------------
# التعريب والتوقيت
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Riyadh"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("ar", "العربية"),
    ("en", "English"),
]

LOCALE_PATHS = [BASE_DIR / "locale"]


# -----------------------------------------------------------------------------
# ملفات static
# -----------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
# ✅ في الإنتاج (Render) غالبًا تحتاج STATIC_ROOT لـ collectstatic
STATIC_ROOT = BASE_DIR / "staticfiles"


# -----------------------------------------------------------------------------
# نوع المفتاح الأساسي الافتراضي
# -----------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"


# -----------------------------------------------------------------------------
# مسارات تسجيل الدخول/الخروج
# -----------------------------------------------------------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/accounts/dashboard/main/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

AUTHENTICATION_BACKENDS = [
    "accounts.auth_backend.NationalIdOrEmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# -----------------------------------------------------------------------------
# Session / Cookies Security
# -----------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# -----------------------------------------------------------------------------
# Cache (OTP / عام)
# -----------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "ecr-otp-cache",
    }
}


# -----------------------------------------------------------------------------
# REST Framework + JWT
# -----------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "user": os.getenv("API_THROTTLE_USER", "120/min"),
        "anon": os.getenv("API_THROTTLE_ANON", "30/min"),
    },
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env_int("JWT_ACCESS_MINUTES", 60)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env_int("JWT_REFRESH_DAYS", 14)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# -----------------------------------------------------------------------------
# إعدادات تتبع المستجيبين
# -----------------------------------------------------------------------------
RESPONDER_ONLINE_WINDOW_SECONDS = env_int("RESPONDER_ONLINE_WINDOW_SECONDS", 3500)


# -----------------------------------------------------------------------------
# إعدادات البريد الإلكتروني (SMTP) - تعمل للتطوير والإنتاج
# -----------------------------------------------------------------------------
# - الإنتاج: لو SMTP مفعل وكلمة المرور ناقصة => نوقف (عشان ما يصير فشل صامت)
# - التطوير: لو كلمة المرور ناقصة => نخلي Console backend (بدون كسر السيرفر)
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.hostinger.com")
EMAIL_PORT = env_int("EMAIL_PORT", 465)  # ✅ Hostinger الشائع: 465 SSL (أو 587 TLS)

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "support@ecrzone.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")

EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)

# ✅ لو ما تحددت صراحة، اختر تلقائيًا حسب البورت
if (os.getenv("EMAIL_USE_TLS") is None) and (os.getenv("EMAIL_USE_SSL") is None):
    if EMAIL_PORT == 465:
        EMAIL_USE_SSL = True
        EMAIL_USE_TLS = False
    elif EMAIL_PORT == 587:
        EMAIL_USE_TLS = True
        EMAIL_USE_SSL = False

# ✅ منع تعارض TLS/SSL بدون كسر الـ deploy
if EMAIL_USE_TLS and EMAIL_USE_SSL:
    if EMAIL_PORT == 465:
        EMAIL_USE_TLS = False
    else:
        EMAIL_USE_SSL = False

# ✅ في التطوير: إذا ما فيه كلمة مرور، لا نوقف السيرفر
if DEBUG and not EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")

# ✅ في الإنتاج: كلمة المرور لازم تكون موجودة لو SMTP شغال
if (not DEBUG) and (EMAIL_BACKEND.endswith("smtp.EmailBackend")) and not EMAIL_HOST_PASSWORD:
    raise ValueError("EMAIL_HOST_PASSWORD is missing. Please set it in your environment variables (.env / Render env).")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"ECR <{EMAIL_HOST_USER}>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 20)


# -----------------------------------------------------------------------------
# إعدادات أمان للإنتاج (تُفعّل تلقائيًا عند DEBUG=False)
# -----------------------------------------------------------------------------
if not DEBUG:
    # ✅ في الإنتاج: اجبر HTTPS (لا تفعله في التطوير)
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"

    # HSTS
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
else:
    # ✅ في التطوير: لا تحول لـ HTTPS أبدًا
    SECURE_SSL_REDIRECT = False
    # DEBUG_PROPAGATE_EXCEPTIONS = False


# -----------------------------------------------------------------------------
# Google Maps
# -----------------------------------------------------------------------------
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")


# -----------------------------------------------------------------------------
# Media
# -----------------------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# -----------------------------------------------------------------------------
# دعم فني
# -----------------------------------------------------------------------------
SUPPORT_TICKETS_SLA_STOP_DURING_PAUSE = True