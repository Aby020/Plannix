"""Canonical display-name helpers for Plannix.

Every user-facing name and avatar initial flows through these two functions so
the identity a visitor sees is consistent everywhere — the navbar, the sidebar,
the dashboards, and the profile. Template filters in
``themes/templatetags/plannix_filters.py`` delegate to these helpers.

``display_name`` prefers the user's full name and falls back to the username;
``avatar_initial`` derives the avatar letter from that exact name so the two
never disagree.
"""


def display_name(user):
    """Return the canonical display name for a user.

    Prefer ``get_full_name()`` (first + last name); fall back to the username
    when the user has no name set. Anonymous/non-auth users (which lack
    ``get_full_name``) render an empty string, so public pages that reuse the
    filter never crash.
    """
    if user is None:
        return ''
    full_name = getattr(user, 'get_full_name', None)
    if callable(full_name):
        name = full_name()
        if name:
            return name
    return getattr(user, 'username', '') or ''


def avatar_initial(user):
    """Return the single uppercase initial used for a user's avatar.

    Derived from the canonical display name so the avatar and the visible name
    always match.
    """
    name = display_name(user)
    return name[:1].upper()
