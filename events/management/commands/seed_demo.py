"""Seed the Plannix app with realistic demo data.

Usage:
    python manage.py seed_demo

Creates roles, an admin account (password from the PLANNIX_ADMIN_PASSWORD
environment variable, or a random one printed to the terminal), staff and
customer accounts, **20 individual event packages** — 5 categories (Birthday,
Catering, Corporate, DJ, Wedding) × 4 events each — where every event has its
own database record, its own unique name and **exactly one image** pulled from
``event_images/<category>/``, plus bookings across every status and sample
feedback.

The first run also cleans up the legacy demo events (the five bare-category
packages from an earlier single-event-per-category seed), then re-seeds the
new 20-event catalogue.

Idempotent where it matters: accounts and events are upserted by a stable
key (username / event name), images are copied into ``media/events/`` only
when missing (or when the source file has changed), and bookings/feedback are
only created when none exist yet — re-running never duplicates or destroys
data.
"""
import os
import secrets
import shutil
from datetime import date, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand

from events.models import Event_Booking, Event_Company
from themes.models import Feedback

# The demo event image set lives in event_images/<category>/ — each folder
# holds exactly the 4 images for that category. Every seeded event is linked
# to exactly one of those images (its own record, its own image). Images are
# copied into media/events/ keeping their original filenames.
EVENT_IMAGE_DIR = Path(settings.BASE_DIR) / 'event_images'

# Category → image-folder name. Corporate's folder is ``corperate`` (as it
# is on disk), so the mapping is explicit rather than a simple lowercase.
CATEGORY_FOLDER = {
    'Birthday': 'birthday',
    'Catering': 'catering',
    'Corporate': 'corperate',
    'DJ': 'dj',
    'Wedding': 'wedding',
}

# Legacy demo packages from the earlier seed (one event per category, each
# carrying a 4-image gallery). They are deleted on the first run of the new
# seed so the catalogue is rebuilt as 20 individual events.
LEGACY_DEMO_EVENT_NAMES = ['Birthday', 'Catering', 'Corporate', 'DJ', 'Wedding']

# ---------------------------------------------------------------------------
# The 20 event packages: 5 categories × 4 events.
#
# ``image`` is the exact source filename inside the category folder, so every
# event maps to precisely one image and categories never mix.
# ---------------------------------------------------------------------------
EVENTS = [
    # --- Birthday -----------------------------------------------------------
    {
        'event_name': 'Birthday Bash',
        'event_type': 'Birthday',
        'event_price': 60000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A lively birthday celebration with balloon decor, a custom cake '
            'and fun games — everything to make the birthday person feel '
            'extra special.'
        ),
        'packages': ['Balloon & themed decor', 'Custom theme cake', 'Games & entertainment', 'Photo booth & props'],
        'image': 'pexels-freestockpro-12616001.jpg',
    },
    {
        'event_name': 'Kids Birthday Party',
        'event_type': 'Birthday',
        'event_price': 40000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A safe, colourful party for little ones — character theme decor, '
            'a cartoon-style cake and a dedicated host for games and fun.'
        ),
        'packages': ['Character theme decor', 'Cartoon cake', 'Kids games & host', 'Party favours & props'],
        'image': 'pexels-rdne-4920988.jpg',
    },
    {
        'event_name': 'Sweet 16 Celebration',
        'event_type': 'Birthday',
        'event_price': 85000,
        'location': 'Trivandrum, Kerala',
        'event_description': (
            'A glamorous sweet-sixteen party with pastel decor, a dessert '
            'table, photo booth and DJ, styled around the birthday star.'
        ),
        'packages': ['Pastel floral decor', 'Dessert table', 'Photo booth', 'DJ & lighting'],
        'image': 'pexels-rdne-7363067.jpg',
    },
    {
        'event_name': 'Milestone Birthday',
        'event_type': 'Birthday',
        'event_price': 120000,
        'location': 'Bangalore, Karnataka',
        'event_description': (
            'An elegant milestone celebration with premium decor, gourmet '
            'dinner, live music and a personalised tribute video.'
        ),
        'packages': ['Premium floral decor', 'Gourmet dinner', 'Live music', 'Tribute video & photography'],
        'image': 'pexels-ron-lach-10032953.jpg',
    },
    # --- Catering -----------------------------------------------------------
    {
        'event_name': 'Grand Catering Service',
        'event_type': 'Catering',
        'event_price': 150000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'Full-service catering for large gatherings — a lavish multi-cuisine '
            'buffet served by an experienced team with elegant table setups.'
        ),
        'packages': ['Multi-cuisine buffet', 'Elegant table setup', 'Service staff', 'Beverage bar'],
        'image': 'pexels-kseniia-lopyreva-3299160-4959845.jpg',
    },
    {
        'event_name': 'Multi-Cuisine Buffet',
        'event_type': 'Catering',
        'event_price': 90000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A spread of regional and continental favourites — live counters, '
            'a dessert bar and on-site chefs for a memorable dining experience.'
        ),
        'packages': ['Live food counters', 'Continental & regional menu', 'Dessert bar', 'On-site chefs'],
        'image': 'pexels-novkov-visuals-34321369.jpg',
    },
    {
        'event_name': 'Live Counter Catering',
        'event_type': 'Catering',
        'event_price': 75000,
        'location': 'Chennai, Tamil Nadu',
        'event_description': (
            'Interactive live stations — pasta, dosa, chaat and grill counters — '
            'prepared fresh in front of your guests.'
        ),
        'packages': ['Pasta & grill counter', 'Dosa & chaat counter', 'Live dessert station', 'Beverage service'],
        'image': 'pexels-prosper-buka-1289782307-28736727.jpg',
    },
    {
        'event_name': 'Premium Wedding Catering',
        'event_type': 'Catering',
        'event_price': 280000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A regal wedding feast — traditional sadhya and fine-dining '
            'courses, ornate table styling and dedicated banquet service.'
        ),
        'packages': ['Traditional sadhya', 'Fine-dining courses', 'Ornate table styling', 'Banquet service team'],
        'image': 'pexels-stewphotography-12253092.jpg',
    },
    # --- Corporate ----------------------------------------------------------
    {
        'event_name': 'Corporate Summit',
        'event_type': 'Corporate',
        'event_price': 480000,
        'location': 'Bangalore, Karnataka',
        'event_description': (
            'Full-scale summit management — keynote stage with AV, guest '
            'registration, conference hall setup and refreshments for up to '
            '500 delegates.'
        ),
        'packages': ['Stage & AV setup', 'Guest registration & staff', 'Catering & refreshments', 'Conference hall setup'],
        'image': 'pexels-kaandurmus-9864907.jpg',
    },
    {
        'event_name': 'Conference & Seminar',
        'event_type': 'Corporate',
        'event_price': 250000,
        'location': 'Mumbai, Maharashtra',
        'event_description': (
            'Professional conference execution — projector and sound, panel '
            'seating, breaks and a help desk for a smooth, focused event.'
        ),
        'packages': ['Projector & sound', 'Panel seating & stage', 'Tea & coffee breaks', 'Help desk & staff'],
        'image': 'pexels-pavel-danilyuk-6405783.jpg',
    },
    {
        'event_name': 'Annual Day Gala',
        'event_type': 'Corporate',
        'event_price': 350000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A celebratory annual gala with awards ceremony, themed decor, '
            'dinner and entertainment for the whole company.'
        ),
        'packages': ['Awards ceremony & stage', 'Themed decor', 'Dinner & drinks', 'Live entertainment'],
        'image': 'pexels-reiez-35042249.jpg',
    },
    {
        'event_name': 'Team Offsite Retreat',
        'event_type': 'Corporate',
        'event_price': 180000,
        'location': 'Goa',
        'event_description': (
            'A relaxed offsite with team-building activities, beachside '
            'accommodation, group meals and a closing bonfire night.'
        ),
        'packages': ['Team-building activities', 'Beachside stay', 'Group meals', 'Bonfire night'],
        'image': 'pexels-reiez-35042461.jpg',
    },
    # --- DJ -----------------------------------------------------------------
    {
        'event_name': 'DJ Night Party',
        'event_type': 'DJ',
        'event_price': 45000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A high-energy DJ night with a pro sound system, laser and stage '
            'lighting and a glowing dance floor to keep the party going.'
        ),
        'packages': ['DJ & music system', 'Laser & stage lighting', 'Dance floor & neon decor', 'Host & sound engineer'],
        'image': 'pexels-ellis-5949085.jpg',
    },
    {
        'event_name': 'Club DJ Experience',
        'event_type': 'DJ',
        'event_price': 60000,
        'location': 'Bangalore, Karnataka',
        'event_description': (
            'An immersive club-style night — open-format DJ sets, VIP booth, '
            'crystal-clear sound and a professional light show.'
        ),
        'packages': ['Open-format DJ sets', 'VIP booth & guest list', 'Crystal sound system', 'Light show'],
        'image': 'pexels-joshua-sanchez-1713464086-29263194.jpg',
    },
    {
        'event_name': 'Pool Party DJ',
        'event_type': 'DJ',
        'event_price': 55000,
        'location': 'Goa',
        'event_description': (
            'Sun-down beats by the pool — tropical DJ sets, ambient lighting, '
            'a mini dance deck and chilled cocktails for the crowd.'
        ),
        'packages': ['Tropical DJ sets', 'Ambient pool lighting', 'Mini dance deck', 'Chilled cocktail bar'],
        'image': 'pexels-leonardo-delsabio-2150529415-35243129.jpg',
    },
    {
        'event_name': 'Festival DJ Show',
        'event_type': 'DJ',
        'event_price': 95000,
        'location': 'Mumbai, Maharashtra',
        'event_description': (
            'A big-stage festival show — main-stage DJ, huge LED screens, '
            'confetti and pyro effects for a truly unforgettable set.'
        ),
        'packages': ['Main-stage DJ', 'LED screens', 'Confetti & pyro effects', 'Stage crew'],
        'image': 'pexels-yankrukov-9005499.jpg',
    },
    # --- Wedding ------------------------------------------------------------
    {
        'event_name': 'Royal Wedding',
        'event_type': 'Wedding',
        'event_price': 350000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A regal wedding experience with grand venues, traditional mandap '
            'decor, multi-cuisine catering and a dedicated wedding coordinator.'
        ),
        'packages': ['Mandap & floral decor', 'Multi-cuisine catering', 'Photography & film', 'Wedding music & band'],
        'image': 'pexels-alonssus-3212018.jpg',
    },
    {
        'event_name': 'Classic Wedding',
        'event_type': 'Wedding',
        'event_price': 220000,
        'location': 'Trivandrum, Kerala',
        'event_description': (
            'Timeless wedding styling — elegant floral decor, a warm ceremony '
            'setup and thoughtful planning for a classic celebration.'
        ),
        'packages': ['Elegant floral decor', 'Ceremony setup', 'Guest hospitality', 'Classic photography'],
        'image': 'pexels-breno-cardoso-149064345-18322558.jpg',
    },
    {
        'event_name': 'Destination Wedding',
        'event_type': 'Wedding',
        'event_price': 500000,
        'location': 'Goa',
        'event_description': (
            'A dream beach wedding — seaside altar, stay for guests, sunset '
            'vows and a beachside reception under the stars.'
        ),
        'packages': ['Beach altar setup', 'Guest stay package', 'Sunset ceremony', 'Beachside reception'],
        'image': 'pexels-nudethephotographer-37828118.jpg',
    },
    {
        'event_name': 'Intimate Wedding',
        'event_type': 'Wedding',
        'event_price': 120000,
        'location': 'Kochi, Kerala',
        'event_description': (
            'A cosy, close-to-home celebration — soft floral decor, a small '
            'reception and personal touches for up to 50 guests.'
        ),
        'packages': ['Soft floral decor', 'Small reception setup', 'Two-tier wedding cake', 'Personalised planning'],
        'image': 'pexels-thevisionaryvows-33417236.jpg',
    },
]

CUSTOMERS = [
    ('priya', 'priya@example.com', 'Priya', 'Nair'),
    ('arjun', 'arjun@example.com', 'Arjun', 'Menon'),
    ('meera', 'meera@example.com', 'Meera', 'Kurian'),
    ('rahul', 'rahul@example.com', 'Rahul', 'Varma'),
]

FEEDBACK = [
    ('Ananya', 'ananya@example.com', '9876500001', 'Planning our wedding with Plannix was effortless. The team handled everything!'),
    ('Vishnu', 'vishnu@example.com', '9876500002', 'The corporate summit was flawless — stage, AV, catering, all perfect.'),
    ('Sara', 'sara@example.com', '9876500003', 'Loved the beach proposal package. Truly a once-in-a-lifetime experience.'),
    ('Kiran', 'kiran@example.com', '9876500004', 'Very responsive team. They made booking our anniversary gala so simple.'),
    ('Divya', 'divya@example.com', '9876500005', 'From the first call to the final event, everything exceeded expectations.'),
]


class Command(BaseCommand):
    help = 'Seed Plannix with demo users, events, bookings and feedback.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.MIGRATE_HEADING('Seeding Plannix demo data…'))
        self._roles()
        users = self._users()
        events = self._events()
        self._bookings(users, events)
        self._feedback()
        self.stdout.write(self.style.SUCCESS('Demo data is ready.'))

    # ------------------------------------------------------------------
    def _roles(self):
        for name in ('admin', 'staff', 'customer'):
            Group.objects.get_or_create(name=name)
        self.stdout.write('  roles: admin, staff, customer')

    def _users(self):
        """Create admin (from env/random password), staff and customers."""
        users = {}

        # Admin superuser — password from env, else random and printed.
        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'email': 'admin@plannix.app', 'is_superuser': True, 'is_staff': True},
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
        users['admin'] = admin

        # Staff account.
        staff, _ = User.objects.get_or_create(
            username='staff1',
            defaults={'email': 'staff@plannix.app', 'first_name': 'Riya', 'last_name': 'Thomas'},
        )
        staff.groups.add(Group.objects.get(name='staff'))
        if staff.password == '' or not staff.has_usable_password():
            staff.set_password('staffpass123')
            staff.save(update_fields=['password'])
        users['staff'] = staff

        # Customer accounts.
        for username, email, first, last in CUSTOMERS:
            customer, _ = User.objects.get_or_create(
                username=username,
                defaults={'email': email, 'first_name': first, 'last_name': last},
            )
            if customer.password == '' or not customer.has_usable_password():
                customer.set_password('customer123')
                customer.save(update_fields=['password'])
            users[username] = customer

        self.stdout.write(f'  users: {", ".join(users)}')
        return users

    def _events(self):
        """Remove legacy demo events, then upsert the 20 individual packages.

        Each event is upserted by its unique ``event_name`` and linked to
        exactly one image from its category folder.
        """
        legacy = Event_Company.objects.filter(event_name__in=LEGACY_DEMO_EVENT_NAMES)
        if legacy.exists():
            self.stdout.write(f'  cleaned legacy demo events: {legacy.count()}')
            legacy.delete()

        created_count = 0
        for spec in EVENTS:
            event, created = Event_Company.objects.update_or_create(
                event_name=spec['event_name'],
                defaults={
                    'event_type': spec['event_type'],
                    'event_price': spec['event_price'],
                    'location': spec['location'],
                    'event_description': spec['event_description'],
                    'event_mobile_number': '9876543210',
                    'package1': spec['packages'][0],
                    'package2': spec['packages'][1],
                    'package3': spec['packages'][2],
                    'package4': spec['packages'][3],
                },
            )
            self._attach_image(event, spec['event_type'], spec['image'])
            created_count += int(created)
        self.stdout.write(f'  events: {created_count} created, {len(EVENTS) - created_count} updated')
        return list(Event_Company.objects.filter(event_name__in=[s['event_name'] for s in EVENTS]))

    def _attach_image(self, event, category, source_name):
        """Copy one image from event_images/<category>/ into media/events/ and link it.

        Uses the source filename as-is (no renaming). Copies only when the
        destination is missing or differs in size, so re-running the seed is
        safe and never clobbers an uploaded file.
        """
        folder = EVENT_IMAGE_DIR / CATEGORY_FOLDER[category]
        source = folder / source_name
        if not source.exists():
            raise FileNotFoundError(
                f'Missing seed image: {source} (event "{event.event_name}")',
            )
        dest = settings.MEDIA_ROOT / 'events' / source_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or dest.stat().st_size != source.stat().st_size:
            shutil.copyfile(source, dest)
        rel = f'events/{source_name}'
        if event.event_img != rel:
            event.event_img = rel
            event.save(update_fields=['event_img'])

    def _bookings(self, users, events):
        """Seed bookings only when none exist yet (never duplicates)."""
        if Event_Booking.objects.exists():
            self.stdout.write('  bookings: already seeded — skipped')
            return

        def pick(event_type):
            return next(e for e in events if e.event_type == event_type)

        today = date.today()
        # (customer, event_type, days_from_today, status)
        scenarios = [
            ('priya', 'Wedding', +45, 'confirmed'),
            ('priya', 'Birthday', +20, 'pending'),
            ('arjun', 'DJ', -30, 'completed'),
            ('arjun', 'Wedding', +60, 'pending'),
            ('meera', 'Corporate', +15, 'confirmed'),
            ('meera', 'DJ', -12, 'completed'),
            ('meera', 'Corporate', +90, 'pending'),
            ('rahul', 'Birthday', +35, 'confirmed'),
            ('rahul', 'Wedding', -8, 'completed'),
            ('priya', 'Catering', +120, 'cancelled'),
        ]
        for username, event_type, delta, status in scenarios:
            customer = users[username]
            event = pick(event_type)
            Event_Booking.objects.create(
                user=customer,
                name=f'{customer.first_name} {customer.last_name}'.strip() or customer.username,
                email=customer.email,
                number='9876543210',
                event_company_name=event.event_name,
                event_type=event.event_type,
                event_price=event.event_price,
                event_location=event.location,
                event_mobile_number=event.event_mobile_number,
                event_booking_date=(today + timedelta(days=delta)).isoformat(),
                status=status,
            )
        self.stdout.write(f'  bookings: {len(scenarios)} created')

    def _feedback(self):
        if Feedback.objects.exists():
            self.stdout.write('  feedback: already seeded — skipped')
            return
        for name, email, number, message in FEEDBACK:
            Feedback.objects.create(name=name, email=email, number=number, message=message)
        self.stdout.write(f'  feedback: {len(FEEDBACK)} created')
