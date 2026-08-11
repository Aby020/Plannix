"""Views for the Plannix events module.

Includes the public event catalogue, booking flow, role-based dashboards,
and the management views used by staff and administrators.
"""
from datetime import date, datetime

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from account_manager.decorators import admin_only, get_role, staff_or_admin
from themes.models import Feedback

from .models import Event_Booking, Event_Company

PLANNIX_SITE_URL = 'https://plannix.example.com'

BOOKING_STATUSES = ['pending', 'confirmed', 'completed', 'cancelled']


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def send_booking_email(booking):
    """Send a booking-confirmation email for a new Plannix booking."""
    subject = 'Plannix — Booking Confirmation'
    message = (
        f'Dear {booking.name},\n\n'
        'You have successfully booked your event with Plannix. '
        'Our team will get back to you shortly to confirm the details.\n\n'
        'Here are your booking details:\n'
        f'    Name: {booking.name}\n'
        f'    Mobile Number: {booking.number}\n'
        f'    Event Company: {booking.event_company_name}\n'
        f'    Event Type: {booking.event_type}\n'
        f'    Event Price: Rs. {booking.event_price}\n'
        f'    Event Location: {booking.event_location}\n'
        f'    Event Date: {booking.event_booking_date}\n'
        f'    Contact Number: {booking.event_mobile_number}\n\n'
        'Please keep this email for your records and do not forward or share it with anyone.\n\n'
        f'Best Regards,\nPlannix Team.\n{PLANNIX_SITE_URL}'
    )
    send_mail(subject, message, settings.EMAIL_HOST_USER, [booking.email], fail_silently=True)


def send_status_email(booking):
    """Notify the customer when a booking status changes."""
    subject = f'Plannix — Booking {booking.get_status_display()}'
    message = (
        f'Dear {booking.name},\n\n'
        f'Your booking for "{booking.event_company_name}" on {booking.event_booking_date} '
        f'is now {booking.get_status_display().lower()}.\n\n'
        f'Best Regards,\nPlannix Team.\n{PLANNIX_SITE_URL}'
    )
    send_mail(subject, message, settings.EMAIL_HOST_USER, [booking.email], fail_silently=True)


# ---------------------------------------------------------------------------
# Public catalogue
# ---------------------------------------------------------------------------

def events(request):
    """Browse all event packages (public)."""
    event_type = request.GET.get('type', '').strip()
    queryset = Event_Company.objects.all().order_by('-created_at')
    if event_type:
        queryset = queryset.filter(event_type__iexact=event_type)
    types = (
        Event_Company.objects.values_list('event_type', flat=True)
        .distinct()
        .order_by('event_type')
    )
    return render(request, 'events.html', {
        'events': queryset,
        'types': types,
        'active_type': event_type,
    })


def readmore(request, pk):
    """Show full details of one event package."""
    event_detail = get_object_or_404(Event_Company, pk=pk)
    return render(request, 'readmore.html', {'event_detail': event_detail})


def searching_events(request):
    """Keyword search over event packages (name, type, location)."""
    search_query = request.GET.get('q') or request.POST.get('search_query') or ''
    search_query = search_query.strip()
    if not search_query:
        messages.error(request, 'Please enter a search term.')
        return render(request, 'search.html', {'events': []})

    results = Event_Company.objects.filter(
        Q(event_name__icontains=search_query)
        | Q(event_type__icontains=search_query)
        | Q(event_price__icontains=search_query)
        | Q(location__icontains=search_query)
    ).order_by('-created_at')

    if not results:
        messages.error(request, f'No packages found for "{search_query}".')
    return render(request, 'search.html', {'events': results, 'search_query': search_query})


# ---------------------------------------------------------------------------
# Booking flow
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def selected_event(request, pk):
    """Open the booking form for a specific event package."""
    event = get_object_or_404(Event_Company, pk=pk)
    return render(request, 'event-booking-form.html', {
        'event': event,
        'today_date': date.today().isoformat(),
    })


@login_required(login_url='sign_in')
def event_booking(request):
    """Handle a new booking submission."""
    today_date = date.today().isoformat()

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        number = request.POST.get('number', '').strip()
        event_company_name = request.POST.get('event_company_name', '').strip()
        event_type = request.POST.get('event_type', '').strip()
        event_price = request.POST.get('event_price', '')
        event_location = request.POST.get('event_location', '').strip()
        event_mobile_number = request.POST.get('event_mobile_number', '').strip()
        event_booking_date = request.POST.get('date', '').strip()

        # Keep the user on the event's booking form when validation fails.
        event_id = request.POST.get('event_id') or None
        event = None
        if event_id:
            event = Event_Company.objects.filter(pk=event_id).first()

        def booking_error(message):
            messages.error(request, message)
            if event is not None:
                return redirect('selected_event', pk=event.pk)
            return redirect('event_booking')

        # Validate required fields
        required = {
            'name': name, 'email': email, 'number': number,
            'event_company_name': event_company_name, 'event_type': event_type,
            'event_price': event_price, 'event_location': event_location,
            'date': event_booking_date,
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            return booking_error('Please complete all the required fields.')

        try:
            selected_date = datetime.strptime(event_booking_date, '%Y-%m-%d').date()
        except ValueError:
            return booking_error('Please choose a valid booking date.')

        if selected_date < date.today():
            return booking_error('You cannot book a date in the past.')

        if len(number) != 10 or not number.isdigit():
            return booking_error('Please enter a valid 10-digit mobile number.')

        conflict = Event_Booking.objects.filter(
            event_booking_date=event_booking_date,
            event_type=event_type,
        ).exclude(status='cancelled').exists()

        if conflict:
            return booking_error(
                'This event type is already booked on that date — please choose another date.',
            )

        booking = Event_Booking.objects.create(
            user=request.user,
            name=name,
            email=email,
            number=number,
            event_company_name=event_company_name,
            event_type=event_type,
            event_price=event_price,
            event_location=event_location,
            event_mobile_number=event_mobile_number,
            event_booking_date=event_booking_date,
            status='pending',
        )
        send_booking_email(booking)
        messages.success(
            request,
            'Your booking request was received! A confirmation email has been sent.',
        )
        return redirect('success')

    return render(request, 'event-booking-form.html', {'today_date': today_date})


# ---------------------------------------------------------------------------
# Role-based dashboards
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def dashboard(request):
    """Route the user to the dashboard matching their role."""
    role = get_role(request.user)
    if role == 'admin':
        return redirect('admin_dashboard')
    if role == 'staff':
        return redirect('staff_dashboard')
    return redirect('customer_dashboard')


@login_required(login_url='sign_in')
def customer_dashboard(request):
    """Personal dashboard for a regular customer."""
    bookings = request.user.bookings.all().order_by('-created_at')
    upcoming = [b for b in bookings if b.event_booking_date >= date.today().isoformat() and b.status != 'cancelled']
    total_spent = bookings.filter(status__in=['confirmed', 'completed']).aggregate(total=Sum('event_price'))['total'] or 0
    return render(request, 'customer_dashboard.html', {
        'bookings': bookings,
        'upcoming_bookings': upcoming[:5],
        'total_bookings': bookings.count(),
        'upcoming_count': len(upcoming),
        'total_spent': total_spent,
        'recent_bookings': bookings[:5],
    })


@login_required(login_url='sign_in')
@staff_or_admin
def staff_dashboard(request):
    """Operational dashboard for staff members and admins."""
    bookings = Event_Booking.objects.all().order_by('-created_at')
    upcoming = bookings.filter(
        event_booking_date__gte=date.today().isoformat(),
    ).exclude(status='cancelled')
    return render(request, 'staff_dashboard.html', {
        'total_events': Event_Company.objects.count(),
        'total_bookings': bookings.count(),
        'pending_bookings': bookings.filter(status='pending').count(),
        'upcoming_count': upcoming.count(),
        'total_feedback': Feedback.objects.count(),
        'recent_bookings': bookings[:6],
        'recent_feedback': Feedback.objects.all().order_by('-created_at')[:5],
    })


@login_required(login_url='sign_in')
@admin_only
def admin_dashboard(request):
    """Full platform overview for administrators."""
    bookings = Event_Booking.objects.all()
    users = User.objects.all()
    revenue = bookings.filter(status__in=['confirmed', 'completed']).aggregate(total=Sum('event_price'))['total'] or 0

    status_counts = {
        status: bookings.filter(status=status).count()
        for status in BOOKING_STATUSES
    }
    type_counts = list(
        Event_Company.objects.values('event_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:6]
    )
    return render(request, 'admin_dashboard.html', {
        'total_users': users.count(),
        'staff_count': users.filter(groups__name='staff').count(),
        'total_events': Event_Company.objects.count(),
        'total_bookings': bookings.count(),
        'status_counts': status_counts,
        'revenue': revenue,
        'recent_bookings': bookings.order_by('-created_at')[:8],
        'recent_feedback': Feedback.objects.all().order_by('-created_at')[:5],
        'type_counts': type_counts,
    })


# ---------------------------------------------------------------------------
# Customer bookings
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
def my_bookings(request):
    """List the current user's bookings."""
    bookings = request.user.bookings.all().order_by('-created_at')
    return render(request, 'my_bookings.html', {'bookings': bookings})


@login_required(login_url='sign_in')
def cancel_booking(request, pk):
    """Let a customer cancel one of their own bookings."""
    booking = get_object_or_404(Event_Booking, pk=pk, user=request.user)
    if request.method == 'POST':
        if booking.status in ('completed', 'cancelled'):
            messages.error(request, 'This booking cannot be cancelled.')
        else:
            booking.status = 'cancelled'
            booking.save(update_fields=['status'])
            send_status_email(booking)
            messages.success(request, 'Your booking has been cancelled.')
        return redirect('my_bookings')
    messages.error(request, 'Invalid request.')
    return redirect('my_bookings')


# ---------------------------------------------------------------------------
# Management — events (staff & admin)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@staff_or_admin
def manage_events(request):
    events = Event_Company.objects.all().order_by('-created_at')
    return render(request, 'manage_events.html', {'events': events})


def _event_from_post(request, event=None):
    """Build or update an Event_Company from POST data. Returns (event, error)."""
    event_name = request.POST.get('event_name', '').strip()
    event_type = request.POST.get('event_type', '').strip()
    event_price = request.POST.get('event_price', '')
    event_description = request.POST.get('event_description', '').strip()
    event_mobile_number = request.POST.get('event_mobile_number', '').strip()
    package1 = request.POST.get('package1', '').strip()
    package2 = request.POST.get('package2', '').strip()
    package3 = request.POST.get('package3', '').strip()
    package4 = request.POST.get('package4', '').strip()
    location = request.POST.get('location', '').strip()

    if not (event_name and event_type and event_price and event_description and location):
        return None, 'Please fill in all required fields.'

    if not event_price.isdigit():
        return None, 'Event price must be a number.'

    if event is None:
        event = Event_Company()

    event.event_name = event_name
    event.event_type = event_type
    event.event_price = int(event_price)
    event.event_description = event_description
    event.event_mobile_number = event_mobile_number
    event.package1 = package1
    event.package2 = package2
    event.package3 = package3
    event.package4 = package4
    event.location = location

    if request.FILES.get('event_img'):
        event.event_img = request.FILES['event_img']
    return event, None


@login_required(login_url='sign_in')
@staff_or_admin
def add_event(request):
    if request.method == 'POST':
        event, error = _event_from_post(request)
        if error:
            messages.error(request, error)
            return redirect('add_event')
        event.save()
        messages.success(request, 'Event package added successfully.')
        return redirect('manage_events')
    return render(request, 'event_form.html', {'event': None})


@login_required(login_url='sign_in')
@staff_or_admin
def edit_event(request, pk):
    event = get_object_or_404(Event_Company, pk=pk)
    if request.method == 'POST':
        event, error = _event_from_post(request, event)
        if error:
            messages.error(request, error)
            return redirect('edit_event', pk=pk)
        event.save()
        messages.success(request, 'Event package updated successfully.')
        return redirect('manage_events')
    return render(request, 'event_form.html', {'event': event})


@login_required(login_url='sign_in')
@staff_or_admin
def delete_event(request, pk):
    event = get_object_or_404(Event_Company, pk=pk)
    if request.method == 'POST':
        event.delete()
        messages.success(request, 'Event package deleted.')
    return redirect('manage_events')


# ---------------------------------------------------------------------------
# Management — bookings (staff & admin)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@staff_or_admin
def manage_bookings(request):
    bookings = Event_Booking.objects.all().order_by('-created_at')
    status_filter = request.GET.get('status', '')
    if status_filter in BOOKING_STATUSES:
        bookings = bookings.filter(status=status_filter)
    return render(request, 'manage_bookings.html', {
        'bookings': bookings,
        'active_status': status_filter,
        'statuses': BOOKING_STATUSES,
    })


@login_required(login_url='sign_in')
@staff_or_admin
def update_booking_status(request, pk):
    booking = get_object_or_404(Event_Booking, pk=pk)
    if request.method == 'POST':
        new_status = request.POST.get('status', '')
        if new_status in BOOKING_STATUSES:
            booking.status = new_status
            booking.save(update_fields=['status'])
            send_status_email(booking)
            messages.success(request, f'Booking marked as {new_status}.')
    return redirect('manage_bookings')


@login_required(login_url='sign_in')
@staff_or_admin
def delete_booking(request, pk):
    booking = get_object_or_404(Event_Booking, pk=pk)
    if request.method == 'POST':
        booking.delete()
        messages.success(request, 'Booking deleted.')
    return redirect('manage_bookings')


# ---------------------------------------------------------------------------
# Management — feedback (staff & admin)
# ---------------------------------------------------------------------------

@login_required(login_url='sign_in')
@staff_or_admin
def manage_feedback(request):
    feedback = Feedback.objects.all().order_by('-created_at')
    return render(request, 'manage_feedback.html', {'feedback_list': feedback})


@login_required(login_url='sign_in')
@staff_or_admin
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
@admin_only
def manage_users(request):
    users = User.objects.all().order_by('-date_joined')
    users_with_roles = [(user, get_role(user)) for user in users]
    return render(request, 'manage_users.html', {
        'users_with_roles': users_with_roles,
    })


@login_required(login_url='sign_in')
@admin_only
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
@admin_only
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
# Error pages
# ---------------------------------------------------------------------------

def error_404(request, exception):
    return render(request, '404.html', status=404)


def error_403(request, exception):
    return render(request, '403.html', status=403)


def error_500(request):
    return render(request, '500.html', status=500)
