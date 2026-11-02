import json
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand

from core.monitoring import health_snapshot


class Command(BaseCommand):
    help = "Check MediMart health and optionally notify an alert webhook."

    def handle(self, *args, **options):
        snapshot = health_snapshot()
        payload = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
        self.stdout.write(json.dumps(snapshot, indent=2, sort_keys=True))
        webhook = str(getattr(settings, "MONITORING_ALERT_WEBHOOK", "") or "").strip()
        if snapshot["status"] != "ok" and webhook:
            try:
                request = Request(webhook, data=payload, headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=10):
                    pass
            except Exception as exc:
                self.stderr.write(f"Alert webhook failed: {exc.__class__.__name__}")
        if snapshot["status"] != "ok":
            raise SystemExit(1)
