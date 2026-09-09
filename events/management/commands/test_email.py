"""Send a real test email through the configured SMTP backend.

Usage:
    python manage.py test_email <recipient>

Sends a plain-text test message via ``django.core.mail`` using the active
``EMAIL_BACKEND`` from settings (Gmail SMTP when configured in ``.env``). Use
this to verify that ``EMAIL_HOST`` / ``EMAIL_PORT`` / ``EMAIL_USE_TLS`` /
``EMAIL_HOST_USER`` / ``EMAIL_HOST_PASSWORD`` / ``DEFAULT_FROM_EMAIL`` are set
up correctly.

Never prints the SMTP password or ``SECRET_KEY``.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Send a real test email through the configured SMTP backend.'

    def add_arguments(self, parser):
        parser.add_argument('recipient', help='Recipient email address.')

    def handle(self, *args, **options):
        recipient = (options['recipient'] or '').strip()
        if not recipient or '@' not in recipient:
            raise CommandError('Provide a valid recipient email address.')

        # Diagnostics only — the password and SECRET_KEY are never shown.
        self.stdout.write(f'Backend   : {settings.EMAIL_BACKEND}')
        self.stdout.write(f'SMTP host : {settings.EMAIL_HOST}')
        self.stdout.write(f'SMTP port : {settings.EMAIL_PORT}')
        self.stdout.write(f'Use TLS   : {settings.EMAIL_USE_TLS}')
        self.stdout.write(f'From      : {settings.DEFAULT_FROM_EMAIL}')
        self.stdout.write(f'Recipient : {recipient}')

        try:
            sent = send_mail(
                'Plannix — Test Email',
                'This is a test email from the Plannix platform.\n'
                'If you received this, the SMTP configuration is working.',
                settings.DEFAULT_FROM_EMAIL,
                [recipient],
                fail_silently=False,
            )
        except Exception as exc:  # e.g. SMTPAuthenticationError, connection refused
            raise CommandError(f'Failed to send test email: {exc}')

        if not sent:
            raise CommandError('send_mail returned 0 — no email was sent.')

        self.stdout.write(self.style.SUCCESS(f'Test email sent to {recipient}.'))
