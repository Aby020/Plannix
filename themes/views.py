from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Count, Sum
from django.shortcuts import redirect, render

from events.models import Event_Booking, Event_Company

from .models import Feedback

PLANNIX_SITE_URL = 'https://plannix.example.com'


def index(request):
    """Plannix landing page."""
    featured = Event_Company.objects.all().order_by('-created_at')[:6]
    event_types = list(
        Event_Company.objects.values_list('event_type', flat=True)
        .distinct()
        .order_by('event_type')
    )
    type_counts = dict(
        Event_Company.objects.values_list('event_type')
        .annotate(count=Count('id'))
    )
    context = {
        'featured_events': featured,
        'event_types': event_types,
        'type_counts': type_counts,
        'total_events': Event_Company.objects.count(),
        'total_bookings': Event_Booking.objects.count(),
        'happy_customers': Event_Booking.objects.values('email').distinct().count(),
        'confirmed_revenue': Event_Booking.objects.filter(
            status__in=['confirmed', 'completed'],
        ).aggregate(total=Sum('event_price'))['total'] or 0,
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

        subject = 'Plannix Feedback'
        body = (
            f'Dear {name},\n\n'
            'Thank you for your feedback. We will get back to you soon.\n\n'
            'Best Regards,\nPlannix Team.'
        )
        send_mail(subject, body, settings.EMAIL_HOST_USER, [email], fail_silently=True)

        messages.success(request, 'Thank you for your feedback!')
        return redirect('feedback')
    return render(request, 'feedback.html')


def success(request):
    return render(request, 'success.html')


def error(request):
    return render(request, 'error.html')


def privacy_policy(request):
    return render(request, 'privacy-policy.html')
