"""Upload featured images for live events to the configured default storage.

Designed for production (USE_CLOUDINARY=True): reads source images from
the repo-tracked event_images/ directory and saves them through Django's
default file storage, which pushes to Cloudinary when that backend is
active.

Safe to run repeatedly — skips any event whose file already matches the
source, and never touches non-live events.

Usage:
    python manage.py upload_live_images            # upload
    python manage.py upload_live_images --dry-run  # preview only
"""
import sys
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from events.models import Event


# ── Image mapping (derived from seed_demo EVENTS + LIFECYCLE_MAP) ──────────
# Keyed by (event title, category folder) → source filename inside event_images/
LIVE_IMAGE_MAP = {
    # Birthday (event_images/birthday/)
    ('Birthday Bash', 'birthday'): 'pexels-freestockpro-12616001.jpg',
    ('Kids Birthday Party', 'birthday'): 'pexels-rdne-4920988.jpg',
    ('Sweet 16 Celebration', 'birthday'): 'pexels-rdne-7363067.jpg',
    # Catering (event_images/catering/)
    ('Grand Catering Service', 'catering'): 'pexels-kseniia-lopyreva-3299160-4959845.jpg',
    ('Multi-Cuisine Buffet', 'catering'): 'pexels-novkov-visuals-34321369.jpg',
    ('Live Counter Catering', 'catering'): 'pexels-prosper-buka-1289782307-28736727.jpg',
    ('Premium Wedding Catering', 'catering'): 'pexels-stewphotography-12253092.jpg',
    # Corporate (event_images/corperate/) — note: folder has the typo
    ('Corporate Summit', 'corperate'): 'pexels-kaandurmus-9864907.jpg',
    ('Conference & Seminar', 'corperate'): 'pexels-pavel-danilyuk-6405783.jpg',
    ('Annual Day Gala', 'corperate'): 'pexels-reiez-35042249.jpg',
    # Wedding (event_images/wedding/)
    ('Royal Wedding', 'wedding'): 'pexels-alonssus-3212018.jpg',
    ('Classic Wedding', 'wedding'): 'pexels-breno-cardoso-149064345-18322558.jpg',
    ('Intimate Wedding', 'wedding'): 'pexels-thevisionaryvows-33417236.jpg',
}

# Category name → folder name (matches seed_demo CATEGORY_FOLDER)
CATEGORY_FOLDER = {
    'Birthday': 'birthday',
    'Catering': 'catering',
    'Corporate': 'corperate',
    'DJ': 'dj',
    'Wedding': 'wedding',
}


class Command(BaseCommand):
    help = 'Upload featured images for live events to Cloudinary (or default storage).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be uploaded without making changes.',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        event_image_dir = Path(settings.BASE_DIR) / 'event_images'

        live_events = Event.objects.filter(
            status='live', is_active=True,
        ).select_related('category').order_by('id')

        updated = 0
        skipped = 0
        missing = 0
        no_match = 0
        has_errors = False

        for event in live_events:
            cat_folder = (
                CATEGORY_FOLDER.get(event.category.name)
                if event.category
                else None
            )
            source_name = LIVE_IMAGE_MAP.get((event.title, cat_folder))

            if not source_name:
                self.stderr.write(
                    self.style.WARNING(
                        f'no-match: "{event.title}" '
                        f'(category={event.category or "None"})'
                    )
                )
                no_match += 1
                has_errors = True
                continue

            source_path = event_image_dir / cat_folder / source_name

            if not source_path.exists():
                self.stderr.write(
                    self.style.ERROR(f'missing:  {source_path}')
                )
                missing += 1
                has_errors = True
                continue

            # Build the storage-relative path: events/<filename>
            storage_name = f'events/{source_path.name}'

            # Idempotent: if storage already holds the exact file, skip upload.
            if default_storage.exists(storage_name):
                existing_size = default_storage.size(storage_name)
                if existing_size == source_path.stat().st_size:
                    if not dry_run:
                        event.featured_image = storage_name
                        event.save(update_fields=['featured_image'])
                    self.stdout.write(
                        f'  {"[dry-run] " if dry_run else ""}unchanged: '
                        f'"{event.title}" → {storage_name}'
                    )
                    skipped += 1
                    continue

            # Upload through Django storage (Cloudinary when active)
            if dry_run:
                self.stdout.write(
                    f'  [dry-run] would upload: {source_path.name} → '
                    f'{storage_name} for "{event.title}"'
                )
                updated += 1
                continue

            try:
                with open(source_path, 'rb') as src_file:
                    saved_name = default_storage.save(
                        storage_name, File(src_file),
                    )
            except OSError as exc:
                self.stderr.write(
                    self.style.ERROR(
                        f'upload-failed: "{event.title}" — {exc}'
                    )
                )
                has_errors = True
                continue

            event.featured_image = saved_name
            event.save(update_fields=['featured_image'])
            self.stdout.write(
                f'  uploaded: {source_path.name} → {saved_name} '
                f'for "{event.title}"'
            )
            updated += 1

        total = updated + skipped + missing + no_match
        self.stdout.write(
            f'\nDone — total live events: {total}, '
            f'uploaded: {updated}, unchanged: {skipped}, '
            f'missing file: {missing}, no mapping: {no_match}'
        )

        if has_errors and not dry_run:
            self.stderr.write(
                self.style.ERROR(
                    '\nErrors occurred — some images were not uploaded.'
                )
            )
            sys.exit(1)
