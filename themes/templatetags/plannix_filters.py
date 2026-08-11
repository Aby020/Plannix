"""Plannix template filters."""
from django import template

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
