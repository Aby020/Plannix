from django.shortcuts import render, redirect
from . models import *
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.mail import send_mail
from datetime import datetime, date
# Create your views here.

@login_required(login_url='sign_in')
def events(request):
    events = {
        'events': Event_Company.objects.all()
    }
    return render(request, 'events.html', events)

def readmore(request, pk):
    event_details = {
        'event_detail': Event_Company.objects.get(id=pk)
    }
    return render(request, 'readmore.html', event_details)

@login_required(login_url='sign_in')
def selected_event(request, pk):
    event = {
        'event':Event_Company.objects.get(pk=pk)
    }
    return render(request, 'event-booking-form.html', event)

@login_required(login_url='sign_in')
def event_booking(request):
    today_date = date.today().isoformat()
    if request.method == 'POST':
        try:
            name = request.POST['name']
            email = request.POST['email']
            number = request.POST['number']
            event_company_name = request.POST['event_company_name']
            event_type = request.POST['event_type']
            event_price = request.POST['event_price']
            event_location = request.POST['event_location']
            event_mobile_number = request.POST['event_mobile_number']
            event_booking_date = request.POST['date']
            selected_date = datetime.strptime(event_booking_date, "%Y-%m-%d").date()
            if selected_date < datetime.today().date():
                messages.error(request, "You cannot book a past date.")
                return redirect('event_booking')
            
            #  Check for conflict
            conflict = Event_Booking.objects.filter(
                event_booking_date=event_booking_date,
                 event_type=event_type 
            ).exists()
            
            if conflict:
                error_msg = 'Event is already Booked on this date please book another date'
                messages.error(request, error_msg)
                return redirect('event_booking')
            else:
                booking_data = Event_Booking.objects.create(name=name, email=email, number=number, event_company_name=event_company_name,
                                                            event_type=event_type, event_price=event_price, event_location=event_location, event_mobile_number=event_mobile_number,
                                                            event_booking_date=event_booking_date)
                booking_data.save()
                subject = "Nexvent Event"
                message = f"Dear {name},\nYou are successfully booked our event Service with Nexvent. We will get back to you soon.\nHere are your booking details:\n\tName: {name}\n\tMobile Number:{number}\n\tEvent Company Name: {event_company_name}\n\tEvent Type: {event_type}\n\tEvent Price: {event_price}\n\tEvent Location: {event_location}\n\tEvent Booked Date: {event_booking_date}\n\tContact Number: {event_mobile_number}\nPlease keep this email for your records and do not forward or share any other person.\nTo get started, please visit our website at https://www.nexvent.pythonanywhere.com/ and use our services.\nFor more details login with Nexvent.\n\nBest Regards,\nNexvent Team."
                recipient = email
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,
                    [recipient],
                    fail_silently=True,
                )
                return redirect('success')
        except Exception as e:
            return redirect('error')
    return render(request, 'event-booking-form.html', {'today_date': today_date})

def searching_events(request):
    if request.method == 'POST':
        search_query = request.POST['search_query']
        if search_query != None:
            search_result = Event_Company.objects.filter(Q(event_name__icontains=search_query)|Q(event_type__icontains=search_query)|Q(event_price__icontains=search_query)|Q(location__icontains=search_query))
            return render(request, 'search.html', {'events': search_result})
        else:
            error_msg = 'Event not Found'
            messages.error(request, error_msg)
            return render(request, 'search.html')