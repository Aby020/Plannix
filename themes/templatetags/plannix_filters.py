"""Plannix template filters."""
import re

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


# ---------------------------------------------------------------------------
# Cloudinary image resizing
# ---------------------------------------------------------------------------

# Matches the path segment after /upload/ in a Cloudinary URL.
# Group 1 = everything before the file path (may already contain transforms).
_CLOUDINARY_UPLOAD_RE = re.compile(r'(/upload/)(?!.*\/upload\/)')


@register.filter
def cloudinary_resize(url, width):
    """Append Cloudinary ``w_<width>,q_auto,f_auto`` transforms to a URL.

    * **Cloudinary URLs** (``res.cloudinary.com``): inserts the transform
      clause after ``/upload/`` so Cloudinary serves a resized, auto-quality,
      auto-format variant — typically **5-10× smaller** than the original.
    * **Non-Cloudinary URLs** (local dev, static fallbacks): returned
      unchanged — no dependency on Pillow or any image-processing library.

    Usage::

        {{ event.featured_image.url|cloudinary_resize:800 }}
    """
    if not url:
        return ''
    if 'res.cloudinary.com' not in url:
        return url
    width = int(width)
    transform = f'w_{width},q_auto,f_auto'
    return _CLOUDINARY_UPLOAD_RE.sub(rf'\g<1>{transform}/', url, count=1)
