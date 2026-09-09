import time

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import Group, User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from Plannix.emails import send_registration_notice

from .decorators import admin_required, organizer_required, unauthenticated_user
from .models import Organization
from .services import (
    approve_organization as approve_org_svc,
    reject_organization as reject_org_svc,
    submit_organization as submit_org_svc,
)

# ---------------------------------------------------------------------------
# Simple in-memory login throttle (per-IP, no external dependencies)
# ---------------------------------------------------------------------------
_LOGIN_ATTEMPTS: dict[str, list[float]] = {}
_LOGIN_MAX_ATTEMPTS = 10
_LOGIN_WINDOW = 300  # 5 minutes


def _is_login_throttled(ip: str) -> bool:
    """Return True if this IP has exceeded the login attempt limit."""
    now = time.time()
    attempts = _LOGIN_ATTEMPTS.get(ip, [])
    attempts = [t for t in attempts if now - t < _LOGIN_WINDOW]
    _LOGIN_ATTEMPTS[ip] = attempts
    return len(attempts) >= _LOGIN_MAX_ATTEMPTS


def _record_login_attempt(ip: str) -> None:
    """Record a failed login attempt for the given IP."""
    _LOGIN_ATTEMPTS.setdefault(ip, []).append(time.time())


@unauthenticated_user
def sign_up(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')
        # Role selection: only 'attendee' or 'organizer' allowed from the form.
        # Never trust 'admin' from the browser.
        user_type = request.POST.get('user_type', 'attendee')
        if user_type not in ('attendee', 'organizer'):
            user_type = 'attendee'

        if not username or not email or not password:
            messages.error(request, 'All fields are required.')
            return redirect('sign_up')

        if len(username) < 3:
            messages.error(request, 'Username must be at least 3 characters.')
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

        # Server-side password validation using Django's AUTH_PASSWORD_VALIDATORS
        try:
            validate_password(password)
        except ValidationError as e:
            for error in e.messages:
                messages.error(request, error)
            return redirect('sign_up')

        try:
            first_name = request.POST.get('first_name', '').strip()[:30]
            last_name = request.POST.get('last_name', '').strip()[:30]
            user_data = User.objects.create_user(username=username, email=email, password=password)
            # Store the user's chosen display name (optional, uses the standard
            # User.first_name/last_name fields — no separate display-name system).
            user_data.first_name = first_name
            user_data.last_name = last_name
            user_data.save(update_fields=['first_name', 'last_name'])
            # Assign the appropriate group based on validated role selection
            if user_type == 'organizer':
                group, _ = Group.objects.get_or_create(name='EventOrganizer')
                user_data.groups.add(group)
                # Create an OrganizerProfile for new organizers
                from .models import OrganizerProfile
                OrganizerProfile.objects.get_or_create(user=user_data)
                # Seed the initial Organization state (pending, unsubmitted) so
                # the organizer has a marketplace entity from day one. It stays
                # out of the admin approval queue until the organizer submits it
                # via the existing my_organization/submit_organization flow.
                Organization.objects.get_or_create(owner=user_data)
            else:
                group, _ = Group.objects.get_or_create(name='Attendee')
                user_data.groups.add(group)
        except Exception:
            messages.error(request, 'Unable to create your account right now. Please try again.')
            return redirect('sign_up')

        role_label = 'Event Organizer' if user_type == 'organizer' else 'User'
        send_registration_notice(email, username, role_label)

        messages.success(request, 'Account created successfully. Please sign in.')
        return redirect('sign_in')
    return render(request, 'sign-up.html')


@unauthenticated_user
def sign_in(request):
    if request.method == 'POST':
        client_ip = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip() or request.META.get('REMOTE_ADDR', '')

        if _is_login_throttled(client_ip):
            messages.error(request, 'Too many sign-in attempts. Please wait a few minutes and try again.')
            return redirect('sign_in')

        username = request.POST.get('username', '')
        password = request.POST.get('password', '')
        user_auth = authenticate(request, username=username, password=password)
        if user_auth is not None:
            # Session fixation prevention: rotate the session key on login
            request.session.cycle_key()
            login(request, user_auth)
            display_name = user_auth.get_full_name() or user_auth.username
            messages.success(request, f'Welcome back, {display_name}!')
            # Follow a safe "next" target when present, else land on the Home page.
            # url_has_allowed_host_and_scheme blocks open redirects to external hosts.
            next_url = request.POST.get('next') or request.GET.get('next')
            if next_url and url_has_allowed_host_and_scheme(next_url, request.get_host()):
                return redirect(next_url)
            return redirect('index')
        # Record failed attempt for throttling
        _record_login_attempt(client_ip)
        messages.error(request, 'Invalid username or password.')
        return redirect('sign_in')
    return render(request, 'sign-in.html')


@require_POST
@login_required(login_url='sign_in')
def sign_out(request):
    """Sign out via POST only (requires CSRF token for safety).

    After logout the user is sent to the public Home page so no stale
    authenticated dashboard lingers on the session.
    """
    logout(request)
    messages.success(request, 'You have been signed out successfully.')
    return redirect('index')


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


# ---------------------------------------------------------------------------
# Organization — the marketplace business entity
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def my_organization(request):
    """The organizer's business workspace: create/edit their marketplace
    Organization and submit it for admin approval."""
    organization = getattr(request.user, 'organization', None)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        contact_number = request.POST.get('contact_number', '').strip()
        email = request.POST.get('email', '').strip()
        website = request.POST.get('website', '').strip()
        description = request.POST.get('description', '').strip()

        if not name:
            messages.error(request, 'Organization name is required.')
            return redirect('my_organization')

        if organization is None:
            organization = Organization(owner=request.user)

        organization.name = name
        organization.contact_number = contact_number[:15]
        organization.email = email
        organization.website = website
        organization.description = description

        # Any substantive edit invalidates a prior decision — reset to a
        # fresh, unsubmitted draft so the organizer explicitly resubmits.
        organization.status = 'pending'
        organization.submitted_at = None
        organization.approved_at = None
        organization.rejection_reason = ''
        organization.review_notes = ''
        organization.save()
        messages.success(request, 'Organization details saved. Submit for review when ready.')
        return redirect('my_organization')

    return render(request, 'my_organization.html', {
        'organization': organization,
    })


@login_required(login_url='sign_in')
@organizer_required
def submit_organization(request):
    """Submit the organizer's Organization for admin review."""
    organization = getattr(request.user, 'organization', None)
    if request.method != 'POST':
        return redirect('my_organization')

    if organization is None:
        messages.error(request, 'Create your organization details first.')
        return redirect('my_organization')

    if organization.status == 'approved':
        messages.info(request, 'Your organization is already approved.')
        return redirect('my_organization')

    try:
        submit_org_svc(organization)
        messages.success(request, 'Your organization has been submitted for review.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('my_organization')


@login_required(login_url='sign_in')
@admin_required
def manage_organizations(request):
    """Admin overview of every marketplace Organization."""
    from django.db.models import Count

    from events.models import EventBooking

    status_filter = request.GET.get('status', '').strip()
    orgs_qs = Organization.objects.select_related('owner').order_by('-created_at')
    if status_filter in ('pending', 'approved', 'rejected', 'suspended'):
        orgs_qs = orgs_qs.filter(status=status_filter)

    # One aggregate for event counts, one for booking counts.
    orgs = list(orgs_qs)
    event_map = dict(
        orgs_qs.values_list('pk').annotate(total=Count('events')).values_list('pk', 'total')
    )
    booking_rows = (
        EventBooking.objects.filter(event__organization__isnull=False)
        .values('event__organization')
        .annotate(total=Count('id'))
    )
    booking_map = {row['event__organization']: row['total'] for row in booking_rows}

    organizations = [
        {
            'organization': org,
            'event_count': event_map.get(org.pk, 0),
            'booking_count': booking_map.get(org.pk, 0),
        }
        for org in orgs
    ]

    return render(request, 'manage_organizations.html', {
        'organizations': organizations,
        'active_status': status_filter,
        'statuses': ('pending', 'approved', 'rejected', 'suspended'),
    })


@login_required(login_url='sign_in')
@admin_required
def approve_organization(request, pk):
    """Approve a submitted Organization (pending -> approved)."""
    org = get_object_or_404(
        Organization.objects.filter(status='pending', submitted_at__isnull=False),
        pk=pk,
    )
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        try:
            approve_org_svc(org, request.user, notes)
            messages.success(request, f'"{org.name}" has been approved.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def reject_organization(request, pk):
    """Reject a submitted Organization (pending -> rejected) with a reason."""
    org = get_object_or_404(
        Organization.objects.filter(status='pending', submitted_at__isnull=False),
        pk=pk,
    )
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'A rejection reason is required.')
            return redirect('approval_queue')
        try:
            reject_org_svc(org, request.user, reason)
            messages.success(request, f'"{org.name}" has been rejected.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')
