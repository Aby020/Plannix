"""Test suite for the Plannix events module."""
from datetime import date, timedelta

from django.contrib.auth.models import Group, User
from django.test import Client, TestCase
from django.urls import reverse

from themes.models import Feedback

from .models import Event_Booking, Event_Company

# ALLOWED_HOSTS only permits 127.0.0.1/localhost in production-style runs,
# so the default 'testserver' host is rejected. Point the client at localhost.


class PlannixTestCase(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    # ---- helpers ----
    def make_user(self, username='customer', group=None, **kwargs):
        user = User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='testpass123',
            **kwargs,
        )
        if group:
            user.groups.add(Group.objects.get(name=group))
        return user

    def make_event(self, **overrides):
        data = {
            'event_name': 'Royal Wedding Package',
            'event_type': 'Wedding',
            'event_price': 150000,
            'event_description': 'A complete wedding planning package.',
            'event_mobile_number': '9876543210',
            'package1': 'Venue booking',
            'package2': 'Decor & catering',
            'package3': 'Photography',
            'package4': 'Music',
            'location': 'Kochi, Kerala',
        }
        data.update(overrides)
        return Event_Company.objects.create(**data)

    def make_booking(self, user, event, **overrides):
        data = {
            'user': user,
            'name': user.get_full_name() or user.username,
            'email': user.email,
            'number': '9876543210',
            'event_company_name': event.event_name,
            'event_type': event.event_type,
            'event_price': event.event_price,
            'event_location': event.location,
            'event_mobile_number': event.event_mobile_number,
            'event_booking_date': (date.today() + timedelta(days=7)).isoformat(),
            'status': 'pending',
        }
        data.update(overrides)
        return Event_Booking.objects.create(**data)


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------

class PublicCatalogueTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.wedding = self.make_event(event_name='Grand Wedding', event_type='Wedding')
        self.party = self.make_event(event_name='Corporate Party', event_type='Corporate')

    def test_index_page_renders(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Plannix')

    def test_events_page_lists_all(self):
        response = self.client.get(reverse('events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertContains(response, 'Corporate Party')

    def test_events_page_filters_by_type(self):
        response = self.client.get(reverse('events'), {'type': 'wedding'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertNotContains(response, 'Corporate Party')

    def test_readmore_shows_event(self):
        response = self.client.get(reverse('readmore', args=[self.wedding.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')
        self.assertContains(response, 'A complete wedding planning package.')

    def test_readmore_missing_event_is_404(self):
        response = self.client.get(reverse('readmore', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_search_by_name(self):
        response = self.client.get(reverse('searching_events'), {'q': 'wedding'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grand Wedding')

    def test_search_with_no_results(self):
        response = self.client.get(reverse('searching_events'), {'q': 'nonexistentxyz'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No packages found')

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
        self.user = self.make_user()
        self.event = self.make_event()

    def test_booking_form_requires_login(self):
        response = self.client.get(reverse('selected_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('sign_in'), response.url)

    def test_booking_form_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('selected_event', args=[self.event.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_create_booking_success(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test Customer',
            'email': self.user.email,
            'number': '9876543210',
            'event_company_name': self.event.event_name,
            'event_type': self.event.event_type,
            'event_price': self.event.event_price,
            'event_location': self.event.location,
            'event_mobile_number': self.event.event_mobile_number,
            'date': (date.today() + timedelta(days=7)).isoformat(),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('success'))
        booking = Event_Booking.objects.get(user=self.user)
        self.assertEqual(booking.status, 'pending')
        self.assertEqual(booking.event_company_name, self.event.event_name)

    def test_booking_rejects_past_date(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test Customer',
            'email': self.user.email,
            'number': '9876543210',
            'event_company_name': self.event.event_name,
            'event_type': self.event.event_type,
            'event_price': self.event.event_price,
            'event_location': self.event.location,
            'event_mobile_number': self.event.event_mobile_number,
            'date': (date.today() - timedelta(days=1)).isoformat(),
        }, follow=True)
        self.assertContains(response, 'date in the past')
        self.assertEqual(Event_Booking.objects.count(), 0)

    def test_booking_rejects_invalid_number(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test Customer',
            'email': self.user.email,
            'number': '12345',
            'event_company_name': self.event.event_name,
            'event_type': self.event.event_type,
            'event_price': self.event.event_price,
            'event_location': self.event.location,
            'event_mobile_number': self.event.event_mobile_number,
            'date': (date.today() + timedelta(days=7)).isoformat(),
        }, follow=True)
        self.assertContains(response, '10-digit mobile number')
        self.assertEqual(Event_Booking.objects.count(), 0)

    def test_booking_rejects_date_conflict(self):
        self.client.force_login(self.user)
        booking_date = (date.today() + timedelta(days=7)).isoformat()
        self.make_booking(self.user, self.event, event_booking_date=booking_date)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': 'Test Customer',
            'email': self.user.email,
            'number': '9876543210',
            'event_company_name': self.event.event_name,
            'event_type': self.event.event_type,
            'event_price': self.event.event_price,
            'event_location': self.event.location,
            'event_mobile_number': self.event.event_mobile_number,
            'date': booking_date,
        }, follow=True)
        self.assertContains(response, 'already booked')
        self.assertEqual(Event_Booking.objects.count(), 1)

    def test_booking_rejects_missing_fields(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('event_booking'), {
            'event_id': self.event.pk,
            'name': '',
            'email': self.user.email,
            'number': '9876543210',
            'event_company_name': self.event.event_name,
            'event_type': self.event.event_type,
            'event_price': self.event.event_price,
            'event_location': self.event.location,
            'event_mobile_number': self.event.event_mobile_number,
            'date': (date.today() + timedelta(days=7)).isoformat(),
        }, follow=True)
        self.assertContains(response, 'required fields')
        self.assertEqual(Event_Booking.objects.count(), 0)


# ---------------------------------------------------------------------------
# Customer dashboards & bookings
# ---------------------------------------------------------------------------

class CustomerDashboardTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()
        self.event = self.make_event()
        self.booking = self.make_booking(self.user, self.event)

    def test_dashboard_redirects_customer(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('dashboard'))
        self.assertRedirects(response, reverse('customer_dashboard'))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_customer_dashboard_renders(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_my_bookings_lists_own_bookings_only(self):
        other = self.make_user(username='other')
        self.make_booking(other, self.event, event_company_name='Somebody Else Event')
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_bookings'))
        self.assertContains(response, self.event.event_name)
        self.assertNotContains(response, 'Somebody Else Event')

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
# Staff management
# ---------------------------------------------------------------------------

class StaffManagementTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        Group.objects.get_or_create(name='staff')
        Group.objects.get_or_create(name='admin')
        self.customer = self.make_user(username='cust1')
        self.staff = self.make_user(username='staff1', group='staff')
        self.event = self.make_event()
        self.booking = self.make_booking(self.customer, self.event)
        self.feedback = Feedback.objects.create(
            name='Jane', email='jane@example.com', number='9876543210',
            message='Amazing service!',
        )

    def test_staff_dashboard_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('staff_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_customer_blocked_from_staff_dashboard(self):
        self.client.force_login(self.customer)
        response = self.client.get(reverse('staff_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_manage_events_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('manage_events'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_add_event(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('add_event'), {
            'event_name': 'Birthday Bash',
            'event_type': 'Birthday',
            'event_price': '50000',
            'event_description': 'A fun birthday package.',
            'event_mobile_number': '9876543210',
            'package1': 'Cake & decor',
            'location': 'Kochi, Kerala',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('manage_events'))
        self.assertTrue(Event_Company.objects.filter(event_name='Birthday Bash').exists())

    def test_add_event_requires_required_fields(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('add_event'), {'event_name': ''}, follow=True)
        self.assertEqual(Event_Company.objects.count(), 1)  # only the seed event

    def test_add_event_rejects_non_numeric_price(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('add_event'), {
            'event_name': 'Bad Price',
            'event_type': 'Party',
            'event_price': 'abc',
            'event_description': 'desc',
            'location': 'Kochi',
        }, follow=True)
        self.assertFalse(Event_Company.objects.filter(event_name='Bad Price').exists())

    def test_edit_event(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('edit_event', args=[self.event.pk]), {
            'event_name': 'Updated Wedding',
            'event_type': 'Wedding',
            'event_price': '200000',
            'event_description': 'An updated package.',
            'event_mobile_number': '9876543210',
            'location': 'Kochi, Kerala',
        })
        self.assertEqual(response.status_code, 302)
        self.event.refresh_from_db()
        self.assertEqual(self.event.event_name, 'Updated Wedding')
        self.assertEqual(self.event.event_price, 200000)

    def test_delete_event(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('delete_event', args=[self.event.pk]))
        self.assertFalse(Event_Company.objects.filter(pk=self.event.pk).exists())

    def test_manage_bookings_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('manage_bookings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_manage_bookings_status_filter(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('manage_bookings'), {'status': 'confirmed'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.event.event_name)

    def test_update_booking_status(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('update_booking_status', args=[self.booking.pk]), {'status': 'confirmed'})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'confirmed')

    def test_update_booking_status_rejects_unknown(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('update_booking_status', args=[self.booking.pk]), {'status': 'nonsense'})
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')

    def test_delete_booking(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('delete_booking', args=[self.booking.pk]))
        self.assertFalse(Event_Booking.objects.filter(pk=self.booking.pk).exists())

    def test_manage_feedback_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('manage_feedback'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Amazing service!')

    def test_delete_feedback(self):
        self.client.force_login(self.staff)
        self.client.post(reverse('delete_feedback', args=[self.feedback.pk]))
        self.assertFalse(Feedback.objects.filter(pk=self.feedback.pk).exists())


# ---------------------------------------------------------------------------
# Admin management
# ---------------------------------------------------------------------------

class AdminManagementTests(PlannixTestCase):
    def setUp(self):
        super().setUp()
        Group.objects.get_or_create(name='staff')
        self.staff = self.make_user(username='staff1', group='staff')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.target = self.make_user(username='target')
        self.event = self.make_event()
        self.make_booking(self.target, self.event)

    def test_admin_dashboard_renders(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.event.event_name)

    def test_staff_blocked_from_admin_dashboard(self):
        self.client.force_login(self.staff)
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
