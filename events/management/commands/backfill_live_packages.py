"""Backfill existing Event packages to the single-gate workflow.

Under the current business rule, **Organization approval is the only admin
gate** — once an organization is approved, its packages are live with no second
admin review. This command brings existing data in line with that rule by
publishing the packages of approved organizations.

Usage:
    python manage.py backfill_live_packages            # report only (no changes)
    python manage.py backfill_live_packages --apply    # publish live

Only packages still awaiting a decision (draft / under_review / approved /
published) owned by an *approved* Organization are touched. Packages already
live, completed or cancelled — and any package whose organization is not
approved — are left untouched. Nothing is deleted.
"""
from django.core.management.base import BaseCommand

from account_manager.models import Organization
from events.models import Event
from events.services import auto_publish_org_packages

AWAITING_STATUSES = ('draft', 'under_review', 'approved', 'published')


class Command(BaseCommand):
    help = (
        'Publish the packages of approved organizations to live (single-gate '
        'workflow). Reports by default; use --apply to change data.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Apply the change: publish qualifying packages live.',
        )

    def handle(self, *args, **options):
        apply_change = options['apply']
        w = self.stdout.write
        s = self.style

        approved_orgs = Organization.objects.filter(status='approved')
        affected = Event.objects.filter(
            organization__status='approved',
            status__in=AWAITING_STATUSES,
        ).order_by('id')

        w('')
        w(s.MIGRATE_HEADING('Plannix — single-gate package backfill'))
        w('=' * 58)
        w(f'Approved organizations: {approved_orgs.count()}')
        w(f'Qualifying packages (owned by an approved org, not yet live): '
          f'{affected.count()}')

        if not apply_change:
            for event in affected:
                w(f'  would publish: #{event.pk} "{event.title}" '
                  f'({event.status}) -> live')
            if affected:
                w(s.WARNING(
                    '\nRun with --apply to publish these packages live.'
                ))
            else:
                w(s.SUCCESS('\nNothing to do.'))
            return

        # Apply, auditing the before/after for every changed package.
        published = 0
        for org in approved_orgs:
            events = auto_publish_org_packages(org, None)
            for event in events:
                w(f'  published: #{event.pk} "{event.title}" -> live')
                published += 1

        w(s.SUCCESS(f'\nPublished {published} package(s) live.'))
        remaining = Event.objects.filter(
            organization__status='approved',
            status__in=AWAITING_STATUSES,
        ).count()
        w(s.HTTP_NOT_MODIFIED(
            f'Remaining awaiting packages for approved orgs: {remaining}'
        ))
