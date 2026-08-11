from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.shortcuts import redirect, render

from .decorators import unauthenticated_user

PLANNIX_SITE_URL = 'https://plannix.example.com'


@unauthenticated_user
def sign_up(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if not username or not email or not password:
            messages.error(request, 'All fields are required.')
            return redirect('sign_up')

        if User.objects.filter(username__iexact=username).exists():
            messages.error(request, 'That username is already taken. Please choose another.')
            return redirect('sign_up')

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, 'An account with that email already exists.')
            return redirect('sign_up')

        if password != confirm_password:
            messages.error(request, 'Passwords do not match.')
            return redirect('sign_up')

        try:
            user_data = User.objects.create_user(username=username, email=email, password=password)
        except Exception:
            messages.error(request, 'Unable to create your account right now. Please try again.')
            return redirect('sign_up')

        subject = 'Welcome to Plannix'
        message = (
            f'Dear {username},\n\n'
            'You have successfully created your Plannix account.\n'
            'Please keep this email for your records and do not forward or share it with anyone.\n\n'
            'You can now sign in and start planning your perfect event:\n'
            f'{PLANNIX_SITE_URL}\n\n'
            'Best Regards,\nPlannix Team.'
        )
        send_mail(subject, message, settings.EMAIL_HOST_USER, [email], fail_silently=True)

        messages.success(request, 'Account created successfully. Please sign in.')
        return redirect('sign_in')
    return render(request, 'sign-up.html')


@unauthenticated_user
def sign_in(request):
    if request.method == 'POST':
        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user_auth = authenticate(request, username=username, password=password)
        if user_auth is not None:
            login(request, user_auth)
            messages.success(request, f'Welcome back, {user_auth.username}!')
            return redirect('dashboard')
        messages.error(request, 'Invalid username or password.')
        return redirect('sign_in')
    return render(request, 'sign-in.html')


@login_required(login_url='sign_in')
def sign_out(request):
    logout(request)
    messages.success(request, 'You have been signed out successfully.')
    return redirect('sign_in')


@login_required(login_url='sign_in')
def profile(request):
    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()

        if not email:
            messages.error(request, 'Email address is required.')
            return redirect('profile')

        if User.objects.filter(email__iexact=email).exclude(pk=request.user.pk).exists():
            messages.error(request, 'That email is already used by another account.')
            return redirect('profile')

        user = request.user
        user.first_name = first_name[:150]
        user.last_name = last_name[:150]
        user.email = email
        user.save(update_fields=['first_name', 'last_name', 'email'])

        messages.success(request, 'Your profile has been updated.')
        return redirect('profile')

    return render(request, 'profile.html')


@login_required(login_url='sign_in')
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)  # keep the user signed in
            messages.success(request, 'Your password has been changed.')
            return redirect('profile')
        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return redirect('change_password')
    return render(request, 'change-password.html', {'form': PasswordChangeForm(request.user)})
