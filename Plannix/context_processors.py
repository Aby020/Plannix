"""Site-wide context available to every Plannix template."""


def plannix_context(request):
    """Provide brand info, the current user's role and a notification count.

    Wrapped in try/except so a transient DB or import error never brings
    down every page via the context processor.
    """
    context = {
        'site_name': 'Plannix',
        'user_role': 'anonymous',
        'notification_count': 0,
    }

    try:
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return context

        from account_manager.decorators import get_role

        role = get_role(user)
        context['user_role'] = role

        if role == 'admin':
            from account_manager.models import Organization
            from events.models import EventBooking
            context['notification_count'] = (
                EventBooking.objects.filter(status='pending').count()
                + Organization.objects.filter(
                    status='pending', submitted_at__isnull=False,
                ).count()
            )
        elif role == 'organizer':
            from events.models import EventBooking
            context['notification_count'] = EventBooking.objects.filter(
                event__owner=user, status='pending',
            ).count()
        else:
            context['notification_count'] = user.bookings.exclude(
                status='cancelled',
            ).count()
    except Exception:  # noqa: BLE001 — never crash the page for a counter
        pass

    return context
