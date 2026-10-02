"""Cache-backed rate limiting for Plannix.

A single decorator, shared by the sign-in, sign-up, password-reset and feedback
endpoints. Backed by ``django.core.cache`` so the counters are shared across
every worker process and survive a restart — unlike an in-process dictionary,
which each gunicorn worker gets its own copy of and which resets on deploy.

IP attribution honours ``settings.TRUST_X_FORWARDED_FOR``. The header is
client-controlled, so it is ignored unless the deployment genuinely sits behind
a reverse proxy that sets it; trusting it blind lets an attacker mint a fresh
rate-limit bucket per request just by varying the header.
"""
import logging

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse

logger = logging.getLogger(__name__)

DEFAULT_WINDOW = 300  # 5 minutes


def client_ip(request):
    """Return the request's IP for rate-limit attribution.

    Uses ``X-Forwarded-For`` only when ``TRUST_X_FORWARDED_FOR`` is enabled and
    a proxy is known to set it; otherwise falls back to ``REMOTE_ADDR``, which
    the application server derives from the socket and a client cannot forge.
    """
    if getattr(settings, 'TRUST_X_FORWARDED_FOR', False):
        forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if forwarded:
            # Left-most entry is the original client; the rest are proxies.
            client = forwarded.split(',')[0].strip()
            if client:
                return client
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def is_throttled(scope, ip, max_attempts, window=DEFAULT_WINDOW):
    """Count one attempt against ``scope:ip``; return True when over the limit.

    The first call for a key creates the counter; subsequent calls increment it.
    The counter expires ``window`` seconds after it was first created, so a
    burst is capped and a steady trickle is allowed to continue.
    """
    key = f'throttle:{scope}:{ip}'
    try:
        if cache.add(key, 1, timeout=window):
            return False
        return cache.incr(key) > max_attempts
    except ValueError:
        # Key expired between add() and incr() — start a fresh window.
        cache.set(key, 1, timeout=window)
        return False


def clear_throttle(scope, ip):
    """Reset the counter for ``scope:ip`` (used on successful auth and in tests)."""
    cache.delete(f'throttle:{scope}:{ip}')


def clear_throttle_state():
    """Drop every rate-limit counter.

    Test helper. Django's ``TestCase`` rolls back the database but does not
    clear the cache, so a counter incremented by one test would otherwise
    throttle the next — and every test client shares ``REMOTE_ADDR`` of
    ``127.0.0.1``, so they all collide on the same key.
    """
    cache.clear()


def rate_limited(scope, max_attempts, window=DEFAULT_WINDOW):
    """Reject a request once ``scope:ip`` exceeds ``max_attempts`` in ``window``.

    ``max_attempts`` and ``window`` may each be an int or a zero-argument
    callable. Pass a callable when the budget lives in a module global that
    tests patch — a bare int is captured at decoration time and would not
    reflect a later patch.

    Returns HTTP 429 with a plain-text body rather than a redirect, so a
    scripted client gets a machine-readable signal instead of silently
    following a redirect and re-POSTing.
    """

    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            limit = max_attempts() if callable(max_attempts) else max_attempts
            span = window() if callable(window) else window
            ip = client_ip(request)
            if is_throttled(scope, ip, limit, span):
                logger.warning('Rate limit hit for %s from %s', scope, ip)
                return HttpResponse(
                    'Too many requests. Please wait a few minutes and try again.',
                    status=429,
                    content_type='text/plain',
                )
            return view_func(request, *args, **kwargs)

        wrapper.__name__ = getattr(view_func, '__name__', 'wrapper')
        wrapper.__doc__ = view_func.__doc__
        wrapper.__wrapped__ = view_func
        return wrapper

    return decorator