"""Advance payment service (Razorpay).

The advance is always computed server-side from the confirmed package price and
is never trusted from the browser. Order creation is ownership- and
eligibility-gated, and a payment is only ever marked paid after server-side
signature verification (Razorpay's HMAC-SHA256 scheme) — via the verify flow or
a signature-verified webhook.
"""
import base64
import hashlib
import hmac
import json

from django.conf import settings
from django.utils import timezone

from .models import BookingPayment


class PaymentError(Exception):
    """Raised when an advance-payment operation is not permitted."""


def advance_amount(booking):
    """Server-calculated advance (rupees) from the trusted package price."""
    return booking.price * settings.PAYMENT_ADVANCE_PERCENT // 100


def remaining_amount(booking):
    """The amount left after the advance (rupees)."""
    return booking.price - advance_amount(booking)


def gateway_configured():
    """True when Razorpay keys are present (no-op in local dev)."""
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def get_razorpay_client():
    """Return a configured Razorpay client, or None when not configured."""
    if not gateway_configured():
        return None
    import razorpay
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def create_order(booking, user):
    """Create (or reuse) a Razorpay order for the advance on a confirmed booking.

    Returns ``(payment, payload)`` where ``payload`` holds only public checkout
    fields (key_id, order_id, amount, currency, references) — never the secret.

    Raises :class:`PaymentError` when ineligible (wrong owner, not confirmed,
    already paid, or gateway unavailable).
    """
    if booking.attendee_id != user.id:
        raise PaymentError('You can only pay for your own bookings.')
    if booking.status != 'confirmed':
        raise PaymentError('Advance can only be paid once the booking is confirmed.')

    payment = BookingPayment.objects.filter(booking=booking).first()
    if payment is not None and payment.status == BookingPayment.STATUS_PAID:
        raise PaymentError('This advance has already been paid.')

    client = get_razorpay_client()
    if client is None:
        raise PaymentError('Online payment is not available right now.')

    amount = advance_amount(booking)  # rupees — the trusted server value

    if payment is None:
        payment = BookingPayment.objects.create(
            booking=booking, amount=amount, currency='INR',
            status=BookingPayment.STATUS_PENDING)
    elif payment.razorpay_order_id and payment.status == BookingPayment.STATUS_PENDING:
        # Idempotent refresh — reuse the existing pending order.
        payment.amount = amount
        payment.save()
        return payment, _checkout_payload(payment, booking)

    # Reset a previously failed advance to a fresh pending order.
    payment.amount = amount
    payment.status = BookingPayment.STATUS_PENDING
    payment.razorpay_payment_id = ''
    payment.failure_reason = ''
    payment.paid_at = None

    # Razorpay orders are denominated in the smallest currency unit (paise).
    order = client.order.create({
        'amount': amount * 100,
        'currency': 'INR',
        'receipt': payment.payment_reference,
        'notes': {'booking_reference': booking.booking_reference},
    })
    payment.razorpay_order_id = order['id']
    payment.save()
    return payment, _checkout_payload(payment, booking)


def _checkout_payload(payment, booking):
    """Public-only fields for the Razorpay checkout modal."""
    return {
        'key_id': settings.RAZORPAY_KEY_ID,
        'order_id': payment.razorpay_order_id,
        'amount': payment.amount * 100,  # paise for the checkout
        'currency': payment.currency,
        'payment_reference': payment.payment_reference,
        'booking_reference': booking.booking_reference,
        'name': booking.name,
        'email': booking.email,
        'description': f'Advance for {booking.event_title}',
    }


def verify_payment_signature(order_id, payment_id, signature):
    """Return True when the Razorpay signature matches our secret.

    This is Razorpay's exact HMAC-SHA256 scheme over ``order_id|payment_id``.
    """
    payload = f'{order_id}|{payment_id}'.encode()
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), payload,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')


def verify_webhook_signature(payload_bytes, razorpay_signature):
    """Verify a Razorpay webhook signature (base64 HMAC-SHA256 of the body)."""
    expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), payload_bytes,
                        hashlib.sha256).digest()
    expected_b64 = base64.b64encode(expected).decode()
    return hmac.compare_digest(expected_b64, razorpay_signature or '')


def handle_webhook(payload_bytes, razorpay_signature):
    """Process a Razorpay webhook idempotently.

    Returns ``(handled, payment)`` — ``handled`` is True when the event actually
    transitioned the payment (so the caller sends one notification email).
    An already-paid advance is never re-processed (no duplicate emails).
    """
    if not verify_webhook_signature(payload_bytes, razorpay_signature):
        raise PaymentError('Invalid webhook signature.')

    data = json.loads(payload_bytes)
    event = data.get('event')
    entity = data.get('payload', {}).get('payment', {}).get('entity', {})
    order_id = entity.get('order_id', '')

    payment = BookingPayment.objects.filter(razorpay_order_id=order_id).first()
    if payment is None:
        return False, None  # Unknown order — nothing to do.

    if event in ('payment.captured', 'payment.authorized'):
        if payment.status == BookingPayment.STATUS_PAID:
            return False, payment  # Idempotent — already handled.
        payment.status = BookingPayment.STATUS_PAID
        payment.razorpay_payment_id = entity.get('id', payment.razorpay_payment_id)
        payment.paid_at = timezone.now()
        payment.save()
        return True, payment

    if event == 'payment.failed':
        payment.status = BookingPayment.STATUS_FAILED
        payment.failure_reason = entity.get('error_description', 'Payment failed')
        payment.save()
        return True, payment

    return False, payment
