from django.shortcuts import render, redirect
from . models import Feedback
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail

def index(request):
    return render(request, 'index.html')

def about(request):
    return render(request, 'about.html')

def feedback(request):
    if request.method == 'POST':
        try:
            name = request.POST['name']
            email = request.POST['email']
            number = request.POST['number']
            message = request.POST['message']
            feedback_data = Feedback.objects.create(name=name, email=email, number=number, message=message)
            feedback_data.save()
            subject = "Nexvent Feedback"
            message = f"Dear {name},\nThank you for your feedback. We will get back to you soon.\n\nBest Regards,\nNexvent Team."
            recipient = email
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [recipient],
                fail_silently=True,
            )
            success_msg = "Thank you for your Feedback"
            messages.success(request, success_msg)
            return redirect('feedback')
        except Exception as e:
            error_msg = 'Server updating'
            messages.error(request, error_msg)
            return redirect('feedback')
    return render(request, 'feedback.html')

def success(request):
    return render(request, 'success.html')

def error(request):
    return render(request, 'error.html')

def privacy_policy(request):
    return render(request, 'privacy-policy.html')
