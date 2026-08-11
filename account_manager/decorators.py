"""Role-based access control helpers for Plannix.

Roles are derived from Django Groups:
    - ``admin``    -> full platform management (plus Django admin)
    - ``staff``    -> operational management (events, bookings, feedback)
    - ``customer`` -> regular registered users (default when no group is set)

Superusers are always treated as ``admin``.
"""
from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def get_role(user):
    """Return ``'admin'``, ``'staff'``, ``'customer'`` or ``'anonymous'``."""
    if not user.is_authenticated:
        return 'anonymous'
    if user.is_superuser:
        return 'admin'
    groups = set(user.groups.values_list('name', flat=True))
    if 'admin' in groups:
        return 'admin'
    if 'staff' in groups:
        return 'staff'
    return 'customer'


def unauthenticated_user(view_func):
    """Redirect already-authenticated users away from sign-in / sign-up."""

    @wraps(view_func)
    def wrapper_func(request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('dashboard')
        return view_func(request, *args, **kwargs)

    return wrapper_func


def allowed_roles(allowed_roles=()):
    """Allow access only to users whose role is in ``allowed_roles``."""
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


def admin_only(view_func):
    """Restrict a view to administrators only."""
    return allowed_roles(['admin'])(view_func)


def staff_or_admin(view_func):
    """Restrict a view to staff members and administrators."""
    return allowed_roles(['staff', 'admin'])(view_func)
