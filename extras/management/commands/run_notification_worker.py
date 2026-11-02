import signal
from threading import Event

from django.core.management.base import BaseCommand

from extras.queue import notification_worker_loop


class Command(BaseCommand):
    help = "Run the single MediMart WhatsApp retry worker until stopped."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=15)

    def handle(self, *args, **options):
        stop_event = Event()
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
        self.stdout.write(self.style.SUCCESS("MediMart notification worker is running."))
        notification_worker_loop(stop_event, max(5, options["interval"]))
