"""Test suite for the Plannix events module (Phase 1 redesign).

Covers the public LIVE catalogue, transactional booking flow, role-based
dashboards (admin / organizer / attendee), organizer ownership-scoped views,
and admin lifecycle management.
"""
from datetime import date, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.core.management import call_command
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from themes.models import Feedback

from .models import (
    BookingPayment,
    Event,
    EventAuditLog,
    EventBooking,
    EventCategory,
    Review,
)
from .management.commands.upload_live_images import LIVE_IMAGE_MAP
from .payments import (
    PaymentError,
    advance_amount,
    create_order,
    gateway_configured,
    handle_webhook,
    remaining_amount,
    verify_payment_signature,
)
from .pulse import average_rating
from .services import (
    approve,
    approve_and_go_live,
    cancel,
    complete,
    edit_sets_draft,
    go_live,
    publish,
    publish_and_go_live,
    reject,
    resubmit,
    submit,
)

from account_manager.models import Organization
from account_manager.services import (
    approve_organization as approve_org,
    reject_organization as reject_org_svc,
    resubmit_organization as resubmit_org_svc,
    submit_organization as submit_org,
)

# A minimal valid 1x1 PNG used for featured_image uploads in form tests.
PNG_1PX = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)


def make_image_file(name='event.png'):
    return SimpleUploadedFile(name, PNG_1PX, content_type='image/png')

# ALLOWED_HOSTS only permits 127.0.0.1/localhost in production-style runs,
# so the default 'testserver' host is rejected. Point the client at localhost.


class PlannixTestCase(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.attendee_group, _ = Group.objects.get_or_create(name='Attendee')
        self.organizer_group, _ = Group.objects.get_or_create(name='EventOrganizer')
        self.admin_group, _ = Group.objects.get_or_create(name='Admin')

    # ---- helpers ----
    def make_user(self, username='attendee', group='Attendee', **kwargs):
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='testpass123',
            **kwargs,
        )
        if group:
            user.groups.add(Group.objects.get(name=group))
        return user

    def make_category(self, name='Wedding'):
        return EventCategory.objects.create(name=name)

    def make_event(self, owner=None, category=None, **overrides):
        data = {
            'title': 'Royal Wedding Package',
            'description': 'A complete wedding planning package.',
            'price': 150000,
            'location': 'Kochi, Kerala',
            'venue': 'Grand Hyatt',
            'contact_number': '9876543210',
            'capacity': 100,
            'status': 'live',
        }
        data.update(overrides)
        if owner is not None:
            data['owner'] = owner
        if category is not None:
            data['category'] = category
        return Event.objects.create(**data)

    def make_booking(self, attendee, event, **overrides):
        data = {
            'event': event,
            'attendee': attendee,
            'name': attendee.get_full_name() or attendee.username,
            'email': attendee.email,
            'number': '9876543210',
            'event_title': event.title,
            'price': event.price,
            'event_location': event.location,
            'event_date': date.today() + timedelta(days=7),
            'status': 'pending',
        }
        data.update(overrides)
        return EventBooking.objects.create(**data)

    def make_org(self, owner, status='approved', **overrides):
        """Create (and by default approve) an Organization for ``owner``."""
        org = Organization.objects.create(
            owner=owner, name='Events Co.',
            description='Planning.', contact_number='9876543210', **overrides,
        )
        if status == 'approved':
            submit_org(org)
            approve_org(org, owner)
            org.refresh_from_db()
        return org


# ---------------------------------------------------------------------------
# Public catalogue (LIVE only)
# ---------------------------------------------------------------------------

class PublicCatalogueTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        owner = self.make_user(username='org1', group='EventOrganizer')
        self.wedding_cat = self.make_category('Wedding')
        self.corp_cat = self.make_category('Corporate')
        self.wedding = self.make_event(
            owner, self.wedding_cat, title='Grand Wedding', price=200000)
        self.party = self.make_event(owner, self.corp_cat, title='Corporate Party')

    def test_index_page_renders(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plannix')

    def test_events_page_lists_live_only(self):
        # A draft event must NOT appear in the public catalogue.
        self.make_event(self.wedding.owner, status='draft', title='Hidden Draft')
        response = self.client.get(reverse('events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertContains(response, 'Corporate Party')
        self.assertNotContains(response, 'Hidden Draft')

    def test_events_page_filters_by_category_slug(self):
        response = self.client.get(reverse('events'), {'category': self.wedding_cat.slug})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertNotContains(response, 'Corporate Party')

    def test_readmore_shows_live_event(self):
        response = self.client.get(reverse('readmore', args=[self.wedding.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertContains(response, 'A complete wedding planning package.')

    def test_readmore_non_live_event_is_404(self):
        draft = self.make_event(self.wedding.owner, status='draft', title='Draft Event')
        response = self.client.get(reverse('readmore', args=[draft.pk]))
        self.assertEqual(response.status_code, 404)

    def test_readmore_missing_event_is_404(self):
        response = self.client.get(reverse('readmore', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_search_by_name(self):
        response = self.client.get(reverse('searching_events'), {'q': 'wedding'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')

    def test_search_only_returns_live(self):
        self.make_event(self.wedding.owner, status='draft', title='Draft Wedding')
        response = self.client.get(reverse('searching_events'), {'q': 'wedding'})
        self.assertContains(response, 'Grand Wedding')
        self.assertNotContains(response, 'Draft Wedding')

    def test_search_with_no_results(self):
        response = self.client.get(reverse('searching_events'), {'q': 'nonexistentxyz'})
        self.assertEqual(response.status_code, 200)

    def test_search_with_blank_term(self):
        response = self.client.get(reverse('searching_events'), {'q': ''})
        self.assertEqual(response.status_code, 200)

    def test_about_page_renders(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Booking flow
# ---------------------------------------------------------------------------

class BookingFlowTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user(username='attendee1')
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.owner)

    def test_booking_form_requires_login(self):
        response = self.client.get(reverse('selected_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('sign_in'), response.url)

    def test_booking_form_renders_live_event(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('selected_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_booking_form_non_live_event_is_404(self):
        draft = self.make_event(self.owner, status='draft', title='Draft')
        self.client.force_login(self.user)
        response = self.client.get(reverse('selected_event', args=[draft.pk]))
        self.assertEqual(response.status_code, 404)

    def post_booking(self, follow=False, **overrides):
        payload = {
            'event_id': self.event.pk,
            'name': 'Test Attendee',
            'email': self.user.email,
            'number': '9876543210',
            'event_location': self.event.location,
            'date': (date.today() + timedelta(days=7)).isoformat(),
        }
        payload.update(overrides)
        return self.client.post(reverse('event_booking'), payload, follow=follow)

    def test_create_booking_success(self):
        self.client.force_login(self.user)
        response = self.post_booking()
        booking = EventBooking.objects.get(attendee=self.user)
        self.assertRedirects(
            response, f"{reverse('success')}?booking={booking.pk}")
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.event_title, self.event.title)
        # No online advance payment is created in the booking flow.
        self.assertFalse(BookingPayment.objects.exists())

    def test_booking_confirmation_page_shows_details_and_organizer_contact(self):
        """The confirmation page displays the booking and organizer contact."""
        self.client.force_login(self.user)
        response = self.post_booking(follow=True)
        booking = EventBooking.objects.get(attendee=self.user)
        self.assertContains(response, 'Booking received')
        self.assertContains(response, booking.booking_reference)
        self.assertContains(response, self.event.title)
        self.assertContains(
            response, 'For payment details, please contact the event organizer directly.')
        # Organizer's registered email and contact phone are easy to find.
        self.assertContains(response, self.owner.email)
        self.assertContains(response, self.event.contact_number)

    def test_booking_confirmation_page_has_no_pay_advance(self):
        """No advance-payment step appears on the confirmation page."""
        self.client.force_login(self.user)
        response = self.post_booking(follow=True)
        self.assertNotContains(response, 'Pay Advance')
        self.assertNotContains(response, 'Advance (')

    def test_booking_rejects_past_date(self):
        self.client.force_login(self.user)
        response = self.post_booking(
            date=(date.today() - timedelta(days=1)).isoformat(), follow=True)
        self.assertContains(response, 'date in the past')
        self.assertEqual(EventBooking.objects.count(), 0)

    def test_booking_rejects_invalid_number(self):
        self.client.force_login(self.user)
        response = self.post_booking(number='12345', follow=True)
        self.assertContains(response, '10-digit mobile number')
        self.assertEqual(EventBooking.objects.count(), 0)

    def test_booking_rejects_duplicate_active_booking(self):
        self.client.force_login(self.user)
        self.make_booking(self.user, self.event)
        response = self.post_booking(follow=True)
        self.assertContains(response, 'already have an active booking')
        self.assertEqual(EventBooking.objects.count(), 1)

    def test_booking_rejects_missing_fields(self):
        self.client.force_login(self.user)
        response = self.post_booking(name='', follow=True)
        self.assertContains(response, 'required fields')
        self.assertEqual(EventBooking.objects.count(), 0)

    def test_booking_rejects_non_live_event(self):
        self.client.force_login(self.user)
        self.event.status = 'draft'
        self.event.save(update_fields=['status'])
        response = self.post_booking(follow=True)
        self.assertContains(response, 'valid event to book')
        self.assertEqual(EventBooking.objects.count(), 0)

    def test_capacity_blocks_second_booking(self):
        # Small-capacity event: first booking succeeds, second (different
        # attendee) must be rejected with a capacity message.
        self.event.capacity = 1
        self.event.save(update_fields=['capacity'])

        self.client.force_login(self.user)
        response = self.post_booking()
        booking = EventBooking.objects.get(attendee=self.user)
        self.assertRedirects(
            response, f"{reverse('success')}?booking={booking.pk}")
        self.assertEqual(EventBooking.objects.count(), 1)

        other = self.make_user(username='attendee2')
        self.client.force_login(other)
        response = self.post_booking(follow=True)
        self.assertContains(response, 'maximum capacity')
        self.assertEqual(EventBooking.objects.count(), 1)

    def test_double_submit_creates_only_one_booking(self):
        # Simulates a rapid double-click: the first request books, the second
        # (same event + attendee) is rejected by the server-side guard, so a
        # duplicate booking is never created.
        self.client.force_login(self.user)
        first = self.post_booking()
        booking = EventBooking.objects.get(attendee=self.user)
        self.assertRedirects(
            first, f"{reverse('success')}?booking={booking.pk}")
        second = self.post_booking(follow=True)
        self.assertContains(second, 'already have an active booking')
        self.assertEqual(EventBooking.objects.count(), 1)


# ---------------------------------------------------------------------------
# Attendee dashboards & bookings
# ---------------------------------------------------------------------------

class AttendeeDashboardTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user(username='attendee1')
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.owner)
        self.booking = self.make_booking(self.user, self.event)

    def test_dashboard_routes_attendee(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('attendee_dashboard'))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_attendee_dashboard_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('attendee_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_my_bookings_lists_own_bookings_only(self):
        other = self.make_user(username='other')
        self.make_booking(other, self.event)
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, self.event.title)
        self.assertContains(response, '1 booking')

    def test_cancel_booking(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('cancel_booking', args=[self.booking.pk]), follow=True)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'cancelled')
        self.assertContains(response, 'has been cancelled')

    def test_completed_booking_cannot_be_cancelled(self):
        self.booking.status = 'completed'
        self.booking.save(update_fields=['status'])
        self.client.force_login(self.user)
        self.client.post(reverse('cancel_booking', args=[self.booking.pk]), follow=True)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'completed')

    def test_cannot_cancel_someone_elses_booking(self):
        other = self.make_user(username='other')
        other_booking = self.make_booking(other, self.event)
        self.client.force_login(self.user)
        response = self.client.post(reverse('cancel_booking', args=[other_booking.pk]))
        self.assertEqual(response.status_code, 404)
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, 'pending')


# ---------------------------------------------------------------------------
# Organizer management
# ---------------------------------------------------------------------------

class OrganizerManagementTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.attendee = self.make_user(username='attendee1')
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.org = self.make_org(self.organizer)   # approved org — creation auto-lives
        self.event = self.make_event(self.organizer)
        self.booking = self.make_booking(self.attendee, self.event)
        self.feedback = Feedback.objects.create(
            name='Jane', email='jane@example.com', number='9876543210',
            message='Amazing service!',
        )

    def test_organizer_dashboard_renders(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_attendee_blocked_from_organizer_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_manage_events_lists_own_events(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        self.make_event(other_org, title='Somebody Else Event')
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('manage_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)
        self.assertNotContains(response, 'Somebody Else Event')

    def test_create_event(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('add_event'), {
            'title': 'Birthday Bash',
            'description': 'A fun birthday package.',
            'price': '50000',
            'location': 'Kochi, Kerala',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.assertRedirects(response, reverse('my_events'))
        event = Event.objects.get(title='Birthday Bash')
        self.assertEqual(event.owner, self.organizer)
        self.assertEqual(event.status, 'live')
        self.assertEqual(event.organization, self.org)

    def test_create_event_requires_required_fields(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse('add_event'), {'title': ''}, follow=True)
        self.assertEqual(Event.objects.count(), 1)  # only the seed event

    def test_event_form_has_no_date_venue_fields(self):
        """Package creation no longer collects start/end dates or venue."""
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('add_event'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'f_venue')
        self.assertNotContains(response, 'f_start_at')
        self.assertNotContains(response, 'f_end_at')
        self.assertNotContains(response, 'name="venue"')
        self.assertNotContains(response, 'name="start_at"')
        self.assertNotContains(response, 'name="end_at"')

    def test_event_form_preserves_location_and_essential_fields(self):
        """Location/service area, price, capacity and contact remain."""
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('add_event'))
        self.assertContains(response, 'name="location"')
        self.assertContains(response, 'name="price"')
        self.assertContains(response, 'name="capacity"')
        self.assertContains(response, 'name="contact_number"')
        self.assertContains(response, 'name="title"')
        self.assertContains(response, 'name="category"')
        self.assertContains(response, 'name="description"')

    def test_create_event_without_dates_or_venue(self):
        """A package can be created with no start/end dates and no venue."""
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('add_event'), {
            'title': 'No Date Package',
            'description': 'A package with no fixed dates or venue.',
            'price': '25000',
            'location': 'Kochi, Kerala',
            'capacity': '100',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.assertRedirects(response, reverse('my_events'))
        event = Event.objects.get(title='No Date Package')
        self.assertEqual(event.status, 'live')
        self.assertIsNone(event.start_at)
        self.assertIsNone(event.end_at)
        self.assertEqual(event.venue, '')
        self.assertEqual(event.location, 'Kochi, Kerala')
        self.assertEqual(event.capacity, 100)

    def test_edit_event(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('edit_event', args=[self.event.pk]), {
            'title': 'Updated Wedding',
            'description': 'An updated package.',
            'price': '200000',
            'location': 'Kochi, Kerala',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.assertRedirects(response, reverse('my_events'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Updated Wedding')
        self.assertEqual(self.event.price, 200000)

    def test_cannot_edit_someone_elses_event(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        other_event = self.make_event(other_org, title='Other Event')
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('edit_event', args=[other_event.pk]), {
            'title': 'Hacked',
            'description': 'x',
            'price': '1',
            'location': 'X',
        })
        self.assertEqual(response.status_code, 404)
        other_event.refresh_from_db()
        self.assertEqual(other_event.title, 'Other Event')

    def test_delete_event_ownership_scoped(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse('delete_event', args=[self.event.pk]))
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())

    def test_manage_bookings_renders(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('manage_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_update_booking_status(self):
        self.client.force_login(self.organizer)
        self.client.post(
            reverse('update_booking_status', args=[self.booking.pk]),
            {'status': 'confirmed'})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')

    def test_update_booking_status_rejects_unknown(self):
        self.client.force_login(self.organizer)
        self.client.post(
            reverse('update_booking_status', args=[self.booking.pk]),
            {'status': 'nonsense'})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')

    def test_delete_booking(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse('delete_booking', args=[self.booking.pk]))
        self.assertFalse(EventBooking.objects.filter(pk=self.booking.pk).exists())

    def test_cannot_update_someone_elses_booking(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        other_event = self.make_event(other_org, title='Other Event')
        other_booking = self.make_booking(self.attendee, other_event)
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse('update_booking_status', args=[other_booking.pk]),
            {'status': 'confirmed'})
        self.assertEqual(response.status_code, 404)
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, 'pending')

    def test_cannot_delete_someone_elses_booking(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        other_event = self.make_event(other_org, title='Other Event')
        other_booking = self.make_booking(self.attendee, other_event)
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('delete_booking', args=[other_booking.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(EventBooking.objects.filter(pk=other_booking.pk).exists())

    def test_admin_can_update_any_booking(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        other_event = self.make_event(other_org, title='Other Event')
        other_booking = self.make_booking(self.attendee, other_event)
        admin = User.objects.create_superuser(
            username='admin2', email='admin2@example.com', password='testpass123')
        self.client.force_login(admin)
        response = self.client.post(
            reverse('update_booking_status', args=[other_booking.pk]),
            {'status': 'confirmed'})
        self.assertRedirects(response, reverse('manage_bookings'))
        other_booking.refresh_from_db()
        self.assertEqual(other_booking.status, 'confirmed')

    def test_manage_feedback_renders(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('manage_feedback'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amazing service!')

    def test_delete_feedback(self):
        self.client.force_login(self.organizer)
        self.client.post(reverse('delete_feedback', args=[self.feedback.pk]))
        self.assertFalse(Feedback.objects.filter(pk=self.feedback.pk).exists())


# ---------------------------------------------------------------------------
# Admin lifecycle management
# ---------------------------------------------------------------------------

class AdminManagementTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.target = self.make_user(username='target')
        self.event = self.make_event(self.organizer, status='under_review')
        self.make_booking(self.target, self.event)

    def test_admin_dashboard_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_organizer_blocked_from_admin_dashboard(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_manage_users_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_users'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'target')

    def test_toggle_user_active(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('toggle_user_active', args=[self.target.pk]))
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.client.post(reverse('toggle_user_active', args=[self.target.pk]))
        self.target.refresh_from_db()
        self.assertTrue(self.target.is_active)

    def test_cannot_deactivate_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('toggle_user_active', args=[self.admin.pk]))
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_delete_user(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('delete_user', args=[self.target.pk]))
        self.assertFalse(User.objects.filter(pk=self.target.pk).exists())

    def test_cannot_delete_self(self):
        self.client.force_login(self.admin)
        self.client.post(reverse('delete_user', args=[self.admin.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_approval_queue_renders(self):
        """Queue renders but no longer lists individual packages — orgs only."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.event.title)

    def test_approve_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('approve_event', args=[self.event.pk]), {'notes': 'Looks good'})
        self.assertRedirects(response, reverse('approval_queue'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'approved')

    def test_reject_event_requires_reason(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('reject_event', args=[self.event.pk]))
        self.assertRedirects(response, reverse('approval_queue'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'under_review')

    def test_reject_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('reject_event', args=[self.event.pk]), {'reason': 'Too small'})
        self.assertRedirects(response, reverse('approval_queue'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'rejected')

    def test_publish_and_go_live(self):
        self.event.status = 'approved'
        self.event.save(update_fields=['status'])
        self.client.force_login(self.admin)
        self.client.post(reverse('publish_event', args=[self.event.pk]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'published')
        self.client.post(reverse('go_live_event', args=[self.event.pk]))
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'live')


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------

class ErrorPageTests(PlannixTestCase):
    def test_404_handler_renders(self):
        response = self.client.get('/definitely-not-a-real-page')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, '404', status_code=404)

    def test_403_handler_renders(self):
        from events.views import error_403
        from django.test import RequestFactory
        response = error_403(RequestFactory().get('/'), None)
        self.assertEqual(response.status_code, 403)

    def test_500_handler_renders(self):
        from events.views import error_500
        from django.test import RequestFactory
        response = error_500(RequestFactory().get('/'))
        self.assertEqual(response.status_code, 500)


# ---------------------------------------------------------------------------
# Event lifecycle state machine (service-level)
# ---------------------------------------------------------------------------

class LifecycleServiceTests(PlannixTestCase):
    """Drive the event lifecycle transitions through services directly and
    assert each transition writes a matching EventAuditLog row."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')

    def make_submittable(self, **overrides):
        category, _ = EventCategory.objects.get_or_create(name='Wedding')
        data = {
            'title': 'Wedding Package',
            'description': 'A complete wedding planning package.',
            'category': category,
            'start_at': timezone.now() + timedelta(days=10),
            'end_at': timezone.now() + timedelta(days=11),
            'location': 'Kochi, Kerala',
            'capacity': 50,
        }
        data.update(overrides)
        data.setdefault('status', 'draft')
        return self.make_event(self.organizer, **data)

    def last_log(self, event):
        return EventAuditLog.objects.filter(event=event).order_by('-id').first()

    # ---- submit ----

    def test_submit_draft_to_under_review(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        event.refresh_from_db()
        self.assertEqual(event.status, 'under_review')
        self.assertIsNotNone(event.submitted_at)
        log = self.last_log(event)
        self.assertEqual(log.action, 'submit')
        self.assertEqual(log.from_status, 'draft')
        self.assertEqual(log.to_status, 'under_review')

    def test_submit_requires_complete_data(self):
        event = self.make_submittable()
        event.title = ''
        event.save(update_fields=['title'])
        with self.assertRaises(ValueError):
            submit(event, self.organizer)
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')

    def test_submit_requires_category(self):
        event = self.make_submittable(category=None)
        with self.assertRaises(ValueError):
            submit(event, self.organizer)
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')

    def test_submit_without_dates_succeeds(self):
        """Packages carry no start/end dates — submit works without them."""
        event = self.make_submittable(start_at=None, end_at=None)
        submit(event, self.organizer)
        event.refresh_from_db()
        self.assertEqual(event.status, 'under_review')

    # ---- approve ----

    def test_approve_sets_approved_at(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin, notes='Looks good')
        event.refresh_from_db()
        self.assertEqual(event.status, 'approved')
        self.assertIsNotNone(event.approved_at)
        self.assertEqual(event.review_notes, 'Looks good')
        log = self.last_log(event)
        self.assertEqual(log.action, 'approve')
        self.assertEqual(log.from_status, 'under_review')
        self.assertEqual(log.to_status, 'approved')

    # ---- reject ----

    def test_reject_requires_reason(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        with self.assertRaises(ValueError):
            reject(event, self.admin, reason='')
        event.refresh_from_db()
        self.assertEqual(event.status, 'under_review')

    def test_reject_sets_rejection_reason(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        reject(event, self.admin, reason='Too small')
        event.refresh_from_db()
        self.assertEqual(event.status, 'rejected')
        self.assertEqual(event.rejection_reason, 'Too small')
        log = self.last_log(event)
        self.assertEqual(log.action, 'reject')
        self.assertEqual(log.from_status, 'under_review')
        self.assertEqual(log.to_status, 'rejected')

    # ---- resubmit ----

    def test_resubmit_clears_rejection_reason(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        reject(event, self.admin, reason='Too small')
        resubmit(event, self.organizer)
        event.refresh_from_db()
        self.assertEqual(event.status, 'under_review')
        self.assertEqual(event.rejection_reason, '')
        log = self.last_log(event)
        self.assertEqual(log.action, 'resubmit')
        self.assertEqual(log.from_status, 'rejected')
        self.assertEqual(log.to_status, 'under_review')

    # ---- publish / go_live ----

    def test_publish_sets_publish_at(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        event.refresh_from_db()
        self.assertEqual(event.status, 'published')
        self.assertIsNotNone(event.publish_at)
        log = self.last_log(event)
        self.assertEqual(log.action, 'publish')
        self.assertEqual(log.from_status, 'approved')
        self.assertEqual(log.to_status, 'published')

    def test_go_live(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        go_live(event, self.admin)
        event.refresh_from_db()
        self.assertEqual(event.status, 'live')
        log = self.last_log(event)
        self.assertEqual(log.action, 'go_live')
        self.assertEqual(log.from_status, 'published')
        self.assertEqual(log.to_status, 'live')

    # ---- complete ----

    def test_complete_finalizes_bookings(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        go_live(event, self.admin)
        attendee = self.make_user(username='attendee1')
        confirmed = self.make_booking(attendee, event, status='confirmed')
        pending = self.make_booking(attendee, event, status='pending')
        already_cancelled = self.make_booking(attendee, event, status='cancelled')

        complete(event)
        event.refresh_from_db()
        self.assertEqual(event.status, 'completed')
        confirmed.refresh_from_db()
        pending.refresh_from_db()
        already_cancelled.refresh_from_db()
        self.assertEqual(confirmed.status, 'completed')
        self.assertEqual(pending.status, 'cancelled')
        self.assertEqual(already_cancelled.status, 'cancelled')
        log = self.last_log(event)
        self.assertEqual(log.action, 'complete')
        self.assertEqual(log.from_status, 'live')
        self.assertEqual(log.to_status, 'completed')

    # ---- cancel ----

    def test_cancel_auto_cancels_bookings(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        go_live(event, self.admin)
        attendee = self.make_user(username='attendee1')
        confirmed = self.make_booking(attendee, event, status='confirmed')
        pending = self.make_booking(attendee, event, status='pending')

        cancel(event, self.admin, reason='Venue issue')
        event.refresh_from_db()
        self.assertEqual(event.status, 'cancelled')
        confirmed.refresh_from_db()
        pending.refresh_from_db()
        self.assertEqual(confirmed.status, 'cancelled')
        self.assertEqual(pending.status, 'cancelled')
        log = self.last_log(event)
        self.assertEqual(log.action, 'cancel')
        self.assertEqual(log.from_status, 'live')
        self.assertEqual(log.to_status, 'cancelled')

    # ---- edit_sets_draft ----

    def test_edit_sets_draft_from_approved_preserves_confirmed_booking(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        attendee = self.make_user(username='attendee1')
        confirmed = self.make_booking(attendee, event, status='confirmed')

        result = edit_sets_draft(event)
        self.assertTrue(result)
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')
        self.assertIsNone(event.approved_at)
        confirmed.refresh_from_db()
        self.assertEqual(confirmed.status, 'confirmed')

    def test_edit_sets_draft_from_published_and_live(self):
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        self.assertTrue(edit_sets_draft(event))
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')

        event2 = self.make_submittable()
        submit(event2, self.organizer)
        approve(event2, self.admin)
        publish(event2, self.admin)
        go_live(event2, self.admin)
        self.assertTrue(edit_sets_draft(event2))
        event2.refresh_from_db()
        self.assertEqual(event2.status, 'draft')

    # ---- forbidden transitions ----

    def test_submit_on_live_is_forbidden(self):
        event = self.make_submittable(status='live')
        with self.assertRaises(ValueError):
            submit(event, self.organizer)

    def test_approve_on_draft_is_forbidden(self):
        event = self.make_submittable()
        with self.assertRaises(ValueError):
            approve(event, self.admin)

    def test_complete_on_draft_is_forbidden(self):
        event = self.make_submittable()
        with self.assertRaises(ValueError):
            complete(event)

    def test_cancel_on_completed_is_forbidden(self):
        event = self.make_submittable(status='completed')
        with self.assertRaises(ValueError):
            cancel(event, self.admin)

    def test_each_transition_writes_audit_log(self):
        # A full happy-path run should produce exactly one log row per step.
        event = self.make_submittable()
        submit(event, self.organizer)
        approve(event, self.admin)
        publish(event, self.admin)
        go_live(event, self.admin)
        logs = list(EventAuditLog.objects.filter(event=event).order_by('id'))
        self.assertEqual(len(logs), 4)
        self.assertEqual([l.action for l in logs],
                         ['submit', 'approve', 'publish', 'go_live'])


# ---------------------------------------------------------------------------
# Security & access control
# ---------------------------------------------------------------------------

class SecurityTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.attacker = self.make_user(username='attacker', group='EventOrganizer')
        self.victim = self.make_user(username='victim', group='EventOrganizer')
        self.attendee = self.make_user(username='attendee1')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.event = self.make_event(self.victim)  # owned by the victim
        self.under_review = self.make_event(self.victim, status='under_review')
        self.approved = self.make_event(self.victim, status='approved')
        self.published = self.make_event(self.victim, status='published')

    # ---- IDOR: organizer A vs organizer B's event ----

    def test_idor_edit_event_404(self):
        self.client.force_login(self.attacker)
        response = self.client.get(reverse('edit_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)

    def test_idor_submit_event_404(self):
        self.client.force_login(self.attacker)
        response = self.client.get(reverse('submit_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)

    def test_idor_event_registrations_404(self):
        self.client.force_login(self.attacker)
        response = self.client.get(reverse('event_registrations', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)

    def test_idor_event_pulse_view_404(self):
        self.client.force_login(self.attacker)
        response = self.client.get(reverse('event_pulse_view', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)

    def test_idor_cancel_event_404(self):
        self.client.force_login(self.attacker)
        response = self.client.post(reverse('cancel_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)

    def test_idor_delete_event_404(self):
        self.client.force_login(self.attacker)
        response = self.client.post(reverse('delete_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(pk=self.event.pk).exists())

    # ---- role escalation ----

    def test_attendee_blocked_from_organizer_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_attendee_blocked_from_admin_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_organizer_blocked_from_admin_dashboard(self):
        self.client.force_login(self.attacker)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    # ---- admin-only ops are not reachable by non-admins ----

    def test_admin_only_ops_redirect_for_organizer(self):
        self.client.force_login(self.attacker)
        urls = [
            reverse('approve_event', args=[self.under_review.pk]),
            reverse('reject_event', args=[self.under_review.pk]),
            reverse('publish_event', args=[self.approved.pk]),
            reverse('go_live_event', args=[self.published.pk]),
            reverse('approval_queue'),
            reverse('manage_users'),
            reverse('manage_organizers'),
            reverse('manage_categories'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertRedirects(response, reverse('dashboard'),
                                 fetch_redirect_response=False, msg_prefix=url)

    def test_admin_only_ops_redirect_for_attendee(self):
        self.client.force_login(self.attendee)
        urls = [
            reverse('approve_event', args=[self.under_review.pk]),
            reverse('approval_queue'),
            reverse('manage_users'),
            reverse('manage_organizers'),
            reverse('manage_categories'),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertRedirects(response, reverse('dashboard'),
                                 fetch_redirect_response=False, msg_prefix=url)

    # ---- unauthorized POST: attendee cannot approve ----

    def test_attendee_cannot_approve_event_via_post(self):
        self.client.force_login(self.attendee)
        response = self.client.post(
            reverse('approve_event', args=[self.under_review.pk]), {'notes': 'hax'})
        self.assertEqual(response.status_code, 302)
        self.under_review.refresh_from_db()
        self.assertEqual(self.under_review.status, 'under_review')

    # ---- CSRF ----

    def test_post_without_csrf_token_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True, SERVER_NAME='localhost')
        csrf_client.force_login(self.attendee)
        response = csrf_client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test',
            'email': 'test@example.com',
            'number': '9876543210',
            'date': (date.today() + timedelta(days=7)).isoformat(),
        })
        self.assertEqual(response.status_code, 403)

    # ---- anonymous access ----

    def test_anonymous_redirected_to_sign_in_for_protected_views(self):
        for name in ('my_bookings', 'organizer_dashboard', 'attendee_dashboard'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('sign_in'), response.url)


# ---------------------------------------------------------------------------
# Data integrity: slugs, event_date, Review constraints & pulse
# ---------------------------------------------------------------------------

class DataIntegrityTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.attendee = self.make_user(username='attendee1')

    def test_event_slug_auto_generation_is_unique(self):
        e1 = self.make_event(self.owner, title='Same Title')
        e2 = self.make_event(self.owner, title='Same Title')
        self.assertEqual(e1.slug, 'same-title')
        self.assertEqual(e2.slug, 'same-title-1')
        self.assertNotEqual(e1.slug, e2.slug)

    def test_event_category_slug_auto_generation(self):
        cat = self.make_category('Birthday Bash')
        self.assertEqual(cat.slug, 'birthday-bash')

    def test_booking_event_date_persists(self):
        event = self.make_event(self.owner)
        booking = self.make_booking(
            self.attendee, event, event_date=date(2030, 1, 15))
        booking.refresh_from_db()
        self.assertEqual(booking.event_date, date(2030, 1, 15))

    def test_review_valid_rating(self):
        event = self.make_event(self.owner)
        booking = self.make_booking(self.attendee, event)
        review = Review.objects.create(
            event=event, attendee=self.attendee, booking=booking, rating=4)
        review.full_clean()  # should not raise for a valid 1-5 rating
        self.assertEqual(review.rating, 4)

    def test_review_rating_out_of_range_raises(self):
        event = self.make_event(self.owner)
        review = Review(event=event, attendee=self.attendee, rating=6)
        with self.assertRaises(ValidationError):
            review.full_clean()

    def test_review_rating_zero_raises(self):
        event = self.make_event(self.owner)
        review = Review(event=event, attendee=self.attendee, rating=0)
        with self.assertRaises(ValidationError):
            review.full_clean()

    def test_review_booking_one_to_one_uniqueness(self):
        event = self.make_event(self.owner)
        booking = self.make_booking(self.attendee, event)
        Review.objects.create(
            event=event, attendee=self.attendee, booking=booking, rating=5)
        with self.assertRaises(IntegrityError):
            Review.objects.create(
                event=event, attendee=self.attendee, booking=booking, rating=3)

    def test_pulse_average_rating_approved_only(self):
        event = self.make_event(self.owner)
        other = self.make_user(username='attendee2')
        Review.objects.create(
            event=event, attendee=self.attendee, rating=2,
            moderation_status='approved')
        Review.objects.create(
            event=event, attendee=other, rating=4,
            moderation_status='approved')
        # A pending review must NOT affect the average.
        Review.objects.create(
            event=event, attendee=self.attendee, rating=5,
            moderation_status='pending')
        self.assertEqual(average_rating(event), 3.0)


# ---------------------------------------------------------------------------
# Organization gate: submit_event + create_event
# ---------------------------------------------------------------------------

class OrganizationGateTests(PlannixTestCase):
    """Single-gate flow: Organization approval is the only admin gate; approved
    org packages auto-become live and package creation is blocked without it."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        category, _ = EventCategory.objects.get_or_create(name='Wedding')
        self.category = category

    def _make_draft_event(self):
        return self.make_event(
            self.organizer, category=self.category, status='draft',
            title='Draft Package',
            start_at=timezone.now() + timedelta(days=10),
            end_at=timezone.now() + timedelta(days=11),
        )

    def test_submit_event_without_org_blocked(self):
        """Organizer without an approved org gets redirected, event stays draft."""
        event = self._make_draft_event()
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('submit_event', args=[event.pk]))
        self.assertRedirects(response, reverse('my_organization'))
        event.refresh_from_db()
        self.assertEqual(event.status, 'draft')

    def test_submit_event_with_approved_org_publishes_live(self):
        """Organizer with an approved org publishing a draft package goes live
        immediately — no second admin approval."""
        org = self.make_org(self.organizer)
        event = self._make_draft_event()
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('submit_event', args=[event.pk]))
        self.assertRedirects(response, reverse('my_events'))
        event.refresh_from_db()
        self.assertEqual(event.status, 'live')
        self.assertEqual(event.organization, org)

    def test_create_event_auto_links_approved_org_and_lives(self):
        """Event created while org is approved is linked and created live."""
        org = self.make_org(self.organizer)
        self.client.force_login(self.organizer)
        self.client.post(reverse('add_event'), {
            'title': 'New Package',
            'description': 'A fun package.',
            'price': '50000',
            'location': 'Kochi, Kerala',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        event = Event.objects.get(title='New Package')
        self.assertEqual(event.organization, org)
        self.assertEqual(event.status, 'live')

    def test_create_event_without_org_blocked(self):
        """Organizer without an approved org cannot create a package."""
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('add_event'), {
            'title': 'No Org Package',
            'description': 'Plain package.',
            'price': '30000',
            'location': 'Kochi, Kerala',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.assertRedirects(response, reverse('my_organization'))
        self.assertFalse(
            Event.objects.filter(title='No Org Package').exists())

    def test_org_approval_auto_publishes_pending_packages(self):
        """Approving an org flips its linked draft/under_review packages live."""
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        pending = self.make_event(
            self.organizer, category=self.category, status='under_review',
            organization=org, title='Pending Package')
        draft = self.make_event(
            self.organizer, category=self.category, status='draft',
            organization=org, title='Draft Package')
        submit_org(org)
        approve_org(org, self.make_user(username='admin1'))
        org.refresh_from_db()
        self.assertEqual(org.status, 'approved')
        pending.refresh_from_db()
        self.assertEqual(pending.status, 'live')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'live')


# ---------------------------------------------------------------------------
# Approval queue: org + event rendering
# ---------------------------------------------------------------------------

class ApprovalQueueOrgTests(PlannixTestCase):
    """The approval queue reviews Organizations only — packages are never
    listed because org approval is the single marketplace gate."""
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.organizer, status='under_review',
                                     title='Pending Package')

    def _make_pending_org(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        submit_org(org)
        return org

    def test_approval_queue_does_not_list_packages(self):
        """A pending package is invisible in the queue — orgs only."""
        self.client.force_login(self.admin)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Pending Package')

    def test_approval_queue_renders_pending_org(self):
        self._make_pending_org()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Events Co.')

    def test_approval_queue_total_pending_count(self):
        """Pending count covers orgs only — packages no longer count."""
        self._make_pending_org()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('approval_queue'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_pending'], 1)  # orgs only


# ---------------------------------------------------------------------------
# Admin dashboard: pending-organizations count
# ---------------------------------------------------------------------------

class AdminDashboardOrgCountTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.organizer = self.make_user(username='org1', group='EventOrganizer')

    def _make_pending_org(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        submit_org(org)
        return org

    def test_admin_dashboard_shows_pending_orgs(self):
        self._make_pending_org()
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pending_organization_count'], 1)

    def test_admin_dashboard_zero_pending_orgs(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pending_organization_count'], 0)


# ---------------------------------------------------------------------------
# Admin bypass: admin can manage any event regardless of owner
# ---------------------------------------------------------------------------

class AdminBypassTests(PlannixTestCase):
    """Admin can edit, view, and manage events they don't own."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.event = self.make_event(
            self.organizer, title='Org Event', status='draft')
        self.live_event = self.make_event(
            self.organizer, title='Live Event', status='live')

    def test_admin_can_edit_any_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('edit_event', args=[self.event.pk]), {
            'title': 'Admin Updated',
            'description': 'Updated by admin.',
            'price': '100000',
            'location': 'Kochi',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.assertRedirects(response, reverse('manage_events'))
        self.event.refresh_from_db()
        self.assertEqual(self.event.title, 'Admin Updated')

    def test_admin_edit_resets_approved_to_draft(self):
        self.event.status = 'approved'
        self.event.save(update_fields=['status'])
        self.client.force_login(self.admin)
        self.client.post(reverse('edit_event', args=[self.event.pk]), {
            'title': 'Admin Updated',
            'description': 'Updated.',
            'price': '100000',
            'location': 'Kochi',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, 'draft')

    def test_admin_manage_events_shows_all_events(self):
        other_org = self.make_user(username='org2', group='EventOrganizer')
        self.make_event(other_org, title='Other Org Event')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Org Event')
        self.assertContains(response, 'Other Org Event')

    def test_admin_can_view_event_registrations(self):
        attendee = self.make_user(username='attendee1')
        self.make_booking(attendee, self.live_event)
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('event_registrations', args=[self.live_event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.live_event.title)

    def test_admin_can_view_event_approval_status(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('event_approval_status', args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.title)

    def test_admin_can_view_event_pulse(self):
        self.client.force_login(self.admin)
        response = self.client.get(
            reverse('event_pulse_view', args=[self.live_event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')

    def test_admin_can_cancel_any_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('cancel_event', args=[self.live_event.pk]),
            {'reason': 'Admin cancel'})
        self.assertRedirects(response, reverse('my_events'))
        self.live_event.refresh_from_db()
        self.assertEqual(self.live_event.status, 'cancelled')

    def test_admin_can_delete_any_event(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('delete_event', args=[self.event.pk]))
        self.assertFalse(Event.objects.filter(pk=self.event.pk).exists())


# ---------------------------------------------------------------------------
# Consolidated lifecycle: approve_and_go_live / publish_and_go_live
# ---------------------------------------------------------------------------

class ConsolidatedLifecycleTests(PlannixTestCase):
    """Test the one-click 'Approve & Go Live' and 'Take Live' actions."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.under_review = self.make_event(
            self.organizer, status='under_review', title='Pending Package')
        self.approved = self.make_event(
            self.organizer, status='approved', title='Approved Package')
        self.published = self.make_event(
            self.organizer, status='published', title='Published Package')

    # ---- approve_and_go_live (service) ----

    def test_approve_and_go_live_from_under_review(self):
        approve_and_go_live(self.under_review, self.admin, notes='Great')
        self.under_review.refresh_from_db()
        self.assertEqual(self.under_review.status, 'live')
        # Should have 3 audit log entries: approve, publish, go_live
        logs = EventAuditLog.objects.filter(
            event=self.under_review).order_by('id')
        actions = [log.action for log in logs]
        self.assertEqual(actions, ['approve', 'publish', 'go_live'])

    def test_approve_and_go_live_sets_timestamps(self):
        approve_and_go_live(self.under_review, self.admin)
        self.under_review.refresh_from_db()
        self.assertIsNotNone(self.under_review.approved_at)
        self.assertIsNotNone(self.under_review.publish_at)

    def test_approve_and_go_live_rejects_wrong_status(self):
        self.approved.status = 'live'
        self.approved.save(update_fields=['status'])
        with self.assertRaises(ValueError):
            approve_and_go_live(self.approved, self.admin)

    # ---- publish_and_go_live (service) ----

    def test_publish_and_go_live_from_approved(self):
        publish_and_go_live(self.approved, self.admin)
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, 'live')

    def test_publish_and_go_live_from_published(self):
        publish_and_go_live(self.published, self.admin)
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, 'live')

    def test_publish_and_go_live_from_approved_creates_two_logs(self):
        publish_and_go_live(self.approved, self.admin)
        logs = EventAuditLog.objects.filter(
            event=self.approved).order_by('id')
        actions = [log.action for log in logs]
        self.assertEqual(actions, ['publish', 'go_live'])

    def test_publish_and_go_live_rejects_draft(self):
        draft = self.make_event(self.organizer, status='draft')
        with self.assertRaises(ValueError):
            publish_and_go_live(draft, self.admin)

    # ---- View: approve_event_go_live ----

    def test_admin_approve_and_go_live_view(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('approve_event_go_live', args=[self.under_review.pk]),
            {'notes': 'Looks great'})
        self.assertRedirects(response, reverse('approval_queue'))
        self.under_review.refresh_from_db()
        self.assertEqual(self.under_review.status, 'live')

    def test_organizer_blocked_from_approve_and_go_live(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse('approve_event_go_live', args=[self.under_review.pk]))
        self.assertRedirects(response, reverse('dashboard'),
                             fetch_redirect_response=False)
        self.under_review.refresh_from_db()
        self.assertEqual(self.under_review.status, 'under_review')

    # ---- View: publish_event_go_live ----

    def test_admin_take_live_from_approved(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('publish_event_go_live', args=[self.approved.pk]))
        self.assertRedirects(response, reverse('manage_events'))
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, 'live')

    def test_admin_take_live_from_published(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('publish_event_go_live', args=[self.published.pk]))
        self.assertRedirects(response, reverse('manage_events'))
        self.published.refresh_from_db()
        self.assertEqual(self.published.status, 'live')

    def test_organizer_blocked_from_take_live(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse('publish_event_go_live', args=[self.approved.pk]))
        self.assertRedirects(response, reverse('dashboard'),
                             fetch_redirect_response=False)
        self.approved.refresh_from_db()
        self.assertEqual(self.approved.status, 'approved')


# ---------------------------------------------------------------------------
# Data audit management command
# ---------------------------------------------------------------------------

class AuditEventsDataCommandTest(PlannixTestCase):
    """Test the audit_events_data management command."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')

    def test_audit_report_only(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('audit_events_data', stdout=out)
        output = out.getvalue()
        self.assertIn('event data audit', output)
        self.assertIn('Total events:', output)

    def test_audit_json_output(self):
        from io import StringIO
        from django.core.management import call_command
        import json
        out = StringIO()
        call_command('audit_events_data', '--json', stdout=out)
        data = json.loads(out.getvalue())
        self.assertIn('total_events', data)
        self.assertIn('status_distribution', data)
        self.assertIn('events_without_organization', data)

    def test_audit_fix_links_events_to_approved_org(self):
        from io import StringIO
        from django.core.management import call_command
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
            status='approved',
        )
        event = self.make_event(self.organizer, status='draft', title='Audit Test')
        self.assertIsNone(event.organization)
        out = StringIO()
        call_command('audit_events_data', '--fix', stdout=out)
        event.refresh_from_db()
        self.assertEqual(event.organization, org)

    def test_audit_fix_does_not_link_unapproved_org(self):
        from io import StringIO
        from django.core.management import call_command
        Organization.objects.create(
            owner=self.organizer, name='Unapproved Org',
            description='Planning.', contact_number='9876543210',
            status='pending',
        )
        event = self.make_event(self.organizer, status='draft', title='No Fix')
        out = StringIO()
        call_command('audit_events_data', '--fix', stdout=out)
        event.refresh_from_db()
        self.assertIsNone(event.organization)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class TestEmailCommandTests(PlannixTestCase):
    """test_email sends a test message and never leaks credentials."""

    def test_sends_to_recipient(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('test_email', 'recipient@example.com', stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['recipient@example.com'])
        self.assertIn('Test email sent', out.getvalue())

    def test_output_never_contains_secrets(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('test_email', 'recipient@example.com', stdout=out)
        output = out.getvalue()
        self.assertNotIn(settings.EMAIL_HOST_PASSWORD, output)
        self.assertNotIn(settings.SECRET_KEY, output)


# ---------------------------------------------------------------------------
# Organization rejection clears submitted_at (resubmit flow)
# ---------------------------------------------------------------------------

class OrganizationRejectResubmitTests(PlannixTestCase):
    """After rejection, submitted_at is cleared so the org can resubmit."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')

    def test_reject_clears_submitted_at(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        submit_org(org)
        org.refresh_from_db()
        self.assertIsNotNone(org.submitted_at)
        reject_org_svc(org, self.admin, reason='Incomplete')
        org.refresh_from_db()
        self.assertIsNone(org.submitted_at)
        self.assertEqual(org.status, 'rejected')

    def test_rejected_org_can_resubmit(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        submit_org(org)
        reject_org_svc(org, self.admin, reason='Fix details')
        org.refresh_from_db()
        self.assertIsNone(org.submitted_at)
        # Resubmit should work (sets pending + submitted_at)
        resubmit_org_svc(org)
        org.refresh_from_db()
        self.assertEqual(org.status, 'pending')
        self.assertIsNotNone(org.submitted_at)

    def test_rejected_org_not_in_approval_queue(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Rejected Org',
            description='Planning.', contact_number='9876543210',
        )
        submit_org(org)
        reject_org_svc(org, self.admin, reason='Nope')
        # Approval queue only shows pending orgs with submitted_at
        self.client.force_login(self.admin)
        response = self.client.get(reverse('approval_queue'))
        self.assertNotContains(response, 'Rejected Org')


# ---------------------------------------------------------------------------
# Admin event visibility in manage_events (org NULL — all 22 events)
# ---------------------------------------------------------------------------

class AdminManageEventsVisibilityTests(PlannixTestCase):
    """Admin can see and manage all events in the manage_events view."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.org1 = self.make_user(username='org1', group='EventOrganizer')
        self.org2 = self.make_user(username='org2', group='EventOrganizer')

    def test_admin_sees_all_organizers_events(self):
        self.make_event(self.org1, title='Org1 Event')
        self.make_event(self.org2, title='Org2 Event')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_events'))
        self.assertContains(response, 'Org1 Event')
        self.assertContains(response, 'Org2 Event')

    def test_organizer_sees_own_events_only(self):
        self.make_event(self.org1, title='Org1 Event')
        self.make_event(self.org2, title='Org2 Event')
        self.client.force_login(self.org1)
        response = self.client.get(reverse('manage_events'))
        self.assertContains(response, 'Org1 Event')
        self.assertNotContains(response, 'Org2 Event')

    def test_admin_delete_any_event(self):
        event = self.make_event(self.org1, title='To Delete')
        self.client.force_login(self.admin)
        self.client.post(reverse('delete_event', args=[event.pk]))
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())

    def test_organizer_cannot_delete_other_orgs_event(self):
        event = self.make_event(self.org2, title='Not Mine')
        self.client.force_login(self.org1)
        response = self.client.post(reverse('delete_event', args=[event.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Event.objects.filter(pk=event.pk).exists())


# ---------------------------------------------------------------------------
# Identity: canonical display name + avatar initial (Points 1)
# ---------------------------------------------------------------------------

class IdentityTests(PlannixTestCase):
    """One canonical display-name helper drives every page and every role.

    The helpers prefer the full name and fall back to the username; the avatar
    initial is always derived from that exact name, so name and avatar never
    disagree across templates.
    """

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.organizer = self.make_user(
            username='org1', group='EventOrganizer',
            first_name='Riya', last_name='Menon')
        self.attendee = self.make_user(username='attendee1')
        self.event = self.make_event(self.organizer)

    # ---- helpers directly ----

    def test_display_name_prefers_full_name(self):
        from account_manager.identity import display_name
        self.assertEqual(display_name(self.organizer), 'Riya Menon')

    def test_display_name_falls_back_to_username(self):
        from account_manager.identity import display_name
        self.assertEqual(display_name(self.attendee), 'attendee1')

    def test_display_name_none_is_empty(self):
        from account_manager.identity import display_name
        self.assertEqual(display_name(None), '')
        self.assertEqual(display_name(User()), '')

    def test_avatar_initial_matches_display_name(self):
        from account_manager.identity import avatar_initial
        self.assertEqual(avatar_initial(self.organizer), 'R')   # full name
        self.assertEqual(avatar_initial(self.attendee), 'A')    # username fallback

    def test_avatar_initial_none(self):
        from account_manager.identity import avatar_initial
        self.assertEqual(avatar_initial(None), '')

    def test_avatar_initial_from_display_name_filter(self):
        """The template filter delegates to the same helper."""
        from account_manager.identity import display_name, avatar_initial
        for role_user in (self.admin, self.organizer, self.attendee):
            fmt_name = display_name(role_user)
            self.assertEqual(avatar_initial(role_user), fmt_name[:1].upper())

    # ---- rendering per role ----

    def test_public_navbar_header_cleanup(self):
        """Header cleanup: the public navbar shows a Sign Out form, no name dropdown."""
        self.client.force_login(self.organizer)
        html = self.client.get(reverse('index')).content.decode()
        self.assertIn(reverse('sign_out'), html)
        self.assertNotIn('dropdown-menu', html)
        self.assertNotIn('Riya Menon', html)

    def test_attendee_dashboard_shows_canonical_identity(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('attendee_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'attendee1')  # username fallback
        # Dashboards / public nav both carry an explicit Home link (Point 9).
        self.assertContains(response, '>Home<')

    def test_organizer_dashboard_shows_canonical_identity(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Riya Menon')
        self.assertContains(response, 'R')

    def test_admin_dashboard_shows_canonical_identity(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'admin1')
        self.assertContains(response, 'A')


# ---------------------------------------------------------------------------
# publish_live service (single-gate workflow — Point 3)
# ---------------------------------------------------------------------------

class PublishLiveServiceTests(PlannixTestCase):
    """A draft package goes live directly for an approved organization owner
    — no second admin approval. Unapproved owners are blocked."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.draft = self.make_event(self.organizer, status='draft')

    def test_publish_live_from_draft(self):
        from .services import publish_live
        self.make_org(self.organizer)
        # setUp's draft is unlinked from the org so it stays a draft; publish a
        # fresh draft with an approved org (the re-publish path after an edit).
        draft = self.make_event(self.organizer, status='draft', title='Fresh Draft')
        publish_live(draft, self.organizer)
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'live')
        self.assertIsNotNone(draft.publish_at)
        log = EventAuditLog.objects.filter(event=draft).order_by('-id').first()
        self.assertEqual(log.action, 'publish_live')
        self.assertEqual(log.from_status, 'draft')
        self.assertEqual(log.to_status, 'live')

    def test_publish_live_requires_approved_org(self):
        from .services import publish_live
        with self.assertRaises(ValueError):
            publish_live(self.draft, self.organizer)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'draft')

    def test_publish_live_rejects_non_draft(self):
        from .services import publish_live
        self.make_org(self.organizer)
        live = self.make_event(self.organizer, status='live', title='Already Live')
        with self.assertRaises(ValueError):
            publish_live(live, self.organizer)

    def test_auto_publish_org_packages_skips_terminal_states(self):
        from .services import auto_publish_org_packages
        org = self.make_org(self.organizer)
        # make_org's approval only published packages linked to the org; the
        # unlinked setUp draft stays a draft, so it is never touched.
        fresh_draft = self.make_event(
            self.organizer, status='under_review', organization=org,
            title='Pending Draft')
        completed = self.make_event(
            self.organizer, status='completed', organization=org,
            title='Completed One')
        changed = auto_publish_org_packages(org, self.organizer)
        changed_titles = [e.title for e in changed]
        fresh_draft.refresh_from_db()
        self.assertEqual(fresh_draft.status, 'live')
        self.assertIn('Pending Draft', changed_titles)
        self.assertNotIn('Completed One', changed_titles)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status, 'draft')  # unlinked — untouched


# ---------------------------------------------------------------------------
# Public discovery of approved-org packages (Point 6)
# ---------------------------------------------------------------------------

class ApprovedOrgDiscoveryTests(PlannixTestCase):
    """A package created by an approved organization goes live immediately and
    is listed on the public Discover page with its fields resolved."""

    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1', group='EventOrganizer')
        self.org = self.make_org(self.organizer)
        self.category = self.make_category('Wedding')

    def test_approved_org_live_package_on_discover(self):
        event = self.make_event(
            self.organizer,
            category=self.category,
            organization=self.org,
            status='live',
            title='Apex Live Package',
            location='Kochi, Kerala',
            price=250000,
        )
        response = self.client.get(reverse('events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Apex Live Package')

    def test_approved_org_create_event_appears_on_discover_view(self):
        """End-to-end: approved organizer creates a package via the view and it
        is immediately visible and bookable on the public catalogue."""
        self.client.force_login(self.organizer)
        self.client.post(reverse('add_event'), {
            'title': 'Vista Weddings',
            'description': 'Premium wedding planning.',
            'price': '300000',
            'location': 'Bangalore',
            'contact_number': '9876543210',
            'featured_image': make_image_file(),
        })
        response = self.client.get(reverse('events'))
        self.assertContains(response, 'Vista Weddings')
        event = Event.objects.get(title='Vista Weddings')
        self.assertEqual(event.status, 'live')
        self.assertEqual(event.organization, self.org)


# ---------------------------------------------------------------------------
# Booking confirmation + organizer notification emails (Part D)
# ---------------------------------------------------------------------------

@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class BookingEmailTests(PlannixTestCase):
    """Booking creation routes through the Plannix email service and sends the
    customer a confirmation and the organizer a notification with permitted
    contact details only."""

    def setUp(self):
        super().setUp()
        self.user = self.make_user(username='attendee1')
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.owner, price=150000)

    def _book(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test Attendee',
            'email': self.user.email,
            'number': '9876543210',
            'event_location': self.event.location,
            'date': (date.today() + timedelta(days=7)).isoformat(),
        })
        booking = EventBooking.objects.get(attendee=self.user)
        self.assertRedirects(
            response, f"{reverse('success')}?booking={booking.pk}")
        return booking

    def test_booking_creation_sends_customer_and_organizer_emails(self):
        booking = self._book()
        self.assertEqual(len(mail.outbox), 2)
        customer, organizer = mail.outbox
        self.assertEqual(customer.to, [self.user.email])
        self.assertEqual(organizer.to, [self.owner.email])

    def test_customer_confirmation_content(self):
        booking = self._book()
        body = mail.outbox[0].body
        self.assertIn('Booking Confirmation', mail.outbox[0].subject)
        self.assertIn(booking.booking_reference, body)
        self.assertIn(self.event.title, body)
        self.assertIn(self.event.location, body)
        # Emails render the requested date (localized); assert the year present.
        self.assertIn(str(booking.event_date.year), body)
        self.assertIn('Pending', body)
        self.assertIn(str(booking.price), body)
        # No advance payment in the confirmation email.
        self.assertNotIn('Advance', body)
        self.assertNotIn('45000', body)

    def test_customer_confirmation_contains_organizer_contact(self):
        """Confirmation email points the customer to the organizer directly."""
        self._book()
        body = mail.outbox[0].body
        self.assertIn(
            'For payment details, please contact the event organizer directly.',
            body)
        self.assertIn(self.owner.email, body)     # organizer registered email
        self.assertIn(self.event.contact_number, body)  # organizer phone

    def test_organizer_notification_content(self):
        booking = self._book()
        body = mail.outbox[1].body
        self.assertIn('New Booking Request', mail.outbox[1].subject)
        self.assertIn('Test Attendee', body)
        self.assertIn(self.user.email, body)
        self.assertIn('9876543210', body)
        self.assertIn(booking.booking_reference, body)
        self.assertIn(self.event.title, body)

    def test_organizer_notification_has_no_owner_email_when_missing(self):
        # Owner without an email -> no notification email is attempted.
        self.owner.email = ''
        self.owner.save(update_fields=['email'])
        booking = self._book()
        self.assertEqual(len(mail.outbox), 1)  # only the customer confirmation

    def test_booking_status_change_email_sent(self):
        booking = self._book()
        mail.outbox.clear()
        self.client.force_login(self.owner)
        self.client.post(reverse('update_booking_status', args=[booking.pk]),
                         {'status': 'confirmed'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Confirmed', mail.outbox[0].subject)
        self.assertIn(booking.booking_reference, mail.outbox[0].body)


# ---------------------------------------------------------------------------
# Advance payment (Part E) — server-side amount, eligibility, signatures
# ---------------------------------------------------------------------------

def _payment_signature(order_id, payment_id, secret):
    import hashlib
    import hmac
    return hmac.new(secret.encode(), f'{order_id}|{payment_id}'.encode(),
                    hashlib.sha256).hexdigest()


class FakeRazorpayOrder:
    def __init__(self, calls):
        self.calls = calls

    def create(self, data):
        self.calls.append(data)
        return {'id': 'order_rzp_1234567890', 'amount': data['amount'],
                'currency': data['currency']}


class FakeRazorpayClient:
    def __init__(self):
        self.order_calls = []
        # The real razorpay client exposes ``order`` as an attribute holding a
        # sub-client with a ``create`` method, so mirror that shape.
        self.order = FakeRazorpayOrder(self.order_calls)


@override_settings(
    RAZORPAY_KEY_ID='rzp_test_public_key',
    RAZORPAY_KEY_SECRET='test_secret',
    PAYMENT_ADVANCE_PERCENT=30,
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AdvancePaymentTests(PlannixTestCase):
    """The advance is always the server-calculated 30% of the confirmed price,
    ownership is enforced, and payment is only marked paid after a correct
    HMAC signature."""

    def setUp(self):
        super().setUp()
        self.user = self.make_user(username='attendee1')
        self.other = self.make_user(username='other')
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.owner, price=150000)
        self.booking = self.make_booking(self.user, self.event, status='confirmed')
        self.fake_client = FakeRazorpayClient()
        patcher = patch('events.payments.get_razorpay_client',
                        return_value=self.fake_client)
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_advance_is_thirty_percent_of_price(self):
        self.assertEqual(advance_amount(self.booking), 45000)
        self.assertEqual(remaining_amount(self.booking), 105000)

    def test_advance_ignores_browser_submitted_amount(self):
        # The view never accepts an amount; create_order computes it server-side.
        _, payload = create_order(self.booking, self.user)
        self.assertEqual(payload['amount'], 45000 * 100)  # paise
        self.assertEqual(self.fake_client.order_calls[-1]['amount'], 45000 * 100)

    def test_create_order_requires_confirmed_status(self):
        self.booking.status = 'pending'
        self.booking.save(update_fields=['status'])
        with self.assertRaises(PaymentError):
            create_order(self.booking, self.user)

    def test_create_order_requires_ownership(self):
        with self.assertRaises(PaymentError):
            create_order(self.booking, self.other)

    def test_initiate_view_scopes_to_owner(self):
        # A different attendee cannot initiate payment on this booking.
        self.client.force_login(self.other)
        response = self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(BookingPayment.objects.exists())

    def test_initiate_view_creates_order(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['order_id'], 'order_rzp_1234567890')
        self.assertEqual(data['key_id'], 'rzp_test_public_key')
        self.assertEqual(data['amount'], 45000 * 100)
        # Never leak the secret.
        self.assertNotIn('test_secret', response.content.decode())

    def test_initiate_requires_login(self):
        response = self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('sign_in'), response.url)

    def test_verify_payment_signature_valid(self):
        sig = _payment_signature('order_1', 'pay_1', 'test_secret')
        self.assertTrue(verify_payment_signature('order_1', 'pay_1', sig))

    def test_verify_payment_signature_tampered_fails(self):
        sig = _payment_signature('order_1', 'pay_1', 'test_secret')
        self.assertFalse(verify_payment_signature('order_1', 'pay_1',
                                                  sig[:-2] + '00'))
        self.assertFalse(verify_payment_signature('order_1', 'pay_2', sig))

    def test_verify_view_marks_paid_only_with_valid_signature(self):
        self.client.force_login(self.user)
        self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        payment = BookingPayment.objects.get(booking=self.booking)
        sig = _payment_signature(payment.razorpay_order_id, 'pay_1', 'test_secret')
        self.client.post(reverse('verify_advance'), {
            'razorpay_order_id': payment.razorpay_order_id,
            'razorpay_payment_id': 'pay_1',
            'razorpay_signature': sig,
        })
        payment.refresh_from_db()
        self.assertEqual(payment.status, BookingPayment.STATUS_PAID)
        self.assertIsNotNone(payment.paid_at)
        # Confirmation email sent.
        self.assertGreaterEqual(len(mail.outbox), 1)

    def test_verify_view_fails_on_bad_signature(self):
        self.client.force_login(self.user)
        self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        payment = BookingPayment.objects.get(booking=self.booking)
        self.client.post(reverse('verify_advance'), {
            'razorpay_order_id': payment.razorpay_order_id,
            'razorpay_payment_id': 'pay_1',
            'razorpay_signature': 'badsig',
        })
        payment.refresh_from_db()
        self.assertEqual(payment.status, BookingPayment.STATUS_FAILED)
        self.assertNotEqual(payment.status, BookingPayment.STATUS_PAID)

    def test_paid_advance_cannot_be_paid_again(self):
        self.client.force_login(self.user)
        self.client.post(reverse('initiate_advance', args=[self.booking.pk]))
        payment = BookingPayment.objects.get(booking=self.booking)
        payment.status = BookingPayment.STATUS_PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=['status', 'paid_at'])
        with self.assertRaises(PaymentError):
            create_order(self.booking, self.user)

    def test_cancelled_booking_cannot_be_paid(self):
        self.booking.status = 'cancelled'
        self.booking.save(update_fields=['status'])
        with self.assertRaises(PaymentError):
            create_order(self.booking, self.user)


@override_settings(RAZORPAY_KEY_SECRET='webhook_secret', PAYMENT_ADVANCE_PERCENT=30)
class PaymentWebhookTests(PlannixTestCase):
    """Signature-verified, idempotent webhook handling."""

    def _setup(self):
        user = self.make_user(username='attendee1')
        owner = self.make_user(username='org1', group='EventOrganizer')
        event = self.make_event(owner, price=100000)
        booking = self.make_booking(user, event, status='confirmed')
        payment = BookingPayment.objects.create(
            booking=booking, amount=advance_amount(booking),
            razorpay_order_id='order_wh_1')
        return booking, payment

    def _webhook_body(self, order_id, event='payment.captured'):
        import json
        return json.dumps({
            'event': event,
            'payload': {'payment': {'entity': {
                'id': 'pay_wh_1', 'order_id': order_id,
                'error_description': 'failed'}}},
        }).encode()

    def _sign(self, body):
        import base64
        import hashlib
        import hmac
        return base64.b64encode(hmac.new(
            b'webhook_secret', body, hashlib.sha256).digest()).decode()

    def test_webhook_marks_paid_and_is_idempotent(self):
        booking, payment = self._setup()
        body = self._webhook_body(payment.razorpay_order_id)
        sig = self._sign(body)
        handled1, p1 = handle_webhook(body, sig)
        payment.refresh_from_db()
        self.assertTrue(handled1)
        self.assertEqual(payment.status, BookingPayment.STATUS_PAID)
        # Second delivery of the same event is idempotent (no re-handling).
        handled2, _ = handle_webhook(body, sig)
        self.assertFalse(handled2)

    def test_webhook_rejects_bad_signature(self):
        _, payment = self._setup()
        body = self._webhook_body(payment.razorpay_order_id)
        with self.assertRaises(PaymentError):
            handle_webhook(body, 'wrong-signature')

    def test_webhook_marks_failed(self):
        booking, payment = self._setup()
        body = self._webhook_body(payment.razorpay_order_id, event='payment.failed')
        handled, _ = handle_webhook(body, self._sign(body))
        payment.refresh_from_db()
        self.assertTrue(handled)
        self.assertEqual(payment.status, BookingPayment.STATUS_FAILED)


# ---------------------------------------------------------------------------
# Notifications (Part G) — server-side badge count, only when > 0
# ---------------------------------------------------------------------------

class NotificationBadgeTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='root', email='root@example.com', password='rootpass123')
        self.admin.groups.add(self.admin_group)
        self.owner = self.make_user(username='org1', group='EventOrganizer')
        self.event = self.make_event(self.owner)

    def test_admin_badge_when_pending_bookings_exist(self):
        attendee = self.make_user(username='attendee1')
        self.make_booking(attendee, self.event, status='pending')
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        # The sidebar "count" badge and topbar "dot" render only when count > 0.
        self.assertContains(response, 'class="count"')
        self.assertContains(response, 'class="dot"')
        self.assertContains(response, '1')

    def test_admin_badge_hidden_when_no_pending_items(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertNotContains(response, 'class="count"')
        self.assertNotContains(response, 'class="dot"')

    def test_organizer_badge_only_for_own_pending_bookings(self):
        attendee = self.make_user(username='attendee1')
        self.make_booking(attendee, self.event, status='pending')
        self.client.force_login(self.owner)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertContains(response, 'class="count"')
        self.assertContains(response, '1')

    def test_organizer_badge_ignores_confirmed_bookings(self):
        attendee = self.make_user(username='attendee1')
        self.make_booking(attendee, self.event, status='confirmed')
        self.client.force_login(self.owner)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertNotContains(response, 'class="count"')
        self.assertNotContains(response, 'class="dot"')

    def test_attendee_badge_reflects_non_cancelled_bookings(self):
        attendee = self.make_user(username='attendee1')
        self.make_booking(attendee, self.event, status='pending')
        self.client.force_login(attendee)
        response = self.client.get(reverse('attendee_dashboard'))
        # Attendees have no sidebar count — the topbar notification dot shows.
        self.assertContains(response, 'class="dot"')


# ---------------------------------------------------------------------------
# upload_live_images management command tests
# ---------------------------------------------------------------------------

@override_settings(BASE_DIR=None)  # overridden per-test in setUp
class UploadLiveImagesTests(TestCase):
    """Tests for the upload_live_images management command.

    Each test creates a temporary directory with the expected event_images/
    structure and overrides BASE_DIR so the command resolves source paths
    inside the temp directory — no real images are touched.
    """

    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._tmpdir = Path(self._tmp)

        # Create the category folder + a valid 1x1 PNG for each mapped category
        folders = {'birthday', 'catering', 'corperate', 'wedding'}
        for folder in folders:
            (self._tmpdir / 'event_images' / folder).mkdir(parents=True)
            for key, filename in LIVE_IMAGE_MAP.items():
                if key[1] == folder:
                    (self._tmpdir / 'event_images' / folder / filename).write_bytes(
                        PNG_1PX
                    )

        # MEDIA_ROOT inside the temp tree so default_storage saves there
        (self._tmpdir / 'media').mkdir()

        self._overrides = {
            'BASE_DIR': self._tmpdir,
            'MEDIA_ROOT': self._tmpdir / 'media',
        }

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    _event_counter = 0

    def _make_event(self, title='Event', category_name='Wedding', status='live'):
        cat, _ = EventCategory.objects.get_or_create(name=category_name)
        UploadLiveImagesTests._event_counter += 1
        return Event.objects.create(
            title=title,
            category=cat,
            description=f'{title} description.',
            price=100000,
            location='Kochi, Kerala',
            venue='Grand Hyatt',
            contact_number='9876543210',
            capacity=100,
            status=status,
            owner=User.objects.create_user(
                username=f'owner_{UploadLiveImagesTests._event_counter}',
                password='testpass123',
            ),
        )

    # ---- test 1: dry-run does not modify records ----

    def test_dry_run_does_not_modify_records(self):
        event = self._make_event('Birthday Bash', 'Birthday')
        with override_settings(**self._overrides):
            call_command('upload_live_images', '--dry-run', stdout=StringIO(),
                         stderr=StringIO())
        event.refresh_from_db()
        self.assertEqual(event.featured_image, '')

    # ---- test 2: correct live-event mapping ----

    def test_correct_live_event_mapping(self):
        event = self._make_event('Royal Wedding', 'Wedding')
        with override_settings(**self._overrides):
            call_command('upload_live_images', stdout=StringIO(),
                         stderr=StringIO())
        event.refresh_from_db()
        self.assertEqual(
            event.featured_image, 'events/pexels-alonssus-3212018.jpg',
        )
        dest = self._tmpdir / 'media' / 'events' / 'pexels-alonssus-3212018.jpg'
        self.assertTrue(dest.exists())

    # ---- test 3: non-live events are ignored ----

    def test_non_live_events_are_ignored(self):
        draft = self._make_event('Ghost Event', 'Wedding', status='draft')
        completed = self._make_event(
            'Zombie Event', 'Wedding', status='completed',
        )
        rejected = self._make_event(
            'Lost Event', 'Wedding', status='rejected',
        )
        with override_settings(**self._overrides):
            out = StringIO()
            call_command('upload_live_images', stdout=out, stderr=StringIO())
        draft.refresh_from_db()
        completed.refresh_from_db()
        rejected.refresh_from_db()
        self.assertEqual(draft.featured_image, '')
        self.assertEqual(completed.featured_image, '')
        self.assertEqual(rejected.featured_image, '')
        self.assertNotIn('Ghost Event', out.getvalue())
        self.assertNotIn('Zombie Event', out.getvalue())
        self.assertNotIn('Lost Event', out.getvalue())

    # ---- test 4: missing image is reported ----

    def test_missing_image_is_reported(self):
        event = self._make_event('Birthday Bash', 'Birthday')
        # Remove the source file so the command can't find it
        src = self._tmpdir / 'event_images' / 'birthday'
        for f in src.iterdir():
            f.unlink()
        with override_settings(**self._overrides):
            err = StringIO()
            with self.assertRaises(SystemExit) as ctx:
                call_command('upload_live_images', stdout=StringIO(),
                             stderr=err)
            self.assertEqual(ctx.exception.code, 1)
        self.assertIn('missing:', err.getvalue())

    # ---- test 5: repeated execution is idempotent ----

    def test_repeated_execution_is_idempotent(self):
        event = self._make_event('Intimate Wedding', 'Wedding')
        with override_settings(**self._overrides):
            call_command('upload_live_images', stdout=StringIO(),
                         stderr=StringIO())
        event.refresh_from_db()
        first_name = event.featured_image
        with override_settings(**self._overrides):
            out = StringIO()
            call_command('upload_live_images', stdout=out, stderr=StringIO())
        event.refresh_from_db()
        self.assertEqual(event.featured_image, first_name)
        self.assertIn('unchanged:', out.getvalue())
        # Summary line contains "uploaded: 0" — only check per-event lines.
        self.assertFalse(
            any('uploaded:' in line for line in out.getvalue().splitlines()
                if line.startswith('  ')),
        )
