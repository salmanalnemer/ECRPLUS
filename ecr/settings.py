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
# إعدادات التطوير (غير مناسبة للإنتاج)
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "django-insecure-change-this-in-production")

# ✅ DEBUG يقرأ من .env (DJANGO_DEBUG=True/False)
DEBUG = os.getenv("DJANGO_DEBUG", "False").strip().lower() == "true"

ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "192.168.8.41",
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
# قاعدة البيانات
# -----------------------------------------------------------------------------
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
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", "14"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# -----------------------------------------------------------------------------
# إعدادات تتبع المستجيبين
# -----------------------------------------------------------------------------
RESPONDER_ONLINE_WINDOW_SECONDS = int(os.getenv("RESPONDER_ONLINE_WINDOW_SECONDS", "3500"))

# -----------------------------------------------------------------------------
# إعدادات البريد الإلكتروني (SMTP)
# -----------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.hostinger.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_USE_SSL = os.getenv("EMAIL_USE_SSL", "False").lower() == "true"

if EMAIL_USE_TLS and EMAIL_USE_SSL:
    raise ValueError("Invalid email config: Do not enable both EMAIL_USE_TLS and EMAIL_USE_SSL at the same time.")

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "support@ecrzone.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")
if not EMAIL_HOST_PASSWORD:
    raise ValueError("EMAIL_HOST_PASSWORD is missing. Please set it in your .env file.")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", f"ECR <{EMAIL_HOST_USER}>")
SERVER_EMAIL = os.getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "20"))

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
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "0"))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.getenv("SECURE_HSTS_INCLUDE_SUBDOMAINS", "False").lower() == "true"
    SECURE_HSTS_PRELOAD = os.getenv("SECURE_HSTS_PRELOAD", "False").lower() == "true"
else:
    # ✅ في التطوير: لا تحول لـ HTTPS أبدًا
    SECURE_SSL_REDIRECT = False

    # ✅ (اختياري) إذا تبي تظهر صفحات 404/500 المخصصة في التطوير:
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