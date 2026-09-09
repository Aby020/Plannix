"""Role-based access control helpers for Plannix.

Roles are derived from Django Groups:
    - ``admin``     -> full platform management (superuser or Admin group)
    - ``organizer`` -> event organizers (EventOrganizer group)
    - ``attendee``  -> regular registered users (Attendee group or default)
    - ``anonymous`` -> unauthenticated visitors

Superusers are always treated as ``admin``.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def get_role(user):
    """Return 'admin', 'organizer', 'attendee' or 'anonymous'."""
    if not user.is_authenticated:
        return 'anonymous'
    if user.is_superuser:
        return 'admin'
    groups = set(user.groups.values_list('name', flat=True))
    if 'Admin' in groups:
        return 'admin'
    if 'EventOrganizer' in groups:
        return 'organizer'
    return 'attendee'


def unauthenticated_user(view_func):
    """Redirect already-authenticated users away from sign-in / sign-up."""

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('index')
        return view_func(request, *args, **kwargs)

    return wrapper_func


def attendee_required(view_func):
    """Require the user to be an authenticated attendee."""

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please sign in to continue.')
            return redirect('sign_in')
        role = get_role(request.user)
        if role not in ('attendee', 'organizer', 'admin'):
            messages.error(request, 'You do not have permission to view that page.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return wrapper_func


def organizer_required(view_func):
    """Require the user to be an organizer or admin."""

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please sign in to continue.')
            return redirect('sign_in')
        role = get_role(request.user)
        if role not in ('organizer', 'admin'):
            messages.error(request, 'You do not have permission to view that page.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return wrapper_func


def admin_required(view_func):
    """Require the user to be an admin."""

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, 'Please sign in to continue.')
            return redirect('sign_in')
        role = get_role(request.user)
        if role != 'admin':
            messages.error(request, 'You do not have permission to view that page.')
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return wrapper_func


# ---------------------------------------------------------------------------
# Legacy aliases — kept temporarily until all usages are migrated
# ---------------------------------------------------------------------------

def admin_only(view_func):
    return admin_required(view_func)


def staff_or_admin(view_func):
    return organizer_required(view_func)


def allowed_roles(allowed_roles=()):
    allowed = set(allowed_roles)

    def decorator(view_func):
        @wraps(view_func)
        def wrapper_func(request, *args, **kwargs):
            role = get_role(request.user)
            if role in allowed:
                return view_func(request, *args, **kwargs)
            messages.error(request, 'You do not have permission to view that page.')
            return redirect('dashboard')

        return wrapper_func

    return decorator
