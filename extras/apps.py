from django.apps import AppConfig
import os
import sys
import threading
from threading import Event


class ExtrasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "extras"

    def ready(self):
        if os.getenv("NOTIFICATION_WORKER_AUTOSTART", "false").lower() not in {"1", "true", "yes", "on"}:
            return
        if "test" in sys.argv:
            return
        if "runserver" not in sys.argv or os.getenv("RUN_MAIN") != "true":
            return
        from .queue import notification_worker_loop

        stop_event = Event()
        interval = int(os.getenv("NOTIFICATION_WORKER_INTERVAL_SECONDS", "15"))
        worker = threading.Thread(
            target=notification_worker_loop,
            args=(stop_event, max(5, interval)),
            name="medimart-notification-worker",
            daemon=True,
        )
        worker.start()
