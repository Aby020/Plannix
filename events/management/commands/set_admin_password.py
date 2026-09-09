"""Set the password for the existing ``admin`` superuser from an environment variable.

Designed for production deploys where the admin account was created by
``seed_demo`` with a random, unknown password.  Reading the password from
``PLANNIX_ADMIN_PASSWORD`` lets you pin a known credential without ever
storing it in source code.

Safe to run repeatedly — the command is idempotent: if the password is
already correct it reports success without touching the database.

Usage:
    python manage.py set_admin_password               # reads env var
    PLANNIX_ADMIN_PASSWORD=... python manage.py set_admin_password
"""
import os
import sys

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Set the admin password from the PLANNIX_ADMIN_PASSWORD env var.'

    def handle(self, *args, **options):
        password = os.environ.get('PLANNIX_ADMIN_PASSWORD')

        if not password:
            self.stdout.write(
                'PLANNIX_ADMIN_PASSWORD is not set — skipping.',
            )
            return

        try:
            admin = User.objects.get(username='admin')
        except User.DoesNotExist:
            self.stderr.write(
                self.style.ERROR(
                    'User "admin" does not exist. '
                    'Run seed_demo first.',
                ),
            )
            sys.exit(1)

        # Check whether the password is already current — avoid an
        # unnecessary write and keep the command truly idempotent.
        if admin.check_password(password):
            self.stdout.write('Admin password is already up to date.')
            return

        admin.set_password(password)
        admin.save(update_fields=['password'])
        self.stdout.write(self.style.SUCCESS('Admin password updated.'))
