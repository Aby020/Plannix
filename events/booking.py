"""Transactional booking creation with capacity and uniqueness guards.

Every booking flows through ``create_booking`` so business rules are
enforced in one place, wrapped in an atomic transaction with row-level
locking on the target Event.
"""
from datetime import date

from django.db import transaction

from .models import Event, EventBooking


def create_booking(event, attendee, name, email, number, event_date, event_location=None):
    """Create a new booking inside a transaction with row-level locking.

    Parameters
    ----------
    event : Event
        The event to book (will be locked with ``select_for_update``).
    attendee : User
        The authenticated user making the booking.
    name, email, number : str
        Contact details snapshot.
    event_date : date
        The requested booking date.
    event_location : str, optional
        Override location; defaults to ``event.location``.

    Returns
    -------
    EventBooking
        The newly created booking with status ``pending``.

    Raises
    ------
    ValueError
        On any business-rule violation (wrong status, capacity full,
        duplicate active booking, past date).
    """
    with transaction.atomic():
        # Lock the event row to prevent race conditions on capacity checks.
        locked_event = Event.objects.select_for_update().get(pk=event.pk)

        # --- Status guard ---
        if locked_event.status != 'live':
            raise ValueError('This event is not currently available for booking.')

        # --- Past-date guard ---
        if event_date < date.today():
            raise ValueError('You cannot book a date in the past.')

        # --- Capacity guard ---
        active_bookings = EventBooking.objects.filter(
            event=locked_event,
            status__in=['pending', 'confirmed'],
        ).count()

        if locked_event.capacity is not None and active_bookings >= locked_event.capacity:
            raise ValueError('This event has reached its maximum capacity.')

        # --- Unique active-booking guard ---
        if EventBooking.objects.filter(
            event=locked_event,
            attendee=attendee,
        ).exclude(status='cancelled').exists():
            raise ValueError('You already have an active booking for this event.')

        # --- Create booking ---
        booking = EventBooking.objects.create(
            event=locked_event,
            attendee=attendee,
            name=name,
            email=email,
            number=number,
            event_title=locked_event.title,
            price=locked_event.price,
            event_location=event_location or locked_event.location,
            event_date=event_date,
            status='pending',
        )

    return booking
