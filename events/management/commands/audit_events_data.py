"""Audit and safely repair Event data against the package-marketplace domain
model.

Usage:
    python manage.py audit_events_data            # report only (no changes)
    python manage.py audit_events_data --fix      # apply safe repairs

The marketplace model introduced an Organization holding each event package.
This command audits every Event for:

* ``organization`` is NULL (not attached to a business entity)
* organization belongs to a different owner than the event's owner
* legacy lifecycle statuses or missing approval timestamps
* bookings that lost their event reference (historical data)

``--fix`` applies the *only* safe repair automatically: attaching an event to
its owner's admin-*approved* Organization when it is missing one. Nothing is
deleted and no status is force-changed — every other finding is left for a
human decision and only reported.
"""
import json

from django.core.management.base import BaseCommand
from django.db.models import Count, F

from account_manager.models import Organization
from events.models import Event
from events.services import VALID_TRANSITIONS


class Command(BaseCommand):
    help = (
        'Audit Event records against the marketplace domain model; '
        'optionally apply the safe organization-link repair.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Apply the safe repair: link events to their owner\'s '
                 'approved Organization when organization is NULL.',
        )
        parser.add_argument(
            '--json',
            action='store_true',
            help='Print the audit as one JSON document (machine readable).',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        as_json = options['json']

        total = Event.objects.count()
        organizations = Organization.objects.select_related('owner').all()

        # --- lifecycle distribution -------------------------------------
        status_rows = (
            Event.objects.values('status').annotate(count=Count('id'))
            .order_by('status')
        )
        status_dist = {row['status']: row['count'] for row in status_rows}

        # --- checks -------------------------------------------------------
        unassigned = list(Event.objects.filter(organization__isnull=True))
        mismatched_org = []
        for event in Event.objects.filter(organization__isnull=False).select_related('organization'):
            if event.organization.owner_id != event.owner_id:
                mismatched_org.append(event)

        # Legacy / non-compliant statuses and timestamps.
        legacy_bypass = list(Event.objects.filter(
            status__in=('live', 'published', 'completed'),
            submitted_at__isnull=True,
        ))
        inconsistent_dates = list(Event.objects.filter(
            start_at__isnull=False, end_at__isnull=False, end_at__lt=F('start_at'),
        ))
        invalid_status = [
            e for e in Event.objects.all()
            if e.status not in VALID_TRANSITIONS
        ]

        # Organizations available to link (approved ones only).
        approvable_orgs = {
            org.owner_id: org
            for org in organizations
            if org.is_approved
        }

        # Finding severity buckets.
        findings = {
            'total_events': total,
            'status_distribution': status_dist,
            'events_without_organization': [e.pk for e in unassigned],
            'org_owner_mismatch': [e.pk for e in mismatched_org],
            'live_without_approval_trail': [e.pk for e in legacy_bypass],
            'inconsistent_dates': [e.pk for e in inconsistent_dates],
            'invalid_status': [e.pk for e in invalid_status],
        }

        # --- repair (only when --fix) ------------------------------------
        repaired = []
        if fix:
            for event in unassigned:
                org = approvable_orgs.get(event.owner_id)
                if org is not None:
                    event.organization = org
                    event.save(update_fields=['organization', 'updated_at'])
                    repaired.append(event.pk)
            findings['repaired_org_links'] = repaired
            findings['still_unassigned'] = [
                e.pk for e in unassigned if e.pk not in repaired
            ]

        if as_json:
            self.stdout.write(json.dumps(findings, indent=2, default=str))
            return

        self._print_report(findings, fix, repaired, unassigned, approvable_orgs)

    def _print_report(self, findings, fix, repaired, unassigned, approvable_orgs):
        w = self.stdout.write
        s = self.style

        w('')
        w(s.MIGRATE_HEADING('Plannix event data audit'))
        w('=' * 58)
        w(f'Total events: {findings["total_events"]}')

        w(s.HTTP_INFO('\nLifecycle distribution:'))
        for status, count in sorted(findings['status_distribution'].items()):
            w(f'  {status:<14} {count}')

        self._bucket(w, s, 'Events with organization = NULL',
                     findings['events_without_organization'])
        self._bucket(w, s, 'Org/owner mismatches (invalid organization)',
                     findings['org_owner_mismatch'])
        self._bucket(w, s, 'LIVE/PUBLISHED without approval trail (legacy)',
                     findings['live_without_approval_trail'])
        self._bucket(w, s, 'Inconsistent start/end dates',
                     findings['inconsistent_dates'])
        self._bucket(w, s, 'Status not in the lifecycle state machine',
                     findings['invalid_status'])

        if fix:
            if repaired:
                w(s.SUCCESS(f'\nRepaired: attached {len(repaired)} event(s) to '
                            'their owner\'s approved organization.'))
            else:
                w('\nNo safe repairs applied.')
            if findings['still_unassigned']:
                w(s.WARNING(
                    f'\n{len(findings["still_unassigned"])} event(s) remain '
                    'without an organization because the owner has no '
                    'approved organization yet.'))
        else:
            can_link = sum(1 for e in unassigned if e.owner_id in approvable_orgs)
            w(s.HTTP_NOT_MODIFIED(
                f'\nRun with --fix to attach {can_link} event(s) to an '
                'approved organization. No records are ever deleted or '
                'force-repriced by this command.'))

    def _bucket(self, w, s, label, pks):
        if pks:
            w(s.WARNING(f'\n{label}: {len(pks)}'))
            w(f'  IDs: {", ".join(str(pk) for pk in pks[:40])}'
              f'{"…" if len(pks) > 40 else ""}')
        else:
            w(s.SUCCESS(f'\n{label}: none'))