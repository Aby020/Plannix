"""Plannix template filters."""
from django import template

from account_manager.identity import avatar_initial as _avatar_initial
from account_manager.identity import display_name as _display_name

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return ``dictionary[key]`` if present, else ``None``.

    Usage: ``{{ type_counts|get_item:event_type }}``
    """
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except (AttributeError, TypeError):
        return None


@register.filter
def display_name(user):
    """Canonical display name for a user.

    Usage: ``{{ user|display_name }}``
    """
    return _display_name(user)


@register.filter
def avatar_initial(user):
    """Uppercase avatar initial derived from the canonical display name.

    Usage: ``{{ user|avatar_initial }}``
    """
    return _avatar_initial(user)
