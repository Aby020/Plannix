"""Seed the Plannix app with realistic demo data for the Phase 1 redesign.

Usage:
    python manage.py seed_demo

Creates:
- Groups: Attendee, EventOrganizer, Admin
- Users: admin (superuser), organizer1, organizer2, 4 attendees
- EventCategories with slugs and sort_order
- 20 events across realistic lifecycle states
- EventInclusion rows from package lists
- EventBookings with event FK, attendee FK, snapshots
- Sample Reviews for completed bookings

Idempotent: upserts by stable keys, skips existing bookings/reviews.
"""
import os
import secrets
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand
from django.utils import timezone

from account_manager.models import OrganizerProfile
from events.models import (
    Event, EventAuditLog, EventBooking, EventCategory, EventInclusion, Review,
)

# ---------------------------------------------------------------------------
# Image helpers (reuse existing event_images/ folder structure)
# ---------------------------------------------------------------------------
EVENT_IMAGE_DIR = Path(settings.BASE_DIR) / 'event_images'

CATEGORY_FOLDER = {
    'Birthday': 'birthday',
    'Catering': 'catering',
    'Corporate': 'corperate',
    'DJ': 'dj',
    'Wedding': 'wedding',
}

# ---------------------------------------------------------------------------
# The 20 event definitions: 5 categories x 4 events each.
# Maps to the new model fields: title, category, price, location, description.
# ---------------------------------------------------------------------------
EVENTS = [
    # --- Birthday ---
    {
        'title': 'Birthday Bash',
        'category': 'Birthday',
        'price': 60000,
        'location': 'Kochi, Kerala',
        'description': (
            'A lively birthday celebration with balloon decor, a custom cake '
            'and fun games — everything to make the birthday person feel '
            'extra special.'
        ),
        'packages': ['Balloon & themed decor', 'Custom theme cake', 'Games & entertainment', 'Photo booth & props'],
        'image': 'pexels-freestockpro-12616001.jpg',
    },
    {
        'title': 'Kids Birthday Party',
        'category': 'Birthday',
        'price': 40000,
        'location': 'Kochi, Kerala',
        'description': (
            'A safe, colourful party for little ones — character theme decor, '
            'a cartoon-style cake and a dedicated host for games and fun.'
        ),
        'packages': ['Character theme decor', 'Cartoon cake', 'Kids games & host', 'Party favours & props'],
        'image': 'pexels-rdne-4920988.jpg',
    },
    {
        'title': 'Sweet 16 Celebration',
        'category': 'Birthday',
        'price': 85000,
        'location': 'Trivandrum, Kerala',
        'description': (
            'A glamorous sweet-sixteen party with pastel decor, a dessert '
            'table, photo booth and DJ, styled around the birthday star.'
        ),
        'packages': ['Pastel floral decor', 'Dessert table', 'Photo booth', 'DJ & lighting'],
        'image': 'pexels-rdne-7363067.jpg',
    },
    {
        'title': 'Milestone Birthday',
        'category': 'Birthday',
        'price': 120000,
        'location': 'Bangalore, Karnataka',
        'description': (
            'An elegant milestone celebration with premium decor, gourmet '
            'dinner, live music and a personalised tribute video.'
        ),
        'packages': ['Premium floral decor', 'Gourmet dinner', 'Live music', 'Tribute video & photography'],
        'image': 'pexels-ron-lach-10032953.jpg',
    },
    # --- Catering ---
    {
        'title': 'Grand Catering Service',
        'category': 'Catering',
        'price': 150000,
        'location': 'Kochi, Kerala',
        'description': (
            'Full-service catering for large gatherings — a lavish multi-cuisine '
            'buffet served by an experienced team with elegant table setups.'
        ),
        'packages': ['Multi-cuisine buffet', 'Elegant table setup', 'Service staff', 'Beverage bar'],
        'image': 'pexels-kseniia-lopyreva-3299160-4959845.jpg',
    },
    {
        'title': 'Multi-Cuisine Buffet',
        'category': 'Catering',
        'price': 90000,
        'location': 'Kochi, Kerala',
        'description': (
            'A spread of regional and continental favourites — live counters, '
            'a dessert bar and on-site chefs for a memorable dining experience.'
        ),
        'packages': ['Live food counters', 'Continental & regional menu', 'Dessert bar', 'On-site chefs'],
        'image': 'pexels-novkov-visuals-34321369.jpg',
    },
    {
        'title': 'Live Counter Catering',
        'category': 'Catering',
        'price': 75000,
        'location': 'Chennai, Tamil Nadu',
        'description': (
            'Interactive live stations — pasta, dosa, chaat and grill counters — '
            'prepared fresh in front of your guests.'
        ),
        'packages': ['Pasta & grill counter', 'Dosa & chaat counter', 'Live dessert station', 'Beverage service'],
        'image': 'pexels-prosper-buka-1289782307-28736727.jpg',
    },
    {
        'title': 'Premium Wedding Catering',
        'category': 'Catering',
        'price': 280000,
        'location': 'Kochi, Kerala',
        'description': (
            'A regal wedding feast — traditional sadhya and fine-dining '
            'courses, ornate table styling and dedicated banquet service.'
        ),
        'packages': ['Traditional sadhya', 'Fine-dining courses', 'Ornate table styling', 'Banquet service team'],
        'image': 'pexels-stewphotography-12253092.jpg',
    },
    # --- Corporate ---
    {
        'title': 'Corporate Summit',
        'category': 'Corporate',
        'price': 480000,
        'location': 'Bangalore, Karnataka',
        'description': (
            'Full-scale summit management — keynote stage with AV, guest '
            'registration, conference hall setup and refreshments for up to '
            '500 delegates.'
        ),
        'packages': ['Stage & AV setup', 'Guest registration & staff', 'Catering & refreshments', 'Conference hall setup'],
        'image': 'pexels-kaandurmus-9864907.jpg',
    },
    {
        'title': 'Conference & Seminar',
        'category': 'Corporate',
        'price': 250000,
        'location': 'Mumbai, Maharashtra',
        'description': (
            'Professional conference execution — projector and sound, panel '
            'seating, breaks and a help desk for a smooth, focused event.'
        ),
        'packages': ['Projector & sound', 'Panel seating & stage', 'Tea & coffee breaks', 'Help desk & staff'],
        'image': 'pexels-pavel-danilyuk-6405783.jpg',
    },
    {
        'title': 'Annual Day Gala',
        'category': 'Corporate',
        'price': 350000,
        'location': 'Kochi, Kerala',
        'description': (
            'A celebratory annual gala with awards ceremony, themed decor, '
            'dinner and entertainment for the whole company.'
        ),
        'packages': ['Awards ceremony & stage', 'Themed decor', 'Dinner & drinks', 'Live entertainment'],
        'image': 'pexels-reiez-35042249.jpg',
    },
    {
        'title': 'Team Offsite Retreat',
        'category': 'Corporate',
        'price': 180000,
        'location': 'Goa',
        'description': (
            'A relaxed offsite with team-building activities, beachside '
            'accommodation, group meals and a closing bonfire night.'
        ),
        'packages': ['Team-building activities', 'Beachside stay', 'Group meals', 'Bonfire night'],
        'image': 'pexels-reiez-35042461.jpg',
    },
    # --- DJ ---
    {
        'title': 'DJ Night Party',
        'category': 'DJ',
        'price': 45000,
        'location': 'Kochi, Kerala',
        'description': (
            'A high-energy DJ night with a pro sound system, laser and stage '
            'lighting and a glowing dance floor to keep the party going.'
        ),
        'packages': ['DJ & music system', 'Laser & stage lighting', 'Dance floor & neon decor', 'Host & sound engineer'],
        'image': 'pexels-ellis-5949085.jpg',
    },
    {
        'title': 'Club DJ Experience',
        'category': 'DJ',
        'price': 60000,
        'location': 'Bangalore, Karnataka',
        'description': (
            'An immersive club-style night — open-format DJ sets, VIP booth, '
            'crystal-clear sound and a professional light show.'
        ),
        'packages': ['Open-format DJ sets', 'VIP booth & guest list', 'Crystal sound system', 'Light show'],
        'image': 'pexels-joshua-sanchez-1713464086-29263194.jpg',
    },
    {
        'title': 'Pool Party DJ',
        'category': 'DJ',
        'price': 55000,
        'location': 'Goa',
        'description': (
            'Sun-down beats by the pool — tropical DJ sets, ambient lighting, '
            'a mini dance deck and chilled cocktails for the crowd.'
        ),
        'packages': ['Tropical DJ sets', 'Ambient pool lighting', 'Mini dance deck', 'Chilled cocktail bar'],
        'image': 'pexels-leonardo-delsabio-2150529415-35243129.jpg',
    },
    {
        'title': 'Festival DJ Show',
        'category': 'DJ',
        'price': 95000,
        'location': 'Mumbai, Maharashtra',
        'description': (
            'A big-stage festival show — main-stage DJ, huge LED screens, '
            'confetti and pyro effects for a truly unforgettable set.'
        ),
        'packages': ['Main-stage DJ', 'LED screens', 'Confetti & pyro effects', 'Stage crew'],
        'image': 'pexels-yankrukov-9005499.jpg',
    },
    # --- Wedding ---
    {
        'title': 'Royal Wedding',
        'category': 'Wedding',
        'price': 350000,
        'location': 'Kochi, Kerala',
        'description': (
            'A regal wedding experience with grand venues, traditional mandap '
            'decor, multi-cuisine catering and a dedicated wedding coordinator.'
        ),
        'packages': ['Mandap & floral decor', 'Multi-cuisine catering', 'Photography & film', 'Wedding music & band'],
        'image': 'pexels-alonssus-3212018.jpg',
    },
    {
        'title': 'Classic Wedding',
        'category': 'Wedding',
        'price': 220000,
        'location': 'Trivandrum, Kerala',
        'description': (
            'Timeless wedding styling — elegant floral decor, a warm ceremony '
            'setup and thoughtful planning for a classic celebration.'
        ),
        'packages': ['Elegant floral decor', 'Ceremony setup', 'Guest hospitality', 'Classic photography'],
        'image': 'pexels-breno-cardoso-149064345-18322558.jpg',
    },
    {
        'title': 'Destination Wedding',
        'category': 'Wedding',
        'price': 500000,
        'location': 'Goa',
        'description': (
            'A dream beach wedding — seaside altar, stay for guests, sunset '
            'vows and a beachside reception under the stars.'
        ),
        'packages': ['Beach altar setup', 'Guest stay package', 'Sunset ceremony', 'Beachside reception'],
        'image': 'pexels-nudethephotographer-37828118.jpg',
    },
    {
        'title': 'Intimate Wedding',
        'category': 'Wedding',
        'price': 120000,
        'location': 'Kochi, Kerala',
        'description': (
            'A cosy, close-to-home celebration — soft floral decor, a small '
            'reception and personal touches for up to 50 guests.'
        ),
        'packages': ['Soft floral decor', 'Small reception setup', 'Two-tier wedding cake', 'Personalised planning'],
        'image': 'pexels-thevisionaryvows-33417236.jpg',
    },
]

# ---------------------------------------------------------------------------
# Lifecycle assignment: which event titles get which status
# ---------------------------------------------------------------------------
LIFECYCLE_MAP = {
    # LIVE events (most of the catalogue)
    'Birthday Bash': 'live',
    'Kids Birthday Party': 'live',
    'Sweet 16 Celebration': 'live',
    'Grand Catering Service': 'live',
    'Multi-Cuisine Buffet': 'live',
    'Live Counter Catering': 'live',
    'Premium Wedding Catering': 'live',
    'Corporate Summit': 'live',
    'Conference & Seminar': 'live',
    'Annual Day Gala': 'live',
    'Intimate Wedding': 'live',
    'Royal Wedding': 'live',
    # PUBLISHED — approved and public but not yet live
    'Classic Wedding': 'published',
    # COMPLETED — events that already happened
    'DJ Night Party': 'completed',
    'Club DJ Experience': 'completed',
    # CANCELLED — event was called off
    'Destination Wedding': 'cancelled',
    # DRAFT
    'Milestone Birthday': 'draft',
    # UNDER_REVIEW
    'Team Offsite Retreat': 'under_review',
    # REJECTED
    'Pool Party DJ': 'rejected',
    # APPROVED
    'Festival DJ Show': 'approved',
}

CUSTOMERS = [
    ('priya', 'priya@example.com', 'Priya', 'Nair'),
    ('arjun', 'arjun@example.com', 'Arjun', 'Menon'),
    ('meera', 'meera@example.com', 'Meera', 'Kurian'),
    ('rahul', 'rahul@example.com', 'Rahul', 'Varma'),
]

# Booking scenarios: (username, event_title, days_from_today, status)
BOOKING_SCENARIOS = [
    ('priya', 'Royal Wedding', +45, 'confirmed'),
    ('priya', 'Birthday Bash', +20, 'pending'),
    ('arjun', 'DJ Night Party', -30, 'completed'),
    ('arjun', 'Classic Wedding', +60, 'pending'),
    ('meera', 'Corporate Summit', +15, 'confirmed'),
    ('meera', 'Club DJ Experience', -12, 'completed'),
    ('meera', 'Conference & Seminar', +90, 'pending'),
    ('rahul', 'Kids Birthday Party', +35, 'confirmed'),
    ('rahul', 'Royal Wedding', -8, 'completed'),
    ('priya', 'Grand Catering Service', +120, 'cancelled'),
]


class Command(BaseCommand):
    help = 'Seed Plannix with demo users, events, bookings and feedback.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding Plannix demo data...'))
        self._groups()
        users = self._users()
        categories = self._categories()
        events = self._events(users, categories)
        self._bookings(users, events)
        self._reviews(users, events)
        self._audit_logs(events, users)
        self.stdout.write(self.style.SUCCESS('Demo data is ready.'))

    # ------------------------------------------------------------------
    def _groups(self):
        for name in ('Attendee', 'EventOrganizer', 'Admin'):
            Group.objects.get_or_create(name=name)
        self.stdout.write('  groups: Attendee, EventOrganizer, Admin')

    def _users(self):
        users = {}

        # Admin superuser
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={
                'email': 'admin@plannix.app',
                'is_superuser': True,
                'is_staff': True,
            },
        )
        if created:
            password = os.environ.get('PLANNIX_ADMIN_PASSWORD') or secrets.token_urlsafe(9)
            admin.set_password(password)
            admin.save(update_fields=['password'])
            self.stdout.write(self.style.WARNING(
                f'  admin created — password: {password} '
                '(set PLANNIX_ADMIN_PASSWORD to choose your own)',
            ))
        else:
            self.stdout.write('  admin already exists (password untouched)')
        admin.groups.add(Group.objects.get(name='Admin'))
        users['admin'] = admin

        # Organizer accounts
        org_group = Group.objects.get(name='EventOrganizer')
        organizer_specs = [
            ('organizer1', 'organizer@plannix.app', 'Aravind', 'Kumar'),
            ('organizer2', 'organizer2@plannix.app', 'Deepa', 'Nair'),
            ('demot', 'demot@plannix.app', 'Rohit', 'Menon'),
            ('Doe', 'doe@plannix.app', 'Diana', 'Doe'),
        ]
        for username, email, first, last in organizer_specs:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'first_name': first,
                    'last_name': last,
                },
            )
            user.groups.add(org_group)
            if created or user.password == '' or not user.has_usable_password():
                user.set_password('organizer123')
                user.save(update_fields=['password'])
            OrganizerProfile.objects.get_or_create(
                user=user,
                defaults={'business_name': f'{first} {last} Events'},
            )
            users[username] = user

        # Attendee accounts
        att_group = Group.objects.get(name='Attendee')
        for username, email, first, last in CUSTOMERS:
            customer, created = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first, 'last_name': last},
            )
            customer.groups.add(att_group)
            if created or customer.password == '' or not customer.has_usable_password():
                customer.set_password('customer123')
                customer.save(update_fields=['password'])
            users[username] = customer

        # Organizations for approved and pending organizers
        from account_manager.models import Organization
        from django.utils import timezone as _tz
        now = _tz.now()

        org_approved, created = Organization.objects.get_or_create(
            owner=users['demot'],
            defaults={
                'name': 'Apex Event Planners',
                'status': 'approved',
                'is_verified': True,
                'submitted_at': now - timedelta(days=60),
                'approved_at': now - timedelta(days=50),
                'contact_number': '9876543210',
                'email': 'apex@plannix.app',
            },
        )
        if created:
            self.stdout.write('  org: Apex Event Planners (approved) created')

        org_pending, created = Organization.objects.get_or_create(
            owner=users['Doe'],
            defaults={
                'name': 'Evergreen Events Studio',
                'status': 'pending',
                'submitted_at': now - timedelta(days=5),
                'contact_number': '9876543211',
                'email': 'evergreen@plannix.app',
            },
        )
        if created:
            self.stdout.write('  org: Evergreen Events Studio (pending) created')

        self.stdout.write(f'  users: {", ".join(users)}')
        return users

    def _categories(self):
        """Create EventCategories with slugs and sort_order."""
        category_data = [
            ('Birthday', 'birthday', 1),
            ('Catering', 'catering', 2),
            ('Corporate', 'corporate', 3),
            ('DJ', 'dj', 4),
            ('Wedding', 'wedding', 5),
        ]
        cats = {}
        for name, slug, order in category_data:
            cat, _ = EventCategory.objects.get_or_create(
                name=name,
                defaults={'slug': slug, 'sort_order': order},
            )
            cats[name] = cat
        self.stdout.write(f'  categories: {", ".join(cats.keys())}')
        return cats

    def _events(self, users, categories):
        """Upsert the 20 events with lifecycle states and ownership."""
        now = timezone.now()
        created_count = 0
        events_map = {}

        for idx, spec in enumerate(EVENTS):
            title = spec['title']
            status = LIFECYCLE_MAP.get(title, 'live')
            category = categories.get(spec['category'])

            # Assign owner: alternate between organizer1 and organizer2
            owner = users['organizer1'] if idx % 2 == 0 else users['organizer2']

            # Build lifecycle timestamps based on status
            submitted_at = now - timedelta(days=30) if status != 'draft' else None
            approved_at = now - timedelta(days=20) if status in ('approved', 'published', 'live', 'completed') else None
            publish_at = now - timedelta(days=10) if status in ('published', 'live', 'completed') else None

            # Start/end dates vary by lifecycle state
            if status == 'completed':
                # Past event that already finished
                start_at = now - timedelta(days=60)
                end_at = now - timedelta(days=1)
            elif status == 'cancelled':
                # Was going to happen but got cancelled — past dates
                start_at = now - timedelta(days=10)
                end_at = now - timedelta(days=9)
            elif status in ('draft', 'under_review', 'rejected'):
                # Not yet scheduled — use placeholder future dates
                start_at = now + timedelta(days=14 + idx)
                end_at = start_at + timedelta(days=1)
            else:
                # approved, published, live — future event
                start_at = now + timedelta(days=14 + idx)
                end_at = start_at + timedelta(days=1)

            rejection_reason = ''
            if status == 'rejected':
                rejection_reason = 'Event description needs more detail. Please revise and resubmit.'

            event, created = Event.objects.update_or_create(
                title=title,
                defaults={
                    'owner': owner,
                    'category': category,
                    'price': spec['price'],
                    'location': spec['location'],
                    'description': spec['description'],
                    'contact_number': '9876543210',
                    'venue': spec['location'].split(',')[0] if ',' in spec['location'] else spec['location'],
                    'status': status,
                    'start_at': start_at,
                    'end_at': end_at,
                    'capacity': 100 + idx * 10,
                    'submitted_at': submitted_at,
                    'approved_at': approved_at,
                    'publish_at': publish_at,
                    'rejection_reason': rejection_reason,
                    'is_active': True,
                },
            )
            events_map[title] = event
            self._attach_image(event, spec['category'], spec['image'])
            self._create_inclusions(event, spec['packages'])
            created_count += int(created)

        self.stdout.write(f'  events: {created_count} created, {len(EVENTS) - created_count} updated')
        return events_map

    def _attach_image(self, event, category, source_name):
        """Copy image from event_images/<category>/ into media/events/."""
        folder = EVENT_IMAGE_DIR / CATEGORY_FOLDER[category]
        source = folder / source_name
        if not source.exists():
            self.stdout.write(self.style.WARNING(
                f'  skipping missing image: {source} (event "{event.title}")',
            ))
            return
        dest = settings.MEDIA_ROOT / 'events' / source_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            shutil.copyfile(source, dest)
        rel = f'events/{source_name}'
        if event.featured_image != rel:
            event.featured_image = rel
            event.save(update_fields=['featured_image'])

    def _create_inclusions(self, event, packages):
        """Create EventInclusion rows for an event."""
        # Only create if none exist for this event yet
        if event.inclusions.exists():
            return
        for i, name in enumerate(packages):
            EventInclusion.objects.create(event=event, name=name, sort_order=i)

    def _bookings(self, users, events):
        """Create demo bookings with event FK, attendee FK, snapshots.

        Re-runnable: purges orphaned legacy rows (created before the event FK
        existed) so the demo reflects the current domain model, then creates
        any scenario row that is missing for its (attendee, event) pair.
        """
        # Legacy rows from the pre-migration schema had no event FK — drop them.
        orphans = EventBooking.objects.filter(event__isnull=True)
        if orphans.exists():
            self.stdout.write(f'  bookings: removed {orphans.count()} orphaned legacy rows (no event FK)')
            orphans.delete()

        today = date.today()
        created = 0
        for username, event_title, delta, status in BOOKING_SCENARIOS:
            if event_title not in events:
                continue
            customer = users.get(username)
            event = events[event_title]
            if not customer or not event:
                continue
            existing = EventBooking.objects.filter(
                event=event, attendee=customer,
            ).exists()
            if existing:
                continue
            EventBooking.objects.create(
                event=event,
                attendee=customer,
                name=f'{customer.first_name} {customer.last_name}'.strip() or customer.username,
                email=customer.email,
                number='9876543210',
                event_title=event.title,
                price=event.price,
                event_location=event.location,
                event_date=today + timedelta(days=delta),
                status=status,
            )
            created += 1
        self.stdout.write(f'  bookings: {created} created, {EventBooking.objects.count()} total')

    def _reviews(self, users, events):
        """Create sample reviews for completed bookings."""
        if Review.objects.exists():
            self.stdout.write('  reviews: already seeded — skipped')
            return

        review_data = [
            ('arjun', 'DJ Night Party', 5, 'Amazing DJ setup! The sound system was top-notch.'),
            ('meera', 'Club DJ Experience', 4, 'Great night, professional team. Would recommend.'),
            ('rahul', 'Royal Wedding', 5, 'Flawless wedding planning. Our families loved every moment.'),
        ]

        for username, event_title, rating, comment in review_data:
            customer = users.get(username)
            event = events.get(event_title)
            if not customer or not event:
                continue
            booking = EventBooking.objects.filter(
                event=event, attendee=customer, status='completed',
            ).first()
            Review.objects.create(
                event=event,
                attendee=customer,
                booking=booking,
                rating=rating,
                comment=comment,
                moderation_status='approved',
            )
        self.stdout.write(f'  reviews: {Review.objects.count()} total')

    def _audit_logs(self, events, users):
        """Create audit log entries reflecting each event's lifecycle path.

        created_at is auto_now_add, so it cannot be set at insert time — we
        backfill the historical timestamp via .update() afterwards so the
        seeded logs read like a real lifecycle timeline.
        """
        if EventAuditLog.objects.exists():
            self.stdout.write('  audit_logs: already seeded — skipped')
            return

        def log(event, actor, action, frm, to, when, reason=''):
            entry = EventAuditLog.objects.create(
                event=event, actor=actor, action=action,
                from_status=frm, to_status=to, reason=reason,
            )
            if when is not None:
                EventAuditLog.objects.filter(pk=entry.pk).update(created_at=when)
            return entry

        admin = users['admin']
        now = timezone.now()
        count = 0

        for title, event in events.items():
            status = event.status
            # Every non-draft event was submitted
            if status != 'draft' and event.submitted_at:
                log(event, event.owner, 'submit', 'draft', 'under_review', event.submitted_at)
                count += 1

            # Rejected events also got a reject entry
            if status == 'rejected':
                when = event.submitted_at + timedelta(days=3) if event.submitted_at else now
                log(event, admin, 'reject', 'under_review', 'rejected', when,
                    event.rejection_reason or 'Needs more detail')
                count += 1

            # Approved or beyond got an approve entry
            if status in ('approved', 'published', 'live', 'completed') and event.approved_at:
                log(event, admin, 'approve', 'under_review', 'approved', event.approved_at)
                count += 1

            # Published or beyond got a publish entry
            if status in ('published', 'live', 'completed') and event.publish_at:
                log(event, admin, 'publish', 'approved', 'published', event.publish_at)
                count += 1

            # Live events got a go_live entry
            if status in ('live', 'completed'):
                when = event.publish_at + timedelta(days=5) if event.publish_at else now
                log(event, admin, 'go_live', 'published', 'live', when)
                count += 1

            # Completed events got a complete entry
            if status == 'completed':
                log(event, None, 'complete', 'live', 'completed', event.end_at or now)
                count += 1

            # Cancelled events got a cancel entry
            if status == 'cancelled':
                when = event.start_at - timedelta(days=2) if event.start_at else now
                log(event, admin, 'cancel', 'live', 'cancelled', when,
                    'Organiser requested cancellation')
                count += 1

        self.stdout.write(f'  audit_logs: {count} created')
