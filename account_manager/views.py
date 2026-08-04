from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from . decorators import unauthenticated_user
from django.contrib import messages
from django.conf import settings
from django.core.mail import send_mail

@unauthenticated_user
def sign_up(request):
    if request.method == 'POST':
        try:
            username = request.POST['username']
            email = request.POST['email']
            password = request.POST['password']
            user_data = User.objects.create_user(username=username, email=email, password=password)
            user_data.save()
            subject = "Nexvent Account"
            message = f"Dear {username},\nYou are successfully created your account with Nexvent.\nPlease keep this email for your records and do not forward or share any other person.\nTo get started, please visit our website at https://www.nexvent.pythonanywhere.com/ and use our services.\nFor more details login with Nexvent.\n\nBest Regards,\nNexvent Team."
            recipient = email
            send_mail(
                subject,
                message,
                settings.EMAIL_HOST_USER,
                [recipient],
                fail_silently=True,
            )
            success_msg = 'Account Created'
            messages.success(request, success_msg)
            return redirect('sign_in')
        except Exception as e:
            error_msg = 'Username is already exist'
            messages.error(request, error_msg)
            return redirect('sign_up')
    return render(request, 'sign-up.html')

@unauthenticated_user
def sign_in(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        user_auth = authenticate(username=username, password=password)
        if user_auth is not None:
            login(request, user_auth)
            return redirect('index')
        else:
            error_msg = 'Invalid Username or Password'
            messages.error(request, error_msg)
            return redirect('sign_in')
    return render(request, 'sign-in.html')

@login_required(login_url='sign_in')
def sign_out(request):
    logout(request)
    success_msg = 'Sign Out Successfully'
    messages.success(request, success_msg)
    return redirect('sign_in')
