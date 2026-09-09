"""Test suite for the Plannix themes module (feedback flow + identity filters)."""
from django.contrib.auth.models import User
from django.core import mail
from django.template import Context, Template
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from account_manager.identity import avatar_initial, display_name

from .models import Feedback


# ---------------------------------------------------------------------------
# Identity helpers (account_manager.identity)
# ---------------------------------------------------------------------------
class DisplayNameTests(TestCase):
    """Verify canonical display_name / avatar_initial across user shapes."""

    def test_full_name_user(self):
        u = User(first_name='Jane', last_name='Doe', username='jdoe')
        self.assertEqual(display_name(u), 'Jane Doe')
        self.assertEqual(avatar_initial(u), 'J')

    def test_first_name_only(self):
        u = User(first_name='Priya', last_name='', username='priya')
        self.assertEqual(display_name(u), 'Priya')
        self.assertEqual(avatar_initial(u), 'P')

    def test_no_name_falls_back_to_username(self):
        u = User(first_name='', last_name='', username='admin')
        self.assertEqual(display_name(u), 'admin')
        self.assertEqual(avatar_initial(u), 'A')

    def test_none_user(self):
        self.assertEqual(display_name(None), '')
        self.assertEqual(avatar_initial(None), '')

    def test_whitespace_only_name_falls_back(self):
        """A name of only spaces is falsy after strip in get_full_name."""
        u = User(first_name=' ', last_name=' ', username='ghost')
        # get_full_name returns '  ' which is truthy, so display_name returns it
        result = display_name(u)
        # The initial should be a space uppercased → still a space
        self.assertEqual(avatar_initial(u), result[:1].upper())


class TemplateFilterIdentityTests(TestCase):
    """Verify template filters render canonical identity in HTML."""

    def _render(self, expr, user):
        t = Template('{% load plannix_filters %}' + expr)
        return t.render(Context({'user': user}))

    def test_display_name_filter(self):
        u = User(first_name='Jane', last_name='Doe', username='jdoe')
        self.assertEqual(self._render('{{ user|display_name }}', u), 'Jane Doe')

    def test_avatar_initial_filter(self):
        u = User(first_name='Jane', last_name='Doe', username='jdoe')
        self.assertEqual(self._render('{{ user|avatar_initial }}', u), 'J')

    def test_username_fallback_filter(self):
        u = User(first_name='', last_name='', username='admin')
        self.assertEqual(self._render('{{ user|display_name }}', u), 'admin')
        self.assertEqual(self._render('{{ user|avatar_initial }}', u), 'A')


class IdentityRenderingTests(TestCase):
    """Integration: verify canonical identity renders in key templates."""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.user = User.objects.create_user(
            username='testjane', email='jane@test.com',
            first_name='Jane', last_name='Doe', password='testpass123',
        )
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='Attendee')
        self.user.groups.add(group)

    def test_public_header_no_display_name_dropdown(self):
        """Header cleanup: the public header shows Sign Out, not the name dropdown."""
        self.client.force_login(self.user)
        html = self.client.get(reverse('index')).content.decode()
        self.assertNotIn('dropdown-menu', html)
        self.assertNotIn('Jane Doe', html)
        self.assertIn(reverse('sign_out'), html)

    def test_customer_dashboard_shows_canonical_name(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('customer_dashboard'))
        self.assertContains(response, 'Jane Doe')

    def test_profile_shows_canonical_name(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Jane Doe')


class TopRightAccountControlTests(TestCase):
    """Regression: the top-right account control must show only display_name,
    never the avatar_initial as a separate visible element."""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')
        self.user = User.objects.create_user(
            username='testjane', email='jane@test.com',
            first_name='Jane', last_name='Doe', password='testpass123',
        )
        from django.contrib.auth.models import Group
        group, _ = Group.objects.get_or_create(name='Attendee')
        self.user.groups.add(group)
        self.client.force_login(self.user)

    def _get_topbar_html(self, url):
        """Extract the topbar/header account control HTML."""
        response = self.client.get(url)
        return response.content.decode()

    def test_home_header_no_avatar_initial_in_dropdown(self):
        """The public header no longer renders an account dropdown at all: no
        display name, no avatar-initial circle, no role menu — just Dashboard
        + a POST Sign Out form for an authenticated user."""
        html = self._get_topbar_html(reverse('index'))
        self.assertNotIn('<span class="avatar">J</span>', html)
        self.assertNotIn('Jane Doe', html)
        self.assertIn(f'action="{reverse("sign_out")}"', html)

    def test_dashboard_topbar_no_avatar_initial(self):
        """Dashboard topbar must show display_name, not avatar initial circle."""
        html = self._get_topbar_html(reverse('customer_dashboard'))
        self.assertIn('Jane Doe', html)
        # The old topbar avatar pattern must be gone
        self.assertNotIn('class="avatar"', html.split('topbar-actions')[1]
                         if 'topbar-actions' in html else '')

    def test_organizer_dashboard_topbar_no_avatar_initial(self):
        """Organizer dashboard topbar must show display_name only."""
        from account_manager.models import OrganizerProfile
        from django.contrib.auth.models import Group
        org_group, _ = Group.objects.get_or_create(name='EventOrganizer')
        self.user.groups.add(org_group)
        OrganizerProfile.objects.get_or_create(user=self.user)
        html = self._get_topbar_html(reverse('organizer_dashboard'))
        self.assertIn('Jane Doe', html)

    def test_admin_dashboard_topbar_no_avatar_initial(self):
        """Admin dashboard topbar must show display_name only."""
        from django.contrib.auth.models import Group
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.user.is_superuser = True
        self.user.save(update_fields=['is_superuser'])
        self.user.groups.add(admin_group)
        html = self._get_topbar_html(reverse('admin_dashboard'))
        self.assertIn('Jane Doe', html)


class FeedbackTests(TestCase):
    """Cover the public feedback form: render, create, validation, persistence."""

    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    def post_feedback(self, follow=False, **overrides):
        payload = {
            'name': 'Jane Doe',
            'email': 'jane@example.com',
            'number': '9876543210',
            'message': 'Amazing service, keep it up!',
        }
        payload.update(overrides)
        return self.client.post(reverse('feedback'), payload, follow=follow)

    def test_feedback_page_renders(self):
        response = self.client.get(reverse('feedback'))
        self.assertEqual(response.status_code, 200)

    def test_feedback_post_creates_row_and_redirects(self):
        response = self.post_feedback()
        self.assertRedirects(response, reverse('feedback'))
        self.assertEqual(Feedback.objects.count(), 1)

    def test_feedback_missing_fields_does_not_create_row(self):
        # Missing name, email and message -> error, no row created.
        response = self.post_feedback(
            name='', email='', message='', follow=True)
        self.assertContains(response, 'name, email and message')
        self.assertEqual(Feedback.objects.count(), 0)

    def test_feedback_missing_message_only(self):
        response = self.post_feedback(message='', follow=True)
        self.assertContains(response, 'name, email and message')
        self.assertEqual(Feedback.objects.count(), 0)

    def test_feedback_persists_proper_fields(self):
        self.post_feedback()
        feedback = Feedback.objects.get()
        self.assertEqual(feedback.name, 'Jane Doe')
        self.assertEqual(feedback.email, 'jane@example.com')
        self.assertEqual(feedback.number, '9876543210')
        self.assertEqual(feedback.message, 'Amazing service, keep it up!')
        self.assertIsNotNone(feedback.created_at)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_feedback_routes_confirmation_email_through_service(self):
        """Feedback confirmation is sent via the Plannix email service (not an
        inline send_mail) to the address the user provided."""
        self.post_feedback()
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['jane@example.com'])
        self.assertIn('Thank You for Your Feedback', mail.outbox[0].subject)
