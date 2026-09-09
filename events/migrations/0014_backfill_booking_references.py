# Backfill booking_reference for EventBooking rows created before the field existed.
# NULLs are left untouched (only NULL values remain); the save() override on the
# model generates PXN- references for all new bookings going forward.

import uuid

from django.db import migrations


def _generate_reference():
    return f'PXN-{uuid.uuid4().hex[:8].upper()}'


def forwards(apps, schema_editor):
    EventBooking = apps.get_model('events', 'EventBooking')
    # Only update rows that still have a NULL booking_reference.
    bookings = EventBooking.objects.filter(booking_reference__isnull=True)
    updates = []
    for booking in bookings:
        booking.booking_reference = _generate_reference()
        updates.append(booking)
    if updates:
        EventBooking.objects.bulk_update(updates, ['booking_reference'], batch_size=500)


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0013_eventbooking_booking_reference_bookingpayment'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
