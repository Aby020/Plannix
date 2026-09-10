"""Plannix email service — one reusable, template-based email layer.

All outbound mail flows through this module so views never call
``django.core.mail`` directly. Emails are rendered from templates under
``templates/email/`` with Plannix-consistent branding and never include
passwords, reset tokens, or payment secrets.

The active backend stays environment-driven (``EMAIL_BACKEND`` in settings,
defaulting to the console backend for local development); tests override it
with the locmem backend and inspect ``django.core.mail.outbox``.
"""
import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from account_manager.identity import display_name as _display_name

logger = logging.getLogger(__name__)

PLANNIX_SITE_URL = 'https://plannix.example.com'


def _send(recipient, subject, template_name, context):
    """Render ``templates/email/<template_name>.txt`` and send it.

    Best-effort: a slow or unreachable mail server must never hang or crash
    the request that triggered it (e.g. a booking that has already been
    persisted). Failures are logged instead of raised; delivery remains real
    when the SMTP backend is configured correctly.
    """
    context = {**context, 'site_url': PLANNIX_SITE_URL}
    try:
        body = render_to_string(f'email/{template_name}.txt', context)
        # The SMTP connection timeout is set via EMAIL_TIMEOUT in settings —
        # it cannot be passed to send_mail directly. fail_silently guards the
        # send; any backend error is logged below instead of crashing the
        # request that triggered it.
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [recipient],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001 — never crash the request for mail
        logger.warning('Failed to send %s email to %s: %s', template_name, recipient, exc)


def organizer_contact(booking):
    """Return ``(name, email, phone)`` for the organizer behind a booking.

    Prefers the approved Organization's public business contact; falls back to
    the event owner's email and the event's contact number. These are the
    organizer's own public details, shown to the attendee who booked — never
    an attendee's private data.
    """
    org = getattr(booking.event, 'organization', None)
    if org is not None and getattr(org, 'name', ''):
        name = org.name
        email = getattr(org, 'email', '') or getattr(booking.event.owner, 'email', '')
        phone = getattr(org, 'contact_number', '') or booking.event.contact_number
        return name, email, phone
    return (
        _display_name(booking.event.owner),
        getattr(booking.event.owner, 'email', ''),
        booking.event.contact_number,
    )


def _advance_amount(booking):
    """Server-calculated advance for a booking (paise-compatible integer)."""
    return booking.price * settings.PAYMENT_ADVANCE_PERCENT // 100


def send_registration_notice(email, username, role_label):
    """Welcome email sent after account creation (not a login email)."""
    _send(email, 'Welcome to Plannix', 'registration_notice', {
        'username': username,
        'role_label': role_label,
    })


def send_booking_confirmation(booking):
    """Customer-facing confirmation for a newly created booking.

    Booking confirmation is the successful end of the customer booking flow —
    no online advance payment. The attendee is directed to contact the
    organizer directly for payment details.
    """
    provider, organizer_email, organizer_phone = organizer_contact(booking)
    _send(booking.email, 'Plannix — Booking Confirmation', 'booking_confirmation', {
        'name': booking.name,
        'event_title': booking.event_title,
        'provider': provider,
        'event_date': booking.event_date,
        'event_location': booking.event_location,
        'booking_reference': booking.booking_reference,
        'status': booking.get_status_display(),
        'price': booking.price,
        'organizer_email': organizer_email,
        'organizer_phone': organizer_phone,
    })


def send_organizer_booking_notification(booking):
    """Notify the organizer of a new booking request (permitted details only).

    The recipient is the organizer/organization email — the same business
    contact the customer confirmation points the attendee to (prefer the
    approved Organization's public email, fall back to the event owner's
    email). Without a contact email the notification is skipped.
    """
    _, organizer_email, _ = organizer_contact(booking)
    if not organizer_email:
        return
    _send(organizer_email, 'Plannix — New Booking Request', 'organizer_booking_notification', {
        'customer_name': booking.name,
        'customer_email': booking.email,
        'customer_number': booking.number,
        'event_title': booking.event_title,
        'event_date': booking.event_date,
        'event_location': booking.event_location,
        'booking_reference': booking.booking_reference,
        'status': booking.get_status_display(),
    })


def send_booking_status_change(booking):
    """Notify the customer when their booking status changes."""
    _send(booking.email, f'Plannix — Booking {booking.get_status_display()}',
          'booking_status', {
              'name': booking.name,
              'event_title': booking.event_title,
              'event_date': booking.event_date,
              'status': booking.get_status_display(),
              'booking_reference': booking.booking_reference,
          })


def send_advance_confirmation(booking):
    """Customer confirmation after a verified advance payment."""
    advance = _advance_amount(booking)
    _send(booking.email, 'Plannix — Advance Payment Received', 'advance_confirmation', {
        'name': booking.name,
        'event_title': booking.event_title,
        'booking_reference': booking.booking_reference,
        'advance': advance,
        'remaining': booking.price - advance,
    })


def send_password_reset_email(recipient, context):
    """Send the password-reset email built from Django's reset form context.

    ``context`` carries user, uid, token, domain, protocol, site_name and
    token_lifetime; the reset link is rendered in the email template.
    """
    _send(recipient, 'Plannix — Password Reset', 'password_reset', context)


def send_feedback_confirmation(email, name):
    """Thank-you email after a feedback submission."""
    _send(email, 'Plannix — Thank You for Your Feedback',
          'feedback_confirmation', {'name': name})
