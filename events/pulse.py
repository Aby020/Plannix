"""Deterministic event pulse functions — no AI, no charting libraries.

Provides health indicators and metrics for events, reusable for the
organizer dashboard and future pulse UI.
"""
from datetime import timedelta

from django.db.models import Avg, Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Event, EventBooking, Review


def registration_progress(event):
    """Return (active_count, capacity). capacity may be None."""
    active = EventBooking.objects.filter(
        event=event,
        status__in=['pending', 'confirmed'],
    ).count()
    return active, event.capacity


def cancellation_count(event):
    return EventBooking.objects.filter(event=event, status='cancelled').count()


def recent_registration_activity(event, days=7):
    """Count + optional per-day list of bookings in the last N days."""
    since = timezone.now() - timedelta(days=days)
    qs = EventBooking.objects.filter(event=event, created_at__gte=since)
    count = qs.count()
    per_day = list(
        qs.annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(c=Count('id'))
        .order_by('day')
    )
    return {'count': count, 'per_day': per_day}


def review_count(event):
    return Review.objects.filter(event=event, moderation_status='approved').count()


def average_rating(event):
    result = Review.objects.filter(
        event=event, moderation_status='approved'
    ).aggregate(avg=Avg('rating'))
    return result['avg']


def review_velocity(event):
    """Reviews since the event went live."""
    if not event.start_at:
        return 0
    return Review.objects.filter(
        event=event,
        moderation_status='approved',
        created_at__gte=event.start_at,
    ).count()


def lifecycle_status(event):
    return event.status


def health_indicator(event):
    """Return one of: 'high_demand', 'low_traction', 'cancellation_warning', 'healthy'."""
    active, capacity = registration_progress(event)
    cancel_count = cancellation_count(event)
    total_bookings = EventBooking.objects.filter(event=event).count()

    if capacity and capacity > 0 and active / capacity > 0.8:
        return 'high_demand'

    if total_bookings > 0 and cancel_count / total_bookings > 0.3:
        return 'cancellation_warning'

    if event.start_at and event.status == 'live':
        days_to_start = (event.start_at - timezone.now()).days
        if days_to_start > 30 and (capacity is None or active / max(capacity, 1) < 0.2):
            return 'low_traction'

    return 'healthy'


def event_pulse(event):
    """Return a dict with all pulse metrics for an event."""
    active, capacity = registration_progress(event)
    total = EventBooking.objects.filter(event=event).count()
    return {
        'active_registrations': active,
        'capacity': capacity,
        'total_bookings': total,
        'cancellation_count': cancellation_count(event),
        'recent_activity': recent_registration_activity(event),
        'review_count': review_count(event),
        'average_rating': average_rating(event),
        'review_velocity': review_velocity(event),
        'lifecycle_status': lifecycle_status(event),
        'health': health_indicator(event),
    }


def dashboard_pulse(events):
    """Batched pulse (active registrations + health) for a list of events.

    The full ``event_pulse`` issues several queries per event, which turns the
    organizer dashboard into an N+1 hotspot. This variant aggregates the
    booking counts for the whole queryset in a handful of queries and returns
    ``[(event, {'active_registrations': ..., 'health': ...}), ...]``.
    """
    events = list(events)
    if not events:
        return []

    ids = [e.pk for e in events]

    # One query: total bookings grouped by event.
    totals = dict(
        EventBooking.objects.filter(event_id__in=ids)
        .values('event_id')
        .annotate(total=Count('id'))
        .values_list('event_id', 'total')
    )
    # One query: active (pending/confirmed) bookings grouped by event.
    actives = dict(
        EventBooking.objects.filter(
            event_id__in=ids, status__in=['pending', 'confirmed'],
        )
        .values('event_id')
        .annotate(total=Count('id'))
        .values_list('event_id', 'total')
    )
    # One query: cancelled bookings grouped by event.
    cancelled = dict(
        EventBooking.objects.filter(event_id__in=ids, status='cancelled')
        .values('event_id')
        .annotate(total=Count('id'))
        .values_list('event_id', 'total')
    )

    now = timezone.now()
    results = []
    for event in events:
        total = totals.get(event.pk, 0)
        active = actives.get(event.pk, 0)
        cancel_count = cancelled.get(event.pk, 0)

        capacity = event.capacity
        if capacity and capacity > 0 and active / capacity > 0.8:
            health = 'high_demand'
        elif total > 0 and cancel_count / total > 0.3:
            health = 'cancellation_warning'
        elif event.start_at and event.status == 'live':
            days_to_start = (event.start_at - now).days
            if days_to_start > 30 and (capacity is None or active / max(capacity, 1) < 0.2):
                health = 'low_traction'
        else:
            health = 'healthy'

        results.append({
            'event': event,
            'pulse': {'active_registrations': active, 'health': health},
        })
    return results
