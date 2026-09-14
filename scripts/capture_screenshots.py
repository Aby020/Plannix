"""Capture the Plannix README screenshots using Playwright + the system Chrome.

Targets exactly the nine README gallery views on the CURRENT application and
produces compact 1280x800 page-level captures (no giant full-page images):

    screenshots/home.png                  Home hero (public)
    screenshots/sign-in.png               Sign in (public)
    screenshots/register.png              Create account (public)
    screenshots/discover.png              Discover grid (public, /events)
    screenshots/booking-confirmation.png  Booking receipt (/success, attendee)
    screenshots/my-bookings.png           My Bookings (attendee)
    screenshots/organizer-dashboard.png   Organizer dashboard
    screenshots/admin-dashboard.png       Admin dashboard
    screenshots/approval-queue.png        Organization approval queue (admin)

Requires:  pip install playwright, a system Chrome install, a running dev
server on 127.0.0.1:8009, and the demo database seeded via
``python manage.py seed_demo``.

Demo accounts (created by ``manage.py seed_demo``):
    admin      / PLANNIX_ADMIN_PASSWORD (pin it with set_admin_password)
    organizer1 / organizer123
    priya      / customer123
"""
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Plannix.settings')

BASE_URL = os.environ.get('PLANNIX_BASE_URL', 'http://127.0.0.1:8009')
OUT = BASE / 'screenshots'
OUT.mkdir(exist_ok=True)

VIEWPORT = {'width': 1280, 'height': 800}

# Bring reveal-on-scroll content into view so it is visible in captures.
FORCE_VISIBLE = """
document.querySelectorAll('.reveal, .reveal-stagger, .reveal-stagger > *')
  .forEach(function (el) {
    el.classList.add('reveal-visible');
    el.style.opacity = '1';
    el.style.transform = 'none';
    el.style.transition = 'none';
  });
"""

PUBLIC_SHOTS = [
    ('home', '/'),
    ('sign-in', '/sign-in'),
    ('register', '/sign-up'),
    ('discover', '/events'),
]


def capture(page, name, path):
    page.goto(f'{BASE_URL}{path}', wait_until='networkidle')
    page.wait_for_timeout(1000)  # let toasts/counters/reveals settle
    page.evaluate(FORCE_VISIBLE)
    page.wait_for_timeout(500)
    page.screenshot(path=str(OUT / f'{name}.png'))  # viewport-sized only
    print(f'  saved {name}.png')


def sign_in(page, username, password):
    page.goto(f'{BASE_URL}/sign-in', wait_until='networkidle')
    page.fill('input[name="username"]', username)
    page.fill('input[name="password"]', password)
    page.click('form button[type="submit"]')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(700)
    if page.url.split('?')[0].rstrip('/').endswith('/sign-in'):
        raise RuntimeError(f'!! login failed for {username}')


def attendee_booking_id():
    """The attendee's most current live booking, for the confirmation receipt.

    Picks a non-cancelled booking for the demo attendee ``priya`` so the
    ``/success?booking=<id>`` receipt renders the booking panel.
    """
    from django.contrib.auth.models import User
    from django.utils import timezone

    priya = User.objects.get(username='priya')
    booking = (
        priya.bookings.exclude(status='cancelled')
        .filter(event_date__gte=timezone.localdate())
        .order_by('event_date', '-created_at')
        .first()
    )
    if booking is None:
        booking = priya.bookings.exclude(status='cancelled').first()
    if booking is None:
        raise SystemExit('No bookable demo booking found for priya — seed_demo first.')
    return booking.pk


def main():
    import django

    django.setup()
    booking_id = attendee_booking_id()
    print(f'Booking-confirmation booking id: {booking_id}')

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)

        # --- Public pages ---
        print('Public pages…')
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        for name, path in PUBLIC_SHOTS:
            capture(page, name, path)
        ctx.close()

        # --- Attendee (priya): booking receipt + My Bookings ---
        print('Signing in as attendee (priya)…')
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        sign_in(page, 'priya', 'customer123')
        capture(page, 'booking-confirmation', f'/success?booking={booking_id}')
        capture(page, 'my-bookings', '/my-bookings')
        ctx.close()

        # --- Organizer (organizer1) ---
        print('Signing in as organizer (organizer1)…')
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        sign_in(page, 'organizer1', 'organizer123')
        capture(page, 'organizer-dashboard', '/organizer-dashboard')
        ctx.close()

        # --- Admin ---
        admin_password = os.environ.get('PLANNIX_ADMIN_PASSWORD', '')
        if not admin_password:
            raise SystemExit('PLANNIX_ADMIN_PASSWORD is not set — cannot sign in as admin.')
        print('Signing in as admin…')
        ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        page = ctx.new_page()
        sign_in(page, 'admin', admin_password)
        capture(page, 'admin-dashboard', '/admin-dashboard')
        capture(page, 'approval-queue', '/admin/approval-queue')
        ctx.close()

        browser.close()
    print('Done — screenshots are in screenshots/.')


if __name__ == '__main__':
    main()