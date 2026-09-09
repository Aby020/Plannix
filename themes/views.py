from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import redirect, render

from events.models import Event, EventBooking, EventCategory

from Plannix.emails import send_feedback_confirmation

from .models import Feedback


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


def feedback(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        email = request.POST.get('email', '').strip()
        number = request.POST.get('number', '').strip()
        message = request.POST.get('message', '').strip()

        if not (name and email and message):
            messages.error(request, 'Please fill in your name, email and message.')
            return redirect('feedback')

        Feedback.objects.create(name=name, email=email, number=number, message=message)
        send_feedback_confirmation(email, name)

        messages.success(request, 'Thank you for your feedback!')
        return redirect('feedback')
    return render(request, 'feedback.html')


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
