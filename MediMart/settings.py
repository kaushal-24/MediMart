"""Django settings for MediMart."""

from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured
from dotenv import dotenv_values, load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")
_DOTENV_VALUES = dotenv_values(BASE_DIR / ".env")


def env_value(name, default=""):
    """Use a non-empty process value, then fall back to the local .env file."""
    value = os.getenv(name)
    if value is not None and value.strip():
        return value
    return _DOTENV_VALUES.get(name) or default


def env_bool(name, default=False):
    return os.getenv(name, str(default)).lower() in {"true", "1", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def env_int(name, default):
    value = os.getenv(name, str(default)).strip()
    return int(value) if value else default


DEBUG = env_bool("DEBUG", True)

SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-this-secret-key")
if not DEBUG and SECRET_KEY == "dev-only-change-this-secret-key":
    raise ImproperlyConfigured("SECRET_KEY must be configured when DEBUG=False.")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost,")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")


INSTALLED_APPS = [
    "accounts",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
    "products",
    "vendors",
    "cart",
    "prescriptions",
    "orders",
    "reviews",
    "dashboards",
    "extras",
    "healthcare",
    "assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.account_security.ActiveAccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "MediMart.urls"

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
                "accounts.context_processors.dashboard_access",
                "core.context_processors.site_location",
                "cart.context_processors.navigation_counts",
                "extras.context_processors.in_app_notifications",
            ],
        },
    },
]

WSGI_APPLICATION = "MediMart.wsgi.application"


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env_value("DB_NAME", "medimart"),
        "USER": env_value("DB_USER", "root"),
        "PASSWORD": env_value("DB_PASSWORD"),
        "HOST": env_value("DB_HOST", "127.0.0.1"),
        "PORT": env_value("DB_PORT", "3306"),
        "OPTIONS": {
            "charset": "utf8mb4",
        },
    }
}


AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


LANGUAGE_CODE = "en-us"

TIME_ZONE = "Asia/Kolkata"

USE_I18N = True

USE_TZ = True


STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
PRIVATE_MEDIA_ROOT = BASE_DIR / "private_media"

DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 12 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 5 * 1024 * 1024)

USE_CLOUD_MEDIA = env_bool("USE_CLOUD_MEDIA", False)
MEDIA_CLOUD_PROVIDER = os.getenv("MEDIA_CLOUD_PROVIDER", "s3")
MEDIA_CLOUD_BUCKET = os.getenv("MEDIA_CLOUD_BUCKET", "")
MEDIA_CLOUD_CONNECTION_OPTIONS = {
    key: value
    for key, value in {
        "access_key": os.getenv("AWS_ACCESS_KEY_ID"),
        "secret_key": os.getenv("AWS_SECRET_ACCESS_KEY"),
        "region_name": os.getenv("AWS_S3_REGION_NAME"),
        "endpoint_url": os.getenv("AWS_S3_ENDPOINT_URL"),
    }.items()
    if value
}

if USE_CLOUD_MEDIA:
    if MEDIA_CLOUD_PROVIDER.lower() != "s3":
        raise ValueError("MEDIA_CLOUD_PROVIDER must be 's3' when USE_CLOUD_MEDIA is enabled.")
    if not MEDIA_CLOUD_BUCKET:
        raise ValueError("MEDIA_CLOUD_BUCKET is required when USE_CLOUD_MEDIA is enabled.")

    INSTALLED_APPS.append("storages")
    s3_options = {
        "bucket_name": MEDIA_CLOUD_BUCKET,
        "location": "public",
        "default_acl": None,
        "file_overwrite": False,
        "querystring_auth": False,
        "object_parameters": {
            "CacheControl": "public, max-age=31536000, immutable",
        },
    }
    s3_options.update(MEDIA_CLOUD_CONNECTION_OPTIONS)
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": s3_options,
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.ManifestStaticFilesStorage",
        },
    }


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "core:home"
PASSWORD_RESET_TIMEOUT = env_int("PASSWORD_RESET_TIMEOUT", 3600)
SESSION_COOKIE_AGE = env_int("SESSION_COOKIE_AGE", 4 * 60 * 60)
SESSION_EXPIRE_AT_BROWSER_CLOSE = env_bool("SESSION_EXPIRE_AT_BROWSER_CLOSE", False)

EMAIL_BACKEND = os.getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "MediMart <medimart.notifications@gmail.com>")
FIELD_ENCRYPTION_KEY = os.getenv("FIELD_ENCRYPTION_KEY", "")
if not DEBUG and not FIELD_ENCRYPTION_KEY:
    raise ImproperlyConfigured("FIELD_ENCRYPTION_KEY must be configured when DEBUG=False.")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)

RAZORPAY_KEY_ID = env_value("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = env_value("RAZORPAY_KEY_SECRET")
RAZORPAY_CURRENCY = env_value("RAZORPAY_CURRENCY", "INR")
RAZORPAY_WEBHOOK_SECRET = env_value("RAZORPAY_WEBHOOK_SECRET")
PAYMENT_RESERVATION_MINUTES = env_int("PAYMENT_RESERVATION_MINUTES", 20)

# Delivery fee settings — toggle FREE_DELIVERY=true in .env for testing
DELIVERY_FEE = env_int("DELIVERY_FEE", 49)
FREE_DELIVERY = env_bool("FREE_DELIVERY", False)
COD_MAX_ORDER_VALUE = env_int("COD_MAX_ORDER_VALUE", 5000)
COD_BLOCKED_PINCODES = set(env_list("COD_BLOCKED_PINCODES"))

CHATBOT_API_URL = env_value("CHATBOT_API_URL", "https://api.groq.com/openai/v1").strip()
CHATBOT_API_KEY = env_value("CHATBOT_API_KEY")
CHATBOT_PROVIDER = env_value("CHATBOT_PROVIDER", "openai_compatible").strip().casefold()
CHATBOT_MODEL = env_value("CHATBOT_MODEL", "openai/gpt-oss-120b")
CHATBOT_MODELS = [
    model.strip()
    for model in env_value(
        "CHATBOT_MODELS",
        "openai/gpt-oss-120b",
    ).split(",")
    if model.strip()
]
if CHATBOT_MODEL and CHATBOT_MODEL not in CHATBOT_MODELS:
    CHATBOT_MODELS.insert(0, CHATBOT_MODEL)
CHATBOT_MODEL_COOLDOWN_SECONDS = env_int("CHATBOT_MODEL_COOLDOWN_SECONDS", 60)
CHATBOT_THINKING_LEVEL = env_value("CHATBOT_THINKING_LEVEL", "minimal").strip().casefold()
CHATBOT_TIMEOUT_SECONDS = env_int("CHATBOT_TIMEOUT_SECONDS", 30)
CHATBOT_MAX_INPUT_CHARS = env_int("CHATBOT_MAX_INPUT_CHARS", 1000)
CHATBOT_MAX_OUTPUT_CHARS = env_int("CHATBOT_MAX_OUTPUT_CHARS", 2000)
CHATBOT_MAX_OUTPUT_TOKENS = env_int("CHATBOT_MAX_OUTPUT_TOKENS", 500)
CHATBOT_RESPONSE_CACHE_SECONDS = env_int("CHATBOT_RESPONSE_CACHE_SECONDS", 300)
CHATBOT_SEARCH_CACHE_SECONDS = env_int("CHATBOT_SEARCH_CACHE_SECONDS", 180)
CHATBOT_FALLBACK_CACHE_SECONDS = env_int("CHATBOT_FALLBACK_CACHE_SECONDS", 30)
CHATBOT_DEDUP_LOCK_SECONDS = env_int("CHATBOT_DEDUP_LOCK_SECONDS", 45)

GEOCODING_REVERSE_URL = os.getenv(
    "GEOCODING_REVERSE_URL",
    "https://nominatim.openstreetmap.org/reverse",
)
GEOCODING_USER_AGENT = os.getenv(
    "GEOCODING_USER_AGENT",
    "MediMart/1.0 (development; contact: medimart.notifications@gmail.com)",
)
GEOCODING_TIMEOUT_SECONDS = env_int("GEOCODING_TIMEOUT_SECONDS", 5)
TRUSTED_PROXY_COUNT = env_int("TRUSTED_PROXY_COUNT", 0)
RATE_LIMIT_FAIL_CLOSED = env_bool("RATE_LIMIT_FAIL_CLOSED", True)

SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = env_bool("SESSION_COOKIE_HTTPONLY", True)
SESSION_COOKIE_SAMESITE = env_value("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env_value("CSRF_COOKIE_SAMESITE", "Lax")

if env_bool("USE_X_FORWARDED_PROTO", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "medimart-local-cache",
        "TIMEOUT": 300,
    }
}

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}
