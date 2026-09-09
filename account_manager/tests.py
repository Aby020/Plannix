"""Test suite for the Plannix account manager (authentication & profile)."""
from unittest.mock import patch

from django.contrib.auth.models import Group, User
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import Organization
from .services import (
    approve_organization,
    reject_organization,
    resubmit_organization,
    submit_organization,
)


class PlannixAuthTestCase(TestCase):
    def setUp(self):
        self.client = Client(SERVER_NAME='localhost')

    def make_user(self, username='alice', **kwargs):
        return User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='testpass123',
            **kwargs,
        )


class SignUpTests(PlannixAuthTestCase):
    def test_signup_page_renders(self):
        response = self.client.get(reverse('sign_up'))
        self.assertEqual(response.status_code, 200)

    def test_signup_creates_user_and_redirects(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        })
        self.assertRedirects(response, reverse('sign_in'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        # Registration must NOT auto-authenticate: the new user has no session.
        self.assertNotIn('_auth_user_id', self.client.session)

    # Migration 0010 creates a dedicated 'plannix_platform' system user, so all
    # raw User counts are offset by one; filter it out when counting signups.
    def active_users(self):
        return User.objects.exclude(username='plannix_platform')

    def test_signup_missing_fields(self):
        response = self.client.post(reverse('sign_up'), {
            'username': '',
            'email': 'new@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'required')
        self.assertFalse(self.active_users().filter(email='new@example.com').exists())

    def test_signup_duplicate_username(self):
        self.make_user()
        response = self.client.post(reverse('sign_up'), {
            'username': 'alice',
            'email': 'other@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'already taken')
        self.assertEqual(self.active_users().count(), 1)

    def test_signup_duplicate_email(self):
        self.make_user()
        response = self.client.post(reverse('sign_up'), {
            'username': 'bob',
            'email': 'alice@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'already exists')
        self.assertEqual(self.active_users().count(), 1)

    def test_signup_password_mismatch(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'bob',
            'email': 'bob@example.com',
            'password': 'securepass123',
            'confirm_password': 'different123',
        }, follow=True)
        self.assertContains(response, 'do not match')
        self.assertFalse(self.active_users().filter(username='bob').exists())

    def test_authenticated_user_redirected_away(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('sign_up'))
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_signup_captures_display_name(self):
        """Sign-up stores the user's first/last name in the standard User fields."""
        response = self.client.post(reverse('sign_up'), {
            'username': 'newuser',
            'email': 'new@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
            'first_name': 'Priya',
            'last_name': 'Menon',
        })
        self.assertRedirects(response, reverse('sign_in'))
        user = User.objects.get(username='newuser')
        self.assertEqual(user.first_name, 'Priya')
        self.assertEqual(user.last_name, 'Menon')
        self.assertEqual(user.get_full_name(), 'Priya Menon')


class DisplayNameTests(PlannixAuthTestCase):
    """The signed-in user's name must show correctly and never another's."""

    def _make_named_user(self, username='alice', first_name='Alice', last_name='Smith'):
        return User.objects.create_user(
            username=username,
            email=f'{username}@example.com',
            password='testpass123',
            first_name=first_name,
            last_name=last_name,
        )

    def test_dashboard_shows_own_name(self):
        """The attendee dashboard topbar shows the canonical display name."""
        self._make_named_user()
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('customer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice Smith')

    def test_dashboard_falls_back_to_username(self):
        # A user with no name set still shows their username, not a blank.
        self.make_user(username='nono')
        self.client.force_login(User.objects.get(username='nono'))
        response = self.client.get(reverse('customer_dashboard'))
        self.assertContains(response, 'nono')

    def test_public_header_shows_sign_out_not_dropdown(self):
        """The public header keeps a minimal Sign Out form and no role dropdown."""
        user = self._make_named_user()
        self.client.force_login(user)
        html = self.client.get(reverse('index')).content.decode()
        self.assertIn(f'action="{reverse("sign_out")}"', html)
        self.assertNotIn('dropdown-menu', html)
        # The sign out form must carry a CSRF token (secure logout preserved).
        self.assertIn('csrfmiddlewaretoken', html)

    def test_attendee_dashboard_shows_own_name_only(self):
        self._make_named_user()
        self._make_named_user(username='bob', first_name='Bob', last_name='Jones')
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('attendee_dashboard'))
        self.assertContains(response, 'Alice Smith')
        self.assertNotContains(response, 'Bob Jones')

    def test_organizer_dashboard_shows_own_name_only(self):
        group, _ = Group.objects.get_or_create(name='EventOrganizer')
        alice = self._make_named_user()
        group.user_set.add(alice)
        self._make_named_user(username='bob', first_name='Bob', last_name='Jones')
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice Smith')
        self.assertNotContains(response, 'Bob Jones')

    def test_admin_dashboard_shows_own_name_only(self):
        superuser = User.objects.create_superuser(
            username='root', email='root@example.com', password='testpass123',
            first_name='Ria', last_name='Kurian',
        )
        self._make_named_user(username='bob', first_name='Bob', last_name='Jones')
        self.client.force_login(superuser)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Ria Kurian')
        self.assertNotContains(response, 'Bob Jones')


class SignInTests(PlannixAuthTestCase):
    def test_signin_page_renders(self):
        response = self.client.get(reverse('sign_in'))
        self.assertEqual(response.status_code, 200)

    def test_signin_success_redirects_to_home(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice',
            'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_signin_with_safe_next_redirects_there(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice',
            'password': 'testpass123',
            'next': '/events',
        })
        self.assertRedirects(response, '/events', fetch_redirect_response=False)

    def test_signin_with_malicious_next_is_blocked(self):
        # An absolute URL to an external host must be ignored (open-redirect guard).
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice',
            'password': 'testpass123',
            'next': 'https://evil.example/phish',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_signin_wrong_password(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice',
            'password': 'wrongpass',
        }, follow=True)
        self.assertContains(response, 'Invalid username or password')

    def test_authenticated_user_redirected_away(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('sign_in'))
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)


class SignOutTests(PlannixAuthTestCase):
    def test_signout_logs_out(self):
        user = self.make_user()
        self.client.force_login(user)
        self.client.post(reverse('sign_out'), follow=True)
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_signout_get_returns_405(self):
        """sign_out is POST-only — GET returns Method Not Allowed."""
        response = self.client.get(reverse('sign_out'))
        self.assertEqual(response.status_code, 405)


class ProfileTests(PlannixAuthTestCase):
    def test_profile_requires_login(self):
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('sign_in'), response.url)

    def test_profile_page_renders(self):
        user = self.make_user(first_name='Alice', last_name='Smith')
        self.client.force_login(user)
        response = self.client.get(reverse('profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Alice')

    def test_profile_update(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.post(reverse('profile'), {
            'first_name': 'Alice',
            'last_name': 'Wonder',
            'email': 'alice.wonder@example.com',
        }, follow=True)
        user.refresh_from_db()
        self.assertEqual(user.first_name, 'Alice')
        self.assertEqual(user.last_name, 'Wonder')
        self.assertEqual(user.email, 'alice.wonder@example.com')
        self.assertContains(response, 'profile has been updated')

    def test_profile_email_required(self):
        user = self.make_user()
        self.client.force_login(user)
        self.client.post(reverse('profile'), {
            'first_name': 'Alice',
            'last_name': '',
            'email': '',
        }, follow=True)
        user.refresh_from_db()
        self.assertEqual(user.email, 'alice@example.com')

    def test_profile_email_must_be_unique(self):
        self.make_user(username='existing')
        user = self.make_user(username='newbie')
        self.client.force_login(user)
        self.client.post(reverse('profile'), {
            'first_name': '',
            'last_name': '',
            'email': 'existing@example.com',
        }, follow=True)
        user.refresh_from_db()
        self.assertEqual(user.email, 'newbie@example.com')


class PasswordChangeTests(PlannixAuthTestCase):
    def test_change_password_page_renders(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('change_password'))
        self.assertEqual(response.status_code, 200)

    def test_change_password_success(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.post(reverse('change_password'), {
            'old_password': 'testpass123',
            'new_password1': 'brandnewpass456',
            'new_password2': 'brandnewpass456',
        })
        self.assertRedirects(response, reverse('profile'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('brandnewpass456'))

    def test_change_password_wrong_old_password(self):
        user = self.make_user()
        self.client.force_login(user)
        self.client.post(reverse('change_password'), {
            'old_password': 'wrongold',
            'new_password1': 'brandnewpass456',
            'new_password2': 'brandnewpass456',
        }, follow=True)
        user.refresh_from_db()
        self.assertTrue(user.check_password('testpass123'))


# ---------------------------------------------------------------------------
# Organization lifecycle services
# ---------------------------------------------------------------------------

class OrganizationServiceTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')

    def make_org(self, **overrides):
        data = {
            'owner': self.organizer,
            'name': 'Elegant Events Co.',
            'description': 'Premium event planning.',
            'contact_number': '9876543210',
        }
        data.update(overrides)
        return Organization.objects.create(**data)

    def test_submit_sets_pending_and_timestamp(self):
        org = self.make_org()
        submit_organization(org)
        org.refresh_from_db()
        self.assertEqual(org.status, 'pending')
        self.assertIsNotNone(org.submitted_at)

    def test_submit_validates_name(self):
        org = self.make_org(name='')
        with self.assertRaises(ValueError):
            submit_organization(org)

    def test_submit_validates_description(self):
        org = self.make_org(description='')
        with self.assertRaises(ValueError):
            submit_organization(org)

    def test_submit_validates_contact(self):
        org = self.make_org(contact_number='')
        with self.assertRaises(ValueError):
            submit_organization(org)

    def test_approve_sets_approved_at(self):
        org = self.make_org()
        submit_organization(org)
        approve_organization(org, self.admin, notes='Looks good')
        org.refresh_from_db()
        self.assertEqual(org.status, 'approved')
        self.assertIsNotNone(org.approved_at)
        self.assertEqual(org.review_notes, 'Looks good')

    def test_approve_requires_pending(self):
        org = self.make_org(status='approved')
        with self.assertRaises(ValueError):
            approve_organization(org, self.admin)

    def test_reject_requires_reason(self):
        org = self.make_org()
        submit_organization(org)
        with self.assertRaises(ValueError):
            reject_organization(org, self.admin, reason='')

    def test_reject_sets_reason(self):
        org = self.make_org()
        submit_organization(org)
        reject_organization(org, self.admin, reason='Incomplete details')
        org.refresh_from_db()
        self.assertEqual(org.status, 'rejected')
        self.assertEqual(org.rejection_reason, 'Incomplete details')

    def test_reject_requires_pending(self):
        org = self.make_org(status='approved')
        with self.assertRaises(ValueError):
            reject_organization(org, self.admin, reason='Nope')

    def test_reject_then_resubmit_sets_pending(self):
        org = self.make_org()
        submit_organization(org)
        reject_organization(org, self.admin, reason='Needs work')
        resubmit_organization(org)
        org.refresh_from_db()
        self.assertEqual(org.status, 'pending')
        self.assertEqual(org.rejection_reason, '')

    def test_submit_on_approved_is_forbidden(self):
        org = self.make_org(status='approved')
        with self.assertRaises(ValueError):
            submit_organization(org)


# ---------------------------------------------------------------------------
# my_organization view
# ---------------------------------------------------------------------------

class MyOrganizationViewTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        self.attendee = self.make_user(username='attendee1')
        self.attendee.groups.add(Group.objects.get_or_create(name='Attendee')[0])

    def test_organizer_can_create_organization(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('my_organization'), {
            'name': 'Elegant Events Co.',
            'contact_number': '9876543210',
            'email': 'info@elegant.com',
            'description': 'Premium event planning.',
        })
        self.assertRedirects(response, reverse('my_organization'))
        self.assertTrue(Organization.objects.filter(owner=self.organizer).exists())

    def test_organizer_can_edit_organization(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Old Name',
            description='Old.', contact_number='1234567890',
        )
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('my_organization'), {
            'name': 'New Name',
            'contact_number': '9876543210',
            'description': 'Updated description.',
        })
        self.assertRedirects(response, reverse('my_organization'))
        org.refresh_from_db()
        self.assertEqual(org.name, 'New Name')

    def test_submit_organization_flips_to_pending(self):
        org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('submit_organization'))
        self.assertRedirects(response, reverse('my_organization'))
        org.refresh_from_db()
        self.assertEqual(org.status, 'pending')
        self.assertIsNotNone(org.submitted_at)

    def test_submit_without_org_redirects(self):
        self.client.force_login(self.organizer)
        response = self.client.post(reverse('submit_organization'))
        self.assertRedirects(response, reverse('my_organization'))

    def test_attendee_blocked_from_my_organization(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('my_organization'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# manage_organizations (admin-only)
# ---------------------------------------------------------------------------

class ManageOrganizationsTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        self.attendee = self.make_user(username='attendee1')
        self.attendee.groups.add(Group.objects.get_or_create(name='Attendee')[0])
        self.org = Organization.objects.create(
            owner=self.organizer, name='Elegant Events',
            description='Planning.', contact_number='9876543210',
        )

    def test_admin_can_view_manage_organizations(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_organizations'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Elegant Events')

    def test_organizer_blocked_from_manage_organizations(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('manage_organizations'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_attendee_blocked_from_manage_organizations(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('manage_organizations'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_filter_by_status(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('manage_organizations'), {'status': 'pending'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Elegant Events')


# ---------------------------------------------------------------------------
# approve_organization / reject_organization views
# ---------------------------------------------------------------------------

class OrgApprovalViewTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        self.org = Organization.objects.create(
            owner=self.organizer, name='Events Co.',
            description='Planning.', contact_number='9876543210',
        )
        submit_organization(self.org)

    def test_approve_organization(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('approve_organization', args=[self.org.pk]), {'notes': 'Approved'})
        self.assertRedirects(response, reverse('approval_queue'))
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'approved')

    def test_reject_organization(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('reject_organization', args=[self.org.pk]), {'reason': 'Incomplete'})
        self.assertRedirects(response, reverse('approval_queue'))
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'rejected')

    def test_reject_organization_without_reason(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('reject_organization', args=[self.org.pk]))
        self.assertRedirects(response, reverse('approval_queue'))
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'pending')  # unchanged

    def test_approve_nonexistent_org_404(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('approve_organization', args=[99999]))
        self.assertEqual(response.status_code, 404)

    def test_organizer_blocked_from_approve_org(self):
        self.client.force_login(self.organizer)
        response = self.client.post(
            reverse('approve_organization', args=[self.org.pk]), {'notes': 'hax'})
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)
        self.org.refresh_from_db()
        self.assertEqual(self.org.status, 'pending')


# ---------------------------------------------------------------------------
# Role guards for org pages
# ---------------------------------------------------------------------------

class OrgRoleGuardTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        self.attendee = self.make_user(username='attendee1')
        self.attendee.groups.add(Group.objects.get_or_create(name='Attendee')[0])

    def test_attendee_blocked_from_my_organization(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('my_organization'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_attendee_blocked_from_submit_organization(self):
        self.client.force_login(self.attendee)
        response = self.client.post(reverse('submit_organization'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_anonymous_blocked_from_my_organization(self):
        response = self.client.get(reverse('my_organization'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('sign_in'), response.url)


# ---------------------------------------------------------------------------
# Role-aware header navigation (base.html)
# ---------------------------------------------------------------------------

class RoleAwareNavTests(PlannixAuthTestCase):
    """Role-specific navigation renders only on the matching role's dashboard,
    and the public header exposes only a Dashboard link + Sign Out — never a
    role-specific menu or another role's dashboard link."""

    def setUp(self):
        super().setUp()
        self.attendee = self.make_user(username='attendee1')
        self.attendee.groups.add(Group.objects.get_or_create(name='Attendee')[0])
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        self.admin = User.objects.create_superuser(
            username='admin1', email='admin1@example.com', password='testpass123')
        self.admin.groups.add(admin_group)

    def render_dashboard_for(self, user, url_name):
        self.client.force_login(user)
        return self.client.get(reverse(url_name))

    def test_public_header_has_no_role_specific_nav(self):
        """The public navbar shows only Dashboard + Sign Out for an authenticated
        user (even an admin) — never an admin/organizer menu. (The footer keeps
        its role links; only the navbar dropdown was removed.)"""
        self.client.force_login(self.admin)
        html = self.client.get(reverse('index')).content.decode()
        header = html.split('<nav class="px-navbar')[1].split('</nav>')[0]
        # The Dashboard link is role-aware — the admin sees admin-dashboard.
        self.assertIn(reverse('admin_dashboard'), header)
        self.assertIn(f'action="{reverse("sign_out")}"', header)
        self.assertNotIn('href="' + reverse('approval_queue') + '"', header)
        self.assertNotIn('href="' + reverse('manage_organizations') + '"', header)
        self.assertNotIn('href="' + reverse('my_bookings') + '"', header)
        self.assertNotIn('dropdown-menu', header)

    def test_attendee_nav(self):
        response = self.render_dashboard_for(self.attendee, 'attendee_dashboard')
        self.assertContains(response, reverse('my_bookings'))
        # Exact href matching so a role-specific path is not confused with a
        # prefix of an admin-only path (e.g. /manage/organizations).
        self.assertNotContains(response, 'href="' + reverse('organizer_dashboard') + '"')
        self.assertNotContains(response, 'href="' + reverse('admin_dashboard') + '"')
        self.assertNotContains(response, 'href="' + reverse('my_organization') + '"')
        self.assertNotContains(response, 'href="' + reverse('manage_organizations') + '"')

    def test_organizer_nav(self):
        response = self.render_dashboard_for(self.organizer, 'organizer_dashboard')
        self.assertContains(response, reverse('my_organization'))
        self.assertNotContains(response, 'href="' + reverse('attendee_dashboard') + '"')
        self.assertNotContains(response, 'href="' + reverse('admin_dashboard') + '"')
        self.assertNotContains(response, 'href="' + reverse('approval_queue') + '"')
        self.assertNotContains(response, 'href="' + reverse('manage_organizations') + '"')

    def test_admin_nav(self):
        response = self.render_dashboard_for(self.admin, 'admin_dashboard')
        self.assertContains(response, reverse('approval_queue'))
        self.assertContains(response, reverse('manage_organizations'))
        self.assertNotContains(response, 'href="' + reverse('my_bookings') + '"')
        self.assertNotContains(response, 'href="' + reverse('my_organization') + '"')

    def test_anonymous_nav_has_sign_in_but_no_dashboard(self):
        response = self.client.get(reverse('about'))
        self.assertContains(response, reverse('sign_in'))
        self.assertNotContains(response, reverse('attendee_dashboard'))
        self.assertNotContains(response, reverse('admin_dashboard'))


# ---------------------------------------------------------------------------
# Unauthorized dashboard access
# ---------------------------------------------------------------------------

class DashboardAccessTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.attendee = self.make_user(username='attendee1')
        self.attendee.groups.add(Group.objects.get_or_create(name='Attendee')[0])
        self.organizer = self.make_user(username='org1')
        self.organizer.groups.add(Group.objects.get_or_create(name='EventOrganizer')[0])

    def test_anonymous_blocked_from_all_dashboards(self):
        for name in ('attendee_dashboard', 'organizer_dashboard', 'admin_dashboard'):
            response = self.client.get(reverse(name))
            self.assertEqual(response.status_code, 302)
            self.assertIn(reverse('sign_in'), response.url)

    def test_attendee_can_access_attendee_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('attendee_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_attendee_blocked_from_organizer_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('organizer_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_attendee_blocked_from_admin_dashboard(self):
        self.client.force_login(self.attendee)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

    def test_organizer_blocked_from_admin_dashboard(self):
        self.client.force_login(self.organizer)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Registration with role selection (user_type)
# ---------------------------------------------------------------------------

class SignUpRoleTests(PlannixAuthTestCase):
    """Registration must accept user_type (attendee/organizer) from the form,
    create the correct group assignment, and never allow admin registration."""

    def _signup(self, user_type='attendee', **overrides):
        data = {
            'username': overrides.pop('username', 'newuser'),
            'email': overrides.pop('email', 'new@example.com'),
            'password': 'securepass123',
            'confirm_password': 'securepass123',
            'user_type': user_type,
        }
        data.update(overrides)
        return self.client.post(reverse('sign_up'), data, follow=True)

    def test_signup_as_attendee_creates_user_in_attendee_group(self):
        self._signup(user_type='attendee')
        user = User.objects.get(username='newuser')
        self.assertTrue(user.groups.filter(name='Attendee').exists())

    def test_signup_as_organizer_creates_user_in_organizer_group(self):
        self._signup(user_type='organizer')
        user = User.objects.get(username='newuser')
        self.assertTrue(user.groups.filter(name='EventOrganizer').exists())

    def test_signup_default_is_attendee(self):
        self._signup(user_type='invalid_garbage')
        user = User.objects.get(username='newuser')
        self.assertTrue(user.groups.filter(name='Attendee').exists())
        self.assertFalse(user.groups.filter(name='EventOrganizer').exists())

    def test_signup_admin_type_falls_back_to_attendee(self):
        """User cannot register as Admin via user_type='admin'."""
        self._signup(user_type='admin')
        user = User.objects.get(username='newuser')
        self.assertTrue(user.groups.filter(name='Attendee').exists())
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_signup_organizer_creates_initial_pending_organization(self):
        """Organizer signup seeds an initial pending Organization that stays out
        of the admin approval queue until the organizer submits it."""
        self._signup(user_type='organizer')
        user = User.objects.get(username='newuser')
        org = Organization.objects.get(owner=user)
        self.assertEqual(org.status, 'pending')
        self.assertIsNone(org.submitted_at)
        self.assertFalse(org.is_approved)

    def test_signup_attendee_does_not_create_organization(self):
        self._signup(user_type='attendee')
        self.assertFalse(Organization.objects.exists())

    def test_initial_org_not_in_approval_queue_until_submitted(self):
        """An org seeded at signup (submitted_at=None) must not appear in the
        admin approval queue until the organizer submits it."""
        self._signup(user_type='organizer')
        user = User.objects.get(username='newuser')
        self.client.force_login(User.objects.create_superuser(
            username='adminx', email='adminx@example.com', password='testpass123'))
        html = self.client.get(reverse('approval_queue')).content.decode()
        # No org row has been submitted yet, so nothing is queued.
        self.assertNotIn('newuser', html)


# ---------------------------------------------------------------------------
# Sign-out requires POST
# ---------------------------------------------------------------------------

class SignOutMethodTests(PlannixAuthTestCase):
    def test_signout_get_not_allowed(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('sign_out'))
        self.assertEqual(response.status_code, 405)

    def test_signout_post_works(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.post(reverse('sign_out'))
        self.assertNotIn('_auth_user_id', self.client.session)
        # After logout the user lands on Home — no stale dashboard shown.
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_signout_redirects_home_not_stale_dashboard(self):
        """After logout the follow-up page is Home and unauthenticated."""
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.post(reverse('sign_out'), follow=True)
        self.assertEqual(response.status_code, 200)
        # Home page no longer renders the authenticated account menu.
        self.assertNotContains(response, 'Settings')
        self.assertContains(response, 'Sign In')

    def test_signout_get_requires_login(self):
        response = self.client.get(reverse('sign_out'))
        self.assertEqual(response.status_code, 405)

    def test_base_renders_post_signout_form_not_get_link(self):
        """The visible Sign Out control submits the POST form — no GET link."""
        self.make_user()
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('index'))
        self.assertContains(response, f'action="{reverse("sign_out")}"')
        # The sign-out URLs appear only inside forms, never as a plain href.
        self.assertNotContains(response, f'href="{reverse("sign_out")}"')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

class LoginThrottlingTests(PlannixAuthTestCase):
    def _attempt_login(self, client, username='alice', password='wrongpass'):
        return client.post(reverse('sign_in'), {
            'username': username, 'password': password,
        }, follow=True)

    @patch('account_manager.views._LOGIN_MAX_ATTEMPTS', 3)
    def test_throttle_after_max_attempts(self):
        self.make_user()
        for _ in range(3):
            self._attempt_login(self.client)
        # 4th attempt should be throttled — even with correct password
        self.make_user(username='alice2')
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice2', 'password': 'testpass123',
        }, follow=True)
        # Django messages are injected as JSON into a JS block in the template,
        # where the apostrophe in "sign-in" is escaped as '.
        self.assertContains(response, 'Too many sign')
        self.assertContains(response, 'attempts. Please wait a few minutes')

    @patch('account_manager.views._LOGIN_MAX_ATTEMPTS', 3)
    @patch('account_manager.views._LOGIN_WINDOW', 0)
    def test_throttle_resets_after_window(self):
        """After the throttle window passes, login works again."""
        self.make_user()
        for _ in range(3):
            self._attempt_login(self.client)
        # Window=0 means attempts expire immediately
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Safe redirect validation
# ---------------------------------------------------------------------------

class SafeRedirectTests(PlannixAuthTestCase):
    def test_safe_next_param_works(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
            'next': '/events',
        })
        self.assertRedirects(response, '/events', fetch_redirect_response=False)

    def test_external_next_is_blocked(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
            'next': 'https://evil.com/phish',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_javascript_next_is_blocked(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
            'next': 'javascript:alert(1)',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)

    def test_empty_next_defaults_to_home(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
            'next': '',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)


# ---------------------------------------------------------------------------
# Password validation on signup
# ---------------------------------------------------------------------------

class PasswordValidationTests(PlannixAuthTestCase):
    def test_very_common_password_rejected(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'user1',
            'email': 'user1@example.com',
            'password': 'password',
            'confirm_password': 'password',
        }, follow=True)
        self.assertContains(response, 'too common')
        self.assertFalse(User.objects.filter(username='user1').exists())

    def test_entirely_numeric_password_rejected(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'user2',
            'email': 'user2@example.com',
            'password': '1234567890',
            'confirm_password': '1234567890',
        }, follow=True)
        self.assertContains(response, 'entirely numeric')
        self.assertFalse(User.objects.filter(username='user2').exists())

    def test_short_password_rejected(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'user3',
            'email': 'user3@example.com',
            'password': 'abc',
            'confirm_password': 'abc',
        }, follow=True)
        # Should have errors about length
        self.assertTrue(User.objects.filter(username='user3').count() == 0)


# ---------------------------------------------------------------------------
# CSRF enforcement on POST-only sign-out
# ---------------------------------------------------------------------------

class SignOutCSRFTests(PlannixAuthTestCase):
    def test_signout_post_without_csrf_rejected(self):
        csrf_client = Client(enforce_csrf_checks=True, SERVER_NAME='localhost')
        user = User.objects.create_user(
            username='csrfuser', email='csrf@example.com', password='testpass123')
        csrf_client.force_login(user)
        response = csrf_client.post(reverse('sign_out'))
        self.assertEqual(response.status_code, 403)

    def test_signout_post_with_csrf_works(self):
        csrf_client = Client(enforce_csrf_checks=True, SERVER_NAME='localhost')
        user = User.objects.create_user(
            username='csrfuser2', email='csrf2@example.com', password='testpass123')
        csrf_client.force_login(user)
        # Obtain a valid CSRF token from the cookie set on a GET request.
        csrf_client.get(reverse('index'))
        token = csrf_client.cookies['csrftoken'].value
        response = csrf_client.post(reverse('sign_out'), {
            'csrfmiddlewaretoken': token,
        })
        self.assertNotEqual(response.status_code, 403)
        self.assertNotIn('_auth_user_id', csrf_client.session)


# ---------------------------------------------------------------------------
# Canonical display identity: name + avatar initial
# ---------------------------------------------------------------------------

class AvatarInitialTests(PlannixAuthTestCase):
    """The avatar shows only the initial of the canonical display name and is
    never appended to the name itself."""

    def test_profile_avatar_initial_from_display_name(self):
        """When username differs from the display name, the avatar initial
        comes from the display name, not the username."""
        user = User.objects.create_user(
            username='doe', email='doe@example.com', password='testpass123',
            first_name='Doe', last_name='',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('profile'))
        self.assertContains(response, 'Doe')
        # Avatar circle shows just the single initial 'D'.
        self.assertContains(response, '>D<')
        # The username itself is shown only as the handle, not as the name.
        self.assertContains(response, '@doe')

    def test_profile_avatar_initial_falls_back_to_username(self):
        user = User.objects.create_user(
            username='jane', email='jane@example.com', password='testpass123',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('profile'))
        # No first/last name -> initial from username 'jane' -> 'J'.
        self.assertContains(response, '>J<')

    def test_dashboard_avatar_initial_and_name_are_consistent(self):
        user = User.objects.create_user(
            username='doe', email='doe@example.com', password='testpass123',
            first_name='Doe', last_name='',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('attendee_dashboard'))
        self.assertEqual(response.status_code, 200)
        # Name is shown as "Doe", avatar initial is a standalone "D".
        self.assertContains(response, 'Doe')
        self.assertContains(response, '>D<')


# ---------------------------------------------------------------------------
# Sign-out: no browser confirmation dialog
# ---------------------------------------------------------------------------

class LogoutNoConfirmTests(PlannixAuthTestCase):
    """Sign-out must submit the POST form immediately — no confirm() dialog,
    no onclick, no GET link."""

    def _render_auth_pages(self):
        user = self.make_user(username='alice')
        self.client.force_login(user)
        index = self.client.get(reverse('index')).content.decode()
        attendee = self.client.get(reverse('attendee_dashboard')).content.decode()
        return index, attendee

    def test_signout_form_has_no_confirm_attribute(self):
        index, attendee = self._render_auth_pages()
        for page in (index, attendee):
            self.assertNotIn('data-confirm', page)
            self.assertNotIn('window.confirm', page)
            self.assertNotIn('confirm(', page)
            self.assertNotIn('onclick=', page)

    def test_signout_remains_post_only_with_csrf(self):
        index, _ = self._render_auth_pages()
        # The control is still a POST form with a CSRF token...
        self.assertIn(f'action="{reverse("sign_out")}"', index)
        self.assertIn('name="csrfmiddlewaretoken"', index)
        # ...and never a GET link.
        self.assertNotIn(f'href="{reverse("sign_out")}"', index)


# ---------------------------------------------------------------------------
# Trusted admin: Django superuser authenticates through the normal sign-in
# ---------------------------------------------------------------------------

class AdminLoginFlowTests(PlannixAuthTestCase):
    def test_superuser_authenticates_via_normal_signin(self):
        User.objects.create_superuser(
            username='root', email='root@example.com', password='rootpass123')
        response = self.client.post(reverse('sign_in'), {
            'username': 'root', 'password': 'rootpass123',
        })
        self.assertRedirects(response, reverse('index'), fetch_redirect_response=False)
        self.assertIn('_auth_user_id', self.client.session)

    def test_superuser_receives_admin_role(self):
        User.objects.create_superuser(
            username='root', email='root@example.com', password='rootpass123')
        self.client.post(reverse('sign_in'), {
            'username': 'root', 'password': 'rootpass123',
        })
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        # The admin dashboard nav is shown because the server sees role=admin.
        self.assertContains(response, reverse('admin_dashboard'))

    def test_superuser_accesses_admin_dashboard_via_normal_login(self):
        User.objects.create_superuser(
            username='root', email='root@example.com', password='rootpass123')
        self.client.post(reverse('sign_in'), {
            'username': 'root', 'password': 'rootpass123',
        })
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_ordinary_user_cannot_access_admin_dashboard(self):
        self.make_user()
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('admin_dashboard'))
        self.assertNotEqual(response.status_code, 200)


# ---------------------------------------------------------------------------
# Role spoofing is rejected: role is always derived server-side
# ---------------------------------------------------------------------------

class RoleSpoofingTests(PlannixAuthTestCase):
    def test_signin_role_param_does_not_elevate(self):
        """POSTing a role/user_type alongside credentials grants nothing."""
        self.make_user()
        self.client.post(reverse('sign_in'), {
            'username': 'alice', 'password': 'testpass123',
            'role': 'admin', 'user_type': 'admin',
        })
        response = self.client.get(reverse('admin_dashboard'))
        # Ordinary attendee cannot reach the admin dashboard.
        self.assertNotEqual(response.status_code, 200)

    def test_spoofed_query_param_does_not_grant_admin(self):
        """GET ?role=admin must not make a non-superuser look like an admin."""
        self.make_user()
        self.client.force_login(User.objects.get(username='alice'))
        response = self.client.get(reverse('admin_dashboard') + '?role=admin')
        self.assertNotEqual(response.status_code, 200)

    def test_spoofing_never_creates_superuser(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'sneaky',
            'email': 'sneaky@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
            'user_type': 'admin',
            'role': 'admin',
        })
        user = User.objects.filter(username='sneaky').first()
        self.assertIsNotNone(user)
        # Even with spoofed admin params, the account is a plain attendee.
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)
# ---------------------------------------------------------------------------
# Password reset (Part C) — no enumeration, expiring single-use token, validation
# ---------------------------------------------------------------------------

@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class PasswordResetTests(PlannixAuthTestCase):
    def setUp(self):
        super().setUp()
        self.user = self.make_user()

    def test_password_reset_page_renders(self):
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)

    def test_password_reset_form_has_csrf(self):
        response = self.client.get(reverse('password_reset'))
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_valid_email_requests_reset(self):
        response = self.client.post(reverse('password_reset'), {
            'email': 'alice@example.com',
        })
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ['alice@example.com'])
        self.assertIn('/reset/', mail.outbox[0].body)

    def test_unknown_email_no_enumeration(self):
        # Same "done" page and no user-language difference for unknown emails.
        response = self.client.post(reverse('password_reset'), {
            'email': 'nobody@example.com',
        })
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 0)

    def test_done_page_uses_no_enumeration_message(self):
        response = self.client.get(reverse('password_reset_done'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'If an account exists')
        self.assertContains(response, 'email')

    def _reset_email_url(self):
        """Extract the real reset link from the email Django just sent.

        Deleting the emailed token and building a URL is the only correct way
        to exercise the single-use token Django generated (regenerating one
        with make_token would produce a different, unusable link).
        """
        from urllib.parse import urlparse
        self.client.post(reverse('password_reset'), {'email': self.user.email})
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        link = next(line.strip() for line in body.splitlines()
                    if line.strip().startswith('http'))
        return urlparse(link).path

    def _reset_form_url(self):
        """Return the password-reset form URL (/reset/<uid>/set-password/).

        Django 6.1 redirects a valid /reset/<uid>/<token>/ request to
        /reset/<uid>/set-password/ (so the token never appears in the Referer
        header); the form then lives at that token-less URL.
        """
        confirm = self._reset_email_url()
        response = self.client.get(confirm, follow=True)
        return response.redirect_chain[-1][0]

    def test_token_works_once(self):
        url = self._reset_form_url()
        response = self.client.post(url, {
            'new_password1': 'brandnewpass321',
            'new_password2': 'brandnewpass321',
        })
        self.assertRedirects(response, reverse('password_reset_complete'))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('brandnewpass321'))
        # The token is single-use — reusing the (now stale) token is rejected.
        self.client.post(url, {
            'new_password1': 'anotherpass321',
            'new_password2': 'anotherpass321',
        })
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('anotherpass321'))

    def test_invalid_token_rejected(self):
        url = reverse('password_reset_confirm', args=[
            'not-a-valid-uid', 'not-a-valid-token'])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'invalid')

    def test_weak_password_rejected_on_confirm(self):
        url = self._reset_form_url()
        self.client.post(url, {
            'new_password1': 'short',
            'new_password2': 'short',
        })
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('testpass123'))

    def test_password_reset_confirm_has_csrf(self):
        # GET the token URL (follows to the set-password form), then assert the
        # form carries a CSRF token.
        confirm = self._reset_email_url()
        response = self.client.get(confirm, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'csrfmiddlewaretoken')

    def test_complete_page_renders(self):
        response = self.client.get(reverse('password_reset_complete'))
        self.assertEqual(response.status_code, 200)