from .settings import *  # noqa: F403

# Tests intentionally use the same MySQL backend as development and production.
# Django creates an isolated test database (test_<DB_NAME>) for each run.

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
PRIVATE_MEDIA_ROOT = BASE_DIR / "test_private_media"  # noqa: F405
