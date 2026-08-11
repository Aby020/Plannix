"""Capture the Plannix README screenshots using Playwright + the system Chrome.

Requires:  pip install playwright
Uses the installed Chrome (channel='chrome') so no browser download is needed.
Output:    screenshots/*.png — the 01–14 numbered shots referenced in README.md.

Run from the project root with the dev server on 127.0.0.1:8009.

Demo accounts (from ``manage.py seed_demo``):
    admin  / PLANNIX_ADMIN_PASSWORD
    staff1 / staffpass123
    priya  / customer123
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

# (filename, path, full_page, element_selector)
PUBLIC_SHOTS = [
    ('01-events-birthday', '/events?type=Birthday', False, None),
    ('02-about-mission', '/about', False,
     'section.px-section:has(.px-eyebrow:text("Our Mission"))'),
    ('03-feedback-form', '/feedback', False, None),
    ('04-about-page', '/about', True, None),
    ('05-events-all', '/events', False, None),
    ('06-login', '/sign-in', False, None),
    ('07-register', '/sign-up', False, None),
    ('09-booking-success', '/success', False, None),
]

# (filename, path, full_page, element_selector) per role — shot while signed in.
ROLE_SHOTS = {
    'customer': {
        'credentials': ('priya', 'customer123'),
        'shots': [
            ('08-book-event', None, False, None),  # path resolved below
            ('10-customer-dashboard', '/customer-dashboard', False, None),
        ],
    },
    'staff': {
        'credentials': ('staff1', 'staffpass123'),
        'shots': [
            ('11-staff-dashboard', '/staff-dashboard', False, None),
        ],
    },
    'admin': {
        'credentials': ('admin', os.environ.get('PLANNIX_ADMIN_PASSWORD', '')),
        'shots': [
            ('12-admin-dashboard', '/admin-dashboard', False, None),
            ('13-manage-events', '/manage/events', False, None),
            ('14-manage-feedback', '/manage/feedback', False, None),
        ],
    },
}


def booking_event_id():
    """The seeded event the booking-form screenshot is pre-filled with."""
    from events.models import Event_Company

    pk = (
        Event_Company.objects.filter(event_name='Royal Wedding')
        .values_list('id', flat=True)
        .first()
    )
    return pk or Event_Company.objects.order_by('id').values_list('id', flat=True).first()


def capture(page, name, path, full_page, selector):
    page.goto(f'{BASE_URL}{path}', wait_until='networkidle')
    page.wait_for_timeout(1200)  # let toasts/counters/reveals settle
    page.evaluate(FORCE_VISIBLE)
    page.wait_for_timeout(500)
    target = OUT / f'{name}.png'
    if selector:
        page.locator(selector).screenshot(path=str(target))
    else:
        page.screenshot(path=str(target), full_page=full_page)
    print(f'  saved {target.name}')


def main():
    import django

    django.setup()
    event_id = booking_event_id()
    print(f'Booking-form event id: {event_id}')

    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        ctx = browser.new_context(
            viewport={'width': 1440, 'height': 900},
            device_scale_factor=1,
        )
        page = ctx.new_page()

        print('Public pages…')
        for name, path, full, selector in PUBLIC_SHOTS:
            capture(page, name, path, full, selector)

        for role, cfg in ROLE_SHOTS.items():
            username, password = cfg['credentials']
            # Log out of any previous role's session first.
            page.goto(f'{BASE_URL}/sign-out', wait_until='networkidle')
            page.wait_for_timeout(400)
            print(f'Signing in as {username}…')
            page.goto(f'{BASE_URL}/sign-in', wait_until='networkidle')
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('form button[type="submit"]')
            page.wait_for_load_state('networkidle')
            page.wait_for_timeout(700)
            if page.url.rstrip('/').endswith('/sign-in'):
                print(f'  !! login failed for {username}')
                continue
            for name, path, full, selector in cfg['shots']:
                if path is None:
                    path = f'/event-booking-form/{event_id}'
                capture(page, name, path, full, selector)

        browser.close()
    print('Done — screenshots are in screenshots/.')


if __name__ == '__main__':
    main()
