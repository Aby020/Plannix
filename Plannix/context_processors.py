"""Site-wide context available to every Plannix template."""

from account_manager.decorators import get_role


def plannix_context(request):
    """Provide brand info, the current user's role and a notification count."""
    context = {
        'site_name': 'Plannix',
        'user_role': 'anonymous',
        'notification_count': 0,
    }

    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return context

    role = get_role(user)
    context['user_role'] = role

    # Staff and admins: bookings that need attention.
    if role in ('staff', 'admin'):
        from events.models import Event_Booking
        context['notification_count'] = Event_Booking.objects.filter(status='pending').count()
    else:
        # Customers: the count of their active (non-cancelled) bookings.
        context['notification_count'] = user.bookings.exclude(status='cancelled').count()

    return context
