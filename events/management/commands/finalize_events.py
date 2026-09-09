"""Move expired LIVE events to COMPLETED and finalize their bookings.

Usage:
    python manage.py finalize_events

Run this via cron or as a periodic task. It:
- Finds all LIVE events whose end_at < now
- Calls services.complete() to transition to COMPLETED
- Confirmed bookings are marked COMPLETED
- Pending bookings are marked CANCELLED

Idempotent: only processes events still in 'live' status.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone

from events.models import Event
from events import services


class Command(BaseCommand):
    help = 'Complete expired LIVE events and finalize their bookings.'

    def handle(self, *args, **options):
        now = timezone.now()
        expired = Event.objects.filter(
            status='live',
            end_at__isnull=False,
            end_at__lt=now,
        )

        count = 0
        for event in expired:
            try:
                services.complete(event)
                count += 1
                self.stdout.write(f'  completed: "{event.title}" (end_at={event.end_at})')
            except ValueError as e:
                self.stdout.write(self.style.WARNING(
                    f'  skipped: "{event.title}" — {e}',
                ))

        if count:
            self.stdout.write(self.style.SUCCESS(f'Finalized {count} event(s).'))
        else:
            self.stdout.write('No expired events to finalize.')
