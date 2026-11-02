import logging
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.db import connection


logger = logging.getLogger("medimart.monitoring")


def health_snapshot(*, include_notification_queue=True):
    """Return cheap checks suitable for an uptime probe or Task Scheduler."""
    checks = {
        "database": {"ok": False},
        "cache": {"ok": False},
        "private_media": {"ok": False},
        "notification_queue": {"ok": False},
    }
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            checks["database"] = {"ok": cursor.fetchone()[0] == 1}
    except Exception as exc:
        checks["database"] = {"ok": False, "error": exc.__class__.__name__}
    try:
        cache.set("health:ready", "ok", 10)
        checks["cache"] = {"ok": cache.get("health:ready") == "ok"}
    except Exception as exc:
        checks["cache"] = {"ok": False, "error": exc.__class__.__name__}
    private_root = Path(getattr(settings, "PRIVATE_MEDIA_ROOT", settings.MEDIA_ROOT))
    checks["private_media"] = {"ok": private_root.exists() and private_root.is_dir()}
    if checks["database"]["ok"] and include_notification_queue:
        try:
            from extras.models import NotificationDelivery
            dead_letters = NotificationDelivery.objects.filter(status=NotificationDelivery.Status.DEAD_LETTER).count()
            checks["notification_queue"] = {"ok": dead_letters == 0, "dead_letters": dead_letters}
        except Exception as exc:
            checks["notification_queue"] = {"ok": False, "error": exc.__class__.__name__}
    if not include_notification_queue:
        checks.pop("notification_queue", None)
    ok = all(item.get("ok") for item in checks.values())
    if not ok:
        logger.error("MediMart health check failed: %s", checks)
    return {"status": "ok" if ok else "unavailable", "checks": checks}
