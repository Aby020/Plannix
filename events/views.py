"""Views for the Plannix events module.

Includes the public event catalogue, booking flow, role-based dashboards,
organizer management views, and admin lifecycle-management views.
"""
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, User
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from account_manager.decorators import admin_required, get_role, organizer_required
from account_manager.identity import display_name as _display_name
from account_manager.models import Organization
from themes.models import Feedback

from Plannix.emails import (
    send_advance_confirmation,
    send_booking_confirmation,
    send_booking_status_change,
    send_organizer_booking_notification,
)
from .booking import create_booking
from .forms import EventBookingForm, EventForm
from .models import BookingPayment, Event, EventAuditLog, EventBooking, EventCategory
from .payments import (
    PaymentError,
    create_order,
    handle_webhook,
    verify_payment_signature,
)
from .pulse import dashboard_pulse, event_pulse
from .services import (
    approve,
    approve_and_go_live,
    cancel,
    complete,
    edit_sets_draft,
    go_live,
    publish,
    publish_and_go_live,
    publish_live,
    reject,
    submit,
)

BOOKING_STATUSES = ['pending', 'confirmed', 'completed', 'cancelled']


# ---------------------------------------------------------------------------
# Public catalogue (LIVE events only)
# ---------------------------------------------------------------------------

def events(request):
    """Browse all LIVE event packages (public catalogue)."""
    category_slug = request.GET.get('category', '').strip()
    queryset = Event.objects.filter(status='live', is_active=True).order_by('-created_at')
    if category_slug:
        queryset = queryset.filter(category__slug=category_slug)
    categories = EventCategory.objects.filter(is_active=True).order_by('sort_order', 'name')
    active_category_name = ''
    if category_slug:
        active_category_name = categories.filter(slug=category_slug).values_list('name', flat=True).first() or category_slug
    return render(request, 'events.html', {
        'events': queryset,
        'categories': categories,
        'active_category': category_slug,
        'active_category_name': active_category_name,
    })


def readmore(request, pk):
    """Show full details of one LIVE event (package detail page)."""
    event_detail = get_object_or_404(Event, pk=pk, status='live')

    # Provider/organizer behind this package, when a profile exists.
    organizer = getattr(event_detail.owner, 'organizer_profile', None)
    provider_name = 'Plannix Provider'
    if organizer is not None:
        provider_name = organizer.business_name or _display_name(event_detail.owner)

    # Approved public reviews + live pulse metrics.
    reviews = event_detail.reviews.filter(moderation_status='approved').order_by('-created_at')
    pulse = event_pulse(event_detail)

    return render(request, 'readmore.html', {
        'event_detail': event_detail,
        'organizer': organizer,
        'provider_name': provider_name,
        'reviews': reviews,
        'pulse': pulse,
    })


def searching_events(request):
    """Keyword search over LIVE events (title, description, location, category name, price)."""
    search_query = request.GET.get('q') or request.POST.get('search_query') or ''
    search_query = search_query.strip()
    if not search_query:
        messages.error(request, 'Please enter a search term.')
        return render(request, 'search.html', {'events': [], 'search_query': search_query})

    q = (
        Q(title__icontains=search_query)
        | Q(description__icontains=search_query)
        | Q(location__icontains=search_query)
        | Q(category__name__icontains=search_query)
    )
    # Price is a numeric field: ``icontains`` (ILIKE) is invalid on PostgreSQL,
    # so only match the numeric price when the query is actually a number.
    if search_query.isdigit():
        q = q | Q(price=search_query)
    results = (
        Event.objects.filter(status='live', is_active=True)
        .filter(q)
        .distinct()
        .order_by('-created_at')
    )

    if not results:
        messages.error(request, f'No events found for "{search_query}".')
    return render(request, 'search.html', {'events': results, 'search_query': search_query})


# ---------------------------------------------------------------------------
# Booking flow
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def selected_event(request, pk):
    """Open the booking form for a specific LIVE event."""
    event = get_object_or_404(Event, pk=pk, status='live')
    return render(request, 'event-booking-form.html', {
        'event': event,
        'today_date': date.today().isoformat(),
    })


@login_required(login_url='sign_in')
def event_booking(request):
    """Handle a new booking submission — transactional and safe."""
    if request.method != 'POST':
        return render(request, 'event-booking-form.html', {'today_date': date.today().isoformat()})

    event_id = request.POST.get('event_id')
    event = None
    if event_id:
        event = Event.objects.filter(pk=event_id, status='live').first()

    def booking_error(message):
        messages.error(request, message)
        if event is not None:
            return redirect('selected_event', pk=event.pk)
        return redirect('events')

    name = request.POST.get('name', '').strip()
    email = request.POST.get('email', '').strip()
    number = request.POST.get('number', '').strip()
    event_location = request.POST.get('event_location', '').strip()
    event_date_str = request.POST.get('date', '').strip()

    # Validate required fields
    if not all([name, email, number, event_date_str]):
        return booking_error('Please complete all the required fields.')

    if len(number) != 10 or not number.isdigit():
        return booking_error('Please enter a valid 10-digit mobile number.')

    if event is None:
        return booking_error('Please select a valid event to book.')

    try:
        from datetime import datetime as dt
        selected_date = dt.strptime(event_date_str, '%Y-%m-%d').date()
    except ValueError:
        return booking_error('Please choose a valid booking date.')

    # Create booking through the transactional service
    try:
        booking = create_booking(
            event=event,
            attendee=request.user,
            name=name,
            email=email,
            number=number,
            event_date=selected_date,
            event_location=event_location or event.location,
        )
    except ValueError as e:
        return booking_error(str(e))

    send_booking_confirmation(booking)
    send_organizer_booking_notification(booking)
    messages.success(
        request,
        f'Your booking request was received! A confirmation email has been '
        f'sent to {booking.email}.',
    )
    return redirect(f"{reverse('success')}?booking={booking.pk}")


# ---------------------------------------------------------------------------
# Role-based dashboards
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def dashboard(request):
    """Route the user to the dashboard matching their role."""
    role = get_role(request.user)
    if role == 'admin':
        return redirect('admin_dashboard')
    if role == 'organizer':
        return redirect('organizer_dashboard')
    return redirect('attendee_dashboard')


@login_required(login_url='sign_in')
def attendee_dashboard(request):
    """Premium attendee dashboard: 'Plan and manage my occasion.'

    Kept minimal: welcome, discover action, one active booking, and bookings list.
    No decorative stat cards, no generic activity feed.
    """
    bookings = (
        request.user.bookings
        .select_related('event', 'event__category')
        .order_by('-created_at')
    )
    # Materialize once to avoid re-querying for the count, the slice and the
    # upcoming scan below.
    bookings_list = list(bookings[:10])
    today = date.today()

    # Next upcoming booking (the one the attendee most needs to see)
    upcoming = [
        b for b in bookings_list
        if b.event_date and b.event_date >= today and b.status not in ('cancelled', 'completed')
    ]
    active_booking = upcoming[0] if upcoming else None
    has_active = active_booking is not None

    return render(request, 'customer_dashboard.html', {
        'active_booking': active_booking,
        'has_active_booking': has_active,
        'upcoming_count': len(upcoming),
        'bookings': bookings_list,
        'total_bookings': len(bookings_list),
    })


@login_required(login_url='sign_in')
@organizer_required
def organizer_dashboard(request):
    """Premium organizer dashboard: 'Manage my organization and event packages.'

    Primary focus: org status, packages, bookings requiring attention.
    """
    organization = getattr(request.user, 'organization', None)
    own_events = Event.objects.filter(owner=request.user).order_by('-created_at')
    events_with_pulse = dashboard_pulse(own_events[:10])

    # Aggregate pending + total bookings in one pass.
    booking_counts = (
        EventBooking.objects.filter(event__owner=request.user)
        .values('status')
        .annotate(total=Count('id'))
    )
    total_bookings = 0
    pending_bookings = 0
    for row in booking_counts:
        total_bookings += row['total']
        if row['status'] == 'pending':
            pending_bookings = row['total']

    # Recent bookings requiring attention
    recent_bookings = (
        EventBooking.objects.filter(event__owner=request.user)
        .select_related('event')
        .order_by('-created_at')[:5]
    )

    return render(request, 'staff_dashboard.html', {
        'organization': organization,
        'events_with_pulse': events_with_pulse,
        'total_events': own_events.count(),
        'total_bookings': total_bookings,
        'pending_bookings': pending_bookings,
        'recent_bookings': recent_bookings,
    })


@login_required(login_url='sign_in')
@admin_required
def admin_dashboard(request):
    """Premium admin dashboard: 'Moderate and operate the Plannix marketplace.'

    Primary focus: organizations awaiting approval. Event packages no longer
    require admin review (Organization approval is the only gate), so the
    attention panel counts organizations only.
    """
    pending_orgs = Organization.objects.filter(
        status='pending', submitted_at__isnull=False,
    ).select_related('owner').order_by('submitted_at')

    # Recent bookings for context
    recent_bookings = EventBooking.objects.all().order_by('-created_at')[:6]

    # Platform summary numbers (only real data)
    total_users = User.objects.filter(is_active=True).count()
    total_organizations = Organization.objects.count()
    total_events = Event.objects.count()

    # Pending review items count for the attention panel (single query).
    total_pending = pending_orgs.count()

    return render(request, 'admin_dashboard.html', {
        'pending_organizations': pending_orgs,
        'pending_organization_count': total_pending,
        'total_pending': total_pending,
        'total_users': total_users,
        'total_organizations': total_organizations,
        'total_events': total_events,
        'recent_bookings': recent_bookings,
    })


# ---------------------------------------------------------------------------
# Customer bookings (kept as-is for URL compatibility)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def my_bookings(request):
    """List the current user's bookings.

    The customer booking flow ends at booking confirmation — there is no
    online advance payment. Payment is arranged with the organizer directly.
    """
    bookings = (
        request.user.bookings
        .select_related('event', 'event__owner', 'event__organization')
        .order_by('-created_at')
    )
    for booking in bookings:
        org = getattr(booking.event, 'organization', None)
        booking.provider_name = (
            org.name if org and org.name else _display_name(booking.event.owner)
        )
    return render(request, 'my_bookings.html', {'bookings': bookings})


@login_required(login_url='sign_in')
def cancel_booking(request, pk):
    """Let a customer cancel one of their own bookings."""
    booking = get_object_or_404(EventBooking, pk=pk, attendee=request.user)
    if request.method == 'POST':
        if booking.status in ('completed', 'cancelled'):
            messages.error(request, 'This booking cannot be cancelled.')
        else:
            booking.status = 'cancelled'
            booking.save(update_fields=['status'])
            send_booking_status_change(booking)
            messages.success(request, 'Your booking has been cancelled.')
        return redirect('my_bookings')
    messages.error(request, 'Invalid request.')
    return redirect('my_bookings')


# ---------------------------------------------------------------------------
# Management — events (legacy admin/staff route, kept for compatibility)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def manage_events(request):
    """List all events (admin sees all, organizer sees own)."""
    role = get_role(request.user)
    if role == 'admin':
        events_qs = Event.objects.all().order_by('-created_at')
    else:
        events_qs = Event.objects.filter(owner=request.user).order_by('-created_at')
    organization = getattr(request.user, 'organization', None)
    return render(request, 'manage_events.html', {
        'events': events_qs,
        'organization': organization,
    })


# ---------------------------------------------------------------------------
# Organizer views (organizer_required + ownership-scoped)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def my_events(request):
    """List events owned by the current organizer."""
    events_qs = Event.objects.filter(owner=request.user).order_by('-created_at')
    organization = getattr(request.user, 'organization', None)
    return render(request, 'manage_events.html', {
        'events': events_qs,
        'organization': organization,
    })


@login_required(login_url='sign_in')
@organizer_required
def create_event(request):
    """Create a new event package.

    Organization approval is the only gate: an approved organizer's package is
    created live and bookable immediately; an organizer without an approved
    Organization cannot create packages.
    """
    org = getattr(request.user, 'organization', None)
    if org is None or not org.is_approved:
        messages.warning(
            request,
            'Your Organization must be approved before you can create event '
            'packages. Set up and submit your organization first.',
        )
        return redirect('my_organization')

    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES)
        if form.is_valid():
            event = form.save(commit=False)
            event.owner = request.user
            event.organization = org
            event.status = 'live'
            event.save()
            messages.success(request, 'Event created and is now live for booking.')
            return redirect('my_events')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = EventForm()
    return render(request, 'event_form.html', {'form': form, 'event': None})


@login_required(login_url='sign_in')
@organizer_required
def edit_event(request, pk):
    """Edit an event — ownership-scoped; admins can edit any event."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    if request.method == 'POST':
        form = EventForm(request.POST, request.FILES, instance=event)
        if form.is_valid():
            edited_event = form.save()
            # If event was approved/published/live, reset to draft
            edit_sets_draft(edited_event)
            messages.success(request, 'Event updated successfully.')
            if get_role(request.user) == 'admin':
                return redirect('manage_events')
            return redirect('my_events')
        messages.error(request, 'Please correct the errors below.')
    else:
        form = EventForm(instance=event)
    return render(request, 'event_form.html', {'form': form, 'event': event})


@login_required(login_url='sign_in')
@organizer_required
def submit_event(request, pk):
    """Publish a draft event package live — ownership-scoped.

    Organization approval is the only gate: an approved organizer takes a
    finished draft package live directly, with no second admin review. An
    organizer without an approved Organization cannot publish.
    """
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    if request.method != 'POST':
        return redirect('my_events')

    org = getattr(request.user, 'organization', None)
    if org is None or not org.is_approved:
        messages.warning(
            request,
            'Your Organization must be approved before you can publish event '
            'packages. Set up and submit your organization first.',
        )
        return redirect('my_organization')

    try:
        if event.organization_id != org.pk:
            event.organization = org
            event.save(update_fields=['organization', 'updated_at'])
        publish_live(event, request.user)
        messages.success(request, 'Event is now live and bookable.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('my_events')


@login_required(login_url='sign_in')
@organizer_required
def event_approval_status(request, pk):
    """Show event status and audit logs — ownership-scoped; admins see all."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    audit_logs = EventAuditLog.objects.filter(event=event).order_by('-created_at')
    return render(request, 'event_approval_status.html', {
        'event': event,
        'audit_logs': audit_logs,
    })


@login_required(login_url='sign_in')
@organizer_required
def event_registrations(request, pk):
    """Show bookings for a specific event — ownership-scoped; admins see all."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
        bookings = EventBooking.objects.filter(event=event).order_by('-created_at')
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
        bookings = EventBooking.objects.filter(
            event=event,
            event__owner=request.user,
        ).order_by('-created_at')
    return render(request, 'event_registrations.html', {
        'event': event,
        'bookings': bookings,
    })


@login_required(login_url='sign_in')
@organizer_required
def event_pulse_view(request, pk):
    """Return JSON pulse metrics for an event — ownership-scoped; admins see all."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    pulse = event_pulse(event)
    return JsonResponse(pulse)


@login_required(login_url='sign_in')
@organizer_required
def cancel_event(request, pk):
    """Cancel a live/published event — ownership-scoped; admins cancel any event."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    if request.method != 'POST':
        return redirect('my_events')
    reason = request.POST.get('reason', '')
    try:
        cancel(event, request.user, reason)
        messages.success(request, 'Event has been cancelled.')
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('my_events')


# ---------------------------------------------------------------------------
# Management — bookings (admin/org can view)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def manage_bookings(request):
    role = get_role(request.user)
    bookings = EventBooking.objects.select_related('event', 'event__owner')
    if role == 'admin':
        bookings = bookings.all()
    else:
        bookings = bookings.filter(event__owner=request.user)
    bookings = bookings.order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter in BOOKING_STATUSES:
        bookings = bookings.filter(status=status_filter)
    return render(request, 'manage_bookings.html', {
        'bookings': bookings,
        'active_status': status_filter,
        'statuses': BOOKING_STATUSES,
    })


def _manageable_booking(request, pk):
    """Return a booking the current user may manage, else 404 (IDOR guard).

    Admins manage all bookings; organizers are scoped to their own events'
    bookings so a guessed pk for another organizer's event returns 404.
    """
    qs = EventBooking.objects.all()
    if get_role(request.user) != 'admin':
        qs = qs.filter(event__owner=request.user)
    return get_object_or_404(qs, pk=pk)


@login_required(login_url='sign_in')
@organizer_required
def update_booking_status(request, pk):
    booking = _manageable_booking(request, pk)
    if request.method == 'POST':
        new_status = request.POST.get('status', '')
        if new_status in BOOKING_STATUSES:
            booking.status = new_status
            booking.save(update_fields=['status'])
            send_booking_status_change(booking)
            messages.success(request, f'Booking marked as {new_status}.')
    return redirect('manage_bookings')


@login_required(login_url='sign_in')
@organizer_required
def delete_booking(request, pk):
    booking = _manageable_booking(request, pk)
    if request.method == 'POST':
        booking.delete()
        messages.success(request, 'Booking deleted.')
    return redirect('manage_bookings')


# ---------------------------------------------------------------------------
# Management — feedback (kept for compatibility)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def manage_feedback(request):
    feedback = Feedback.objects.all().order_by('-created_at')
    return render(request, 'manage_feedback.html', {'feedback_list': feedback})


@login_required(login_url='sign_in')
@organizer_required
def delete_feedback(request, pk):
    feedback = get_object_or_404(Feedback, pk=pk)
    if request.method == 'POST':
        feedback.delete()
        messages.success(request, 'Feedback deleted.')
    return redirect('manage_feedback')


# ---------------------------------------------------------------------------
# Management — users (admin only)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@admin_required
def manage_users(request):
    # Prefetch groups so computing each user's role is a single query, not one
    # per user (N+1).
    users = User.objects.all().prefetch_related('groups').order_by('-date_joined')
    users_with_roles = []
    for user in users:
        if user.is_superuser:
            role = 'admin'
        else:
            names = {g.name for g in user.groups.all()}
            if 'Admin' in names:
                role = 'admin'
            elif 'EventOrganizer' in names:
                role = 'organizer'
            else:
                role = 'attendee'
        users_with_roles.append((user, role))
    return render(request, 'manage_users.html', {
        'users_with_roles': users_with_roles,
    })


@login_required(login_url='sign_in')
@admin_required
def toggle_user_active(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if user == request.user or user.is_superuser:
            messages.error(request, 'You cannot deactivate yourself or a superuser.')
        else:
            user.is_active = not user.is_active
            user.save(update_fields=['is_active'])
            state = 'activated' if user.is_active else 'deactivated'
            messages.success(request, f'{user.username} has been {state}.')
    return redirect('manage_users')


@login_required(login_url='sign_in')
@admin_required
def delete_user(request, pk):
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        if user == request.user or user.is_superuser:
            messages.error(request, 'You cannot delete yourself or a superuser.')
        else:
            user.delete()
            messages.success(request, f'{user.username} has been removed.')
    return redirect('manage_users')


# ---------------------------------------------------------------------------
# Admin lifecycle management
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@admin_required
def approval_queue(request):
    """Review desk — organizations awaiting approval.

    Organization approval is the only admin gate; event packages do not
    require admin review, so the queue focuses on organizations only.
    """
    organizations_qs = Organization.objects.filter(
        status='pending', submitted_at__isnull=False,
    ).order_by('submitted_at').select_related('owner')
    return render(request, 'approval_queue.html', {
        'events': Event.objects.none(),
        'pending_organizations': organizations_qs,
        'total_pending': organizations_qs.count(),
    })


@login_required(login_url='sign_in')
@admin_required
def approve_event(request, pk):
    event = get_object_or_404(Event, pk=pk, status='under_review')
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        try:
            approve(event, request.user, notes)
            messages.success(request, f'Event "{event.title}" has been approved.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def reject_event(request, pk):
    event = get_object_or_404(Event, pk=pk, status='under_review')
    if request.method == 'POST':
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'A rejection reason is required.')
            return redirect('approval_queue')
        try:
            reject(event, request.user, reason)
            messages.success(request, f'Event "{event.title}" has been rejected.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def publish_event(request, pk):
    event = get_object_or_404(Event, pk=pk, status='approved')
    if request.method == 'POST':
        try:
            publish(event, request.user)
            messages.success(request, f'Event "{event.title}" has been published.')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def go_live_event(request, pk):
    event = get_object_or_404(Event, pk=pk, status='published')
    if request.method == 'POST':
        try:
            go_live(event, request.user)
            messages.success(request, f'Event "{event.title}" is now live!')
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def approve_event_go_live(request, pk):
    """Approve, publish and take an under_review package live in one action."""
    event = get_object_or_404(Event, pk=pk, status='under_review')
    if request.method == 'POST':
        notes = request.POST.get('notes', '')
        try:
            approve_and_go_live(event, request.user, notes)
            messages.success(
                request,
                f'Event "{event.title}" has been approved and is now live for booking.',
            )
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('approval_queue')


@login_required(login_url='sign_in')
@admin_required
def publish_event_go_live(request, pk):
    """Take an already-approved (but not yet live) package live in one action."""
    event = get_object_or_404(
        Event,
        pk=pk,
        status__in=('approved', 'published'),
    )
    if request.method == 'POST':
        try:
            publish_and_go_live(event, request.user)
            messages.success(
                request,
                f'Event "{event.title}" is now live for booking.',
            )
        except ValueError as e:
            messages.error(request, str(e))
    return redirect('manage_events')


# ---------------------------------------------------------------------------
# Admin — organizer management
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@admin_required
def manage_organizers(request):
    """Promote attendees to organizers, toggle organizer verification."""
    organizers = User.objects.filter(groups__name='EventOrganizer').select_related('organizer_profile')
    attendees = User.objects.filter(
        groups__name='Attendee',
    ).exclude(is_superuser=True)

    if request.method == 'POST':
        action = request.POST.get('action')
        user_id = request.POST.get('user_id')

        if action == 'promote' and user_id:
            target_user = get_object_or_404(User, pk=user_id)
            org_group, _ = Group.objects.get_or_create(name='EventOrganizer')
            att_group, _ = Group.objects.get_or_create(name='Attendee')
            target_user.groups.add(org_group)
            target_user.groups.remove(att_group)
            from account_manager.models import OrganizerProfile
            OrganizerProfile.objects.get_or_create(user=target_user)
            messages.success(request, f'{target_user.username} promoted to organizer.')
            return redirect('manage_organizers')

        if action == 'toggle_verified' and user_id:
            target_user = get_object_or_404(User, pk=user_id)
            profile, _ = target_user.organizer_profile
            profile.is_verified = not profile.is_verified
            profile.save(update_fields=['is_verified'])
            state = 'verified' if profile.is_verified else 'unverified'
            messages.success(request, f'{target_user.username} is now {state}.')
            return redirect('manage_organizers')

    return render(request, 'manage_organizers.html', {
        'organizers': organizers,
        'pending_attendees': attendees[:20],
    })


# ---------------------------------------------------------------------------
# Admin — category management
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@admin_required
def manage_categories(request):
    """CRUD for EventCategory."""
    categories = EventCategory.objects.all()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            if name:
                cat, created = EventCategory.objects.get_or_create(
                    name__iexact=name,
                    defaults={'name': name, 'description': description},
                )
                if created:
                    messages.success(request, f'Category "{name}" created.')
                else:
                    messages.warning(request, f'Category "{name}" already exists.')
            else:
                messages.error(request, 'Category name is required.')
            return redirect('manage_categories')

        if action == 'delete':
            cat_id = request.POST.get('category_id')
            cat = get_object_or_404(EventCategory, pk=cat_id)
            if cat.events.exists():
                messages.error(request, 'Cannot delete a category with existing events.')
            else:
                cat.delete()
                messages.success(request, 'Category deleted.')
            return redirect('manage_categories')

    return render(request, 'manage_categories.html', {'categories': categories})


# ---------------------------------------------------------------------------
# Delete event (kept for URL compatibility)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@organizer_required
def delete_event(request, pk):
    """Delete an event — ownership-scoped; admins can delete any event."""
    if get_role(request.user) == 'admin':
        event = get_object_or_404(Event, pk=pk)
    else:
        event = get_object_or_404(Event, pk=pk, owner=request.user)
    if request.method == 'POST':
        event.delete()
        messages.success(request, 'Event deleted.')
    return redirect('manage_events')


# ---------------------------------------------------------------------------
# Error pages
# ---------------------------------------------------------------------------

def health_check(request):
    """Lightweight health probe for the hosting platform (Render, etc.).

    Returns 200 with a short JSON body when the app is up and the database is
    reachable, 503 otherwise. No secrets, no HTML — safe to call from uptime
    monitors.
    """
    from django.db import connection
    try:
        connection.ensure_connection()
        return JsonResponse({'status': 'ok'})
    except Exception:  # noqa: BLE001 — a failed probe must return 503, not 500
        return JsonResponse({'status': 'error'}, status=503)


def error_404(request, exception):
    return render(request, '404.html', status=404)


def error_403(request, exception):
    return render(request, '403.html', status=403)


def error_500(request):
    return render(request, '500.html', status=500)


# ---------------------------------------------------------------------------
# Advance payment (Razorpay) — server-side ordering + signature verification
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def initiate_advance(request, pk):
    """Create (or reuse) a Razorpay order for a confirmed booking's advance.

    POST-only, ownership-scoped, and amount is always the server-calculated
    advance — never a value submitted by the browser.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    booking = get_object_or_404(EventBooking, pk=pk, attendee=request.user)
    try:
        _, payload = create_order(booking, request.user)
    except PaymentError as e:
        return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse(payload)


@login_required(login_url='sign_in')
def verify_advance(request):
    """Verify a Razorpay payment signature and mark the advance paid.

    Only the booking's owner can verify, and only a correct HMAC signature
    (over order_id|payment_id with our secret) marks the payment paid.
    """
    if request.method != 'POST':
        return redirect('my_bookings')
    order_id = request.POST.get('razorpay_order_id', '')
    payment_id = request.POST.get('razorpay_payment_id', '')
    signature = request.POST.get('razorpay_signature', '')

    payment = BookingPayment.objects.filter(
        razorpay_order_id=order_id, booking__attendee=request.user,
    ).select_related('booking').first()

    if payment is None:
        messages.error(request, 'Payment could not be verified.')
        return redirect('my_bookings')
    if payment.status == BookingPayment.STATUS_PAID:
        messages.info(request, 'This advance has already been paid.')
        return redirect('my_bookings')

    if not verify_payment_signature(order_id, payment_id, signature):
        payment.status = BookingPayment.STATUS_FAILED
        payment.failure_reason = 'Signature verification failed.'
        payment.save(update_fields=['status', 'failure_reason'])
        messages.error(request, 'Payment verification failed. Please try again.')
        return redirect('my_bookings')

    payment.status = BookingPayment.STATUS_PAID
    payment.razorpay_payment_id = payment_id
    payment.paid_at = timezone.now()
    payment.save(update_fields=['status', 'razorpay_payment_id', 'paid_at'])
    send_advance_confirmation(payment.booking)
    send_booking_status_change(payment.booking)
    messages.success(request, 'Your advance payment was successful. Thank you!')
    return redirect('my_bookings')


@csrf_exempt
def razorpay_webhook(request):
    """Razorpay webhook — idempotent, signature-verified payment capture."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    signature = request.headers.get('X-Razorpay-Signature', '')
    try:
        handled, payment = handle_webhook(request.body, signature)
    except (PaymentError, ValueError):
        return JsonResponse({'error': 'Invalid webhook.'}, status=400)
    if handled and payment is not None:
        send_advance_confirmation(payment.booking)
        send_booking_status_change(payment.booking)
    return JsonResponse({'status': 'ok'})
