"""Test suite for the Plannix account manager (authentication & profile)."""
from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse


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

    def test_signup_missing_fields(self):
        response = self.client.post(reverse('sign_up'), {
            'username': '',
            'email': 'new@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'required')
        self.assertEqual(User.objects.count(), 0)

    def test_signup_duplicate_username(self):
        self.make_user()
        response = self.client.post(reverse('sign_up'), {
            'username': 'alice',
            'email': 'other@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'already taken')
        self.assertEqual(User.objects.count(), 1)

    def test_signup_duplicate_email(self):
        self.make_user()
        response = self.client.post(reverse('sign_up'), {
            'username': 'bob',
            'email': 'alice@example.com',
            'password': 'securepass123',
            'confirm_password': 'securepass123',
        }, follow=True)
        self.assertContains(response, 'already exists')
        self.assertEqual(User.objects.count(), 1)

    def test_signup_password_mismatch(self):
        response = self.client.post(reverse('sign_up'), {
            'username': 'bob',
            'email': 'bob@example.com',
            'password': 'securepass123',
            'confirm_password': 'different123',
        }, follow=True)
        self.assertContains(response, 'do not match')
        self.assertEqual(User.objects.count(), 0)

    def test_authenticated_user_redirected_away(self):
        user = self.make_user()
        self.client.force_login(user)
        response = self.client.get(reverse('sign_up'))
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)


class SignInTests(PlannixAuthTestCase):
    def test_signin_page_renders(self):
        response = self.client.get(reverse('sign_in'))
        self.assertEqual(response.status_code, 200)

    def test_signin_success_redirects_to_dashboard(self):
        self.make_user()
        response = self.client.post(reverse('sign_in'), {
            'username': 'alice',
            'password': 'testpass123',
        })
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)

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
        self.assertRedirects(response, reverse('dashboard'), fetch_redirect_response=False)


class SignOutTests(PlannixAuthTestCase):
    def test_signout_logs_out(self):
        user = self.make_user()
        self.client.force_login(user)
        self.client.post(reverse('sign_out'), follow=True)
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_signout_requires_login(self):
        response = self.client.get(reverse('sign_out'))
        self.assertIn(reverse('sign_in'), response.url)


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
