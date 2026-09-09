"""HTTPS transactional email backend for Plannix (provider: Resend).

Plannix sends all mail through ``django.core.mail`` (see ``Plannix/emails.py``).
This backend replaces SMTP with a single HTTPS POST to the Resend API so that
production on Render Free — which blocks outbound SMTP — can deliver real mail
without a worker process or a queue: Resend accepts the request over HTTPS and
performs delivery asynchronously on its side.

Nothing here is Plannix-asynchronous: the HTTP request is synchronous, but it
is short (default timeout 5s) and the provider absorbs the delivery work.

Configuration (environment only — never committed):
    RESEND_API_KEY      Resend API key (required in production)
    DEFAULT_FROM_EMAIL  sender address (already used by Plannix/emails.py)

Production selects this backend via EMAIL_BACKEND:
    Plannix.email_backends.ResendEmailBackend

Local development is unchanged: EMAIL_BACKEND keeps working with the console
backend or a Gmail SMTP backend.
"""
import json
import logging
import os
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

RESEND_API_URL = 'https://api.resend.com/emails'

# Default timeout if EMAIL_TIMEOUT is not configured (seconds).
_DEFAULT_TIMEOUT = 5


class ResendEmailBackend(BaseEmailBackend):
    """Send Django EmailMessage objects through the Resend REST API.

    Honours Django email-backend conventions: ``send_messages`` returns the
    count of messages accepted, and ``fail_silently`` controls whether a
    delivery error is swallowed (logged, returns the partial count) or raised.
    """

    def __init__(self, fail_silently=False, timeout=None, api_key=None, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        # EMAIL_TIMEOUT in settings bounds every HTTP call; a stubborn or
        # unreachable provider can never hang the request that triggered it.
        self.timeout = (
            timeout
            if timeout is not None
            else getattr(settings, 'EMAIL_TIMEOUT', None) or _DEFAULT_TIMEOUT
        )
        self._api_key = (
            api_key
            if api_key is not None
            else os.environ.get('RESEND_API_KEY', '')
        )

    def send_messages(self, email_messages):
        """Send each message as an HTTPS POST; return the number accepted."""
        if not email_messages:
            return 0

        if not self._api_key:
            logger.error(
                'ResendEmailBackend: RESEND_API_KEY is not set; '
                '%s message(s) dropped.',
                len(email_messages),
            )
            if not self.fail_silently:
                raise ValueError(
                    'RESEND_API_KEY is not set for the Resend email backend.'
                )
            return 0

        num_sent = 0
        for message in email_messages:
            try:
                self._post(message)
                num_sent += 1
            except Exception as exc:  # noqa: BLE001 — backend-level guard
                # Log only enough to triage: subject + recipient, never the
                # API key, never the message body.
                logger.warning(
                    'ResendEmailBackend: failed to send "%s" to %r: %s',
                    message.subject, message.to, exc,
                )
                if not self.fail_silently:
                    raise
        return num_sent

    def _post(self, message):
        """POST a single EmailMessage to the Resend send endpoint."""
        to = list(message.to or [])
        if not to:
            return

        payload = {
            'from': message.from_email,
            'to': to,
            'subject': message.subject,
            'text': message.body,
        }
        # EmailMultiAlternatives carries the HTML body here (Plannix only sends
        # plain text today, but honour the field if a caller supplies it).
        for content, mimetype in getattr(message, 'alternatives', ()) or ():
            if mimetype == 'text/html':
                payload['html'] = content
                break

        cc = list(getattr(message, 'cc', None) or [])
        if cc:
            payload['cc'] = cc
        bcc = list(getattr(message, 'bcc', None) or [])
        if bcc:
            payload['bcc'] = bcc
        reply_to = getattr(message, 'reply_to', None) or []
        if reply_to:
            # EmailMessage normalizes reply_to to a list of address strings.
            flattened = [r[0] if isinstance(r, (list, tuple)) else r for r in reply_to]
            payload['reply_to'] = list(flattened)

        request = urllib.request.Request(
            RESEND_API_URL,
            data=json.dumps(payload).encode('utf-8'),
            method='POST',
            headers={
                'Authorization': f'Bearer {self._api_key}',
                'Content-Type': 'application/json',
                'User-Agent': 'plannix-email-backend',
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            # Fully consume the response so transport errors surface here
            # (non-2xx responses raise urllib.error.HTTPError).
            response.read()