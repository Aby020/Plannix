from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import redirect, render

from events.models import Event, EventBooking, EventCategory

from Plannix.emails import send_feedback_confirmation
from Plannix.throttle import rate_limited
from account_manager.identity import display_name

from .forms import FeedbackForm
from .models import Feedback

# Rate-limit budgets for the public feedback endpoint (module-level so tests
# can patch them).
_FEEDBACK_MAX_ATTEMPTS = 5
_FEEDBACK_WINDOW = 300  # 5 minutes


def index(request):
    """Plannix landing page."""
    # Featured = LIVE events only, most recent first.
    featured = Event.objects.filter(status='live', is_active=True).order_by('-created_at')[:6]

    # Category distribution from EventCategory FK.
    categories = EventCategory.objects.filter(is_active=True).order_by('sort_order', 'name')
    event_types = [cat.name for cat in categories]
    type_counts = dict(
        Event.objects.filter(status='live')
        .values_list('category__name')
        .annotate(count=Count('id'))
    )

    live_events = Event.objects.filter(status='live')

    # Occasion cards: real EventCategory objects behind every link + a static
    # image per known slug, falling back to one shared image for new occasions.
    category_image_map = {
        'birthday': 'img/px-birthday.jpg',
        'catering': 'img/px-catering.jpg',
        'corporate': 'img/px-corporate.jpg',
        'dj': 'img/px-dj.jpg',
        'wedding': 'img/px-wedding.jpg',
    }
    occasion_images = {
        cat.slug: category_image_map.get(cat.slug, 'img/px-event-fallback.jpg')
        for cat in categories
    }

    context = {
        'featured_events': featured,
        'event_types': event_types,
        'type_counts': type_counts,
        'total_events': live_events.count(),
        'total_bookings': EventBooking.objects.count(),
        'happy_customers': EventBooking.objects.values('email').distinct().count(),
        'confirmed_revenue': EventBooking.objects.filter(
            status__in=['confirmed', 'completed'],
        ).aggregate(total=Sum('price'))['total'] or 0,
        'categories': categories,
        'occasion_images': occasion_images,
    }
    return render(request, 'index.html', context)


def about(request):
    return render(request, 'about.html')


@rate_limited('feedback', lambda: _FEEDBACK_MAX_ATTEMPTS, lambda: _FEEDBACK_WINDOW)
def feedback(request):
    # Pre-fill for a signed-in visitor. Read defensively: ``request.user`` is an
    # AnonymousUser when logged out, and ``AnonymousUser.email`` is a plain
    # attribute — accessing it through a template raises VariableDoesNotExist.
    default_name = display_name(request.user)
    default_email = getattr(request.user, 'email', '') or ''

    if request.method == 'POST':
        # Validated through the form, not raw POST values: an over-length name
        # or a malformed email must come back as a form error rather than reach
        # the database (where an over-length value raises DataError on
        # PostgreSQL and surfaces as a 500).
        form = FeedbackForm(request.POST)
        if form.is_valid():
            feedback_entry = form.save()
            send_feedback_confirmation(feedback_entry.email, feedback_entry.name)

            messages.success(request, 'Thank you for your feedback!')
            return redirect('feedback')

        for field_errors in form.errors.values():
            for error in field_errors:
                messages.error(request, error)
        return render(request, 'feedback.html', {
            'form': form,
            'default_name': default_name,
            'default_email': default_email,
        }, status=400)

    return render(request, 'feedback.html', {
        'form': FeedbackForm(),
        'default_name': default_name,
        'default_email': default_email,
    })


def success(request):
    """Booking-confirmation page (also used for other success states).

    When reached right after a booking (``?booking=<id>``), the page shows the
    booking details and the organizer's public contact so the attendee knows
    how to arrange payment. The booking is scoped to the signed-in owner so a
    guessed id can never leak another attendee's booking.
    """
    from Plannix.emails import organizer_contact
    context = {}
    booking_id = request.GET.get('booking')
    if booking_id and request.user.is_authenticated:
        booking = EventBooking.objects.filter(
            pk=booking_id, attendee=request.user,
        ).select_related('event', 'event__owner', 'event__organization').first()
        if booking is not None:
            provider, organizer_email, organizer_phone = organizer_contact(booking)
            context.update({
                'booking': booking,
                'provider_name': provider,
                'organizer_email': organizer_email,
                'organizer_phone': organizer_phone,
            })
    return render(request, 'success.html', context)


def error(request):
    return render(request, 'error.html')


def privacy_policy(request):
    return render(request, 'privacy-policy.html')
