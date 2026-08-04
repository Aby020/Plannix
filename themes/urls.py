from django.urls import path
from . views import *

urlpatterns = [
    path('', index, name='index'),
    path('about', about, name='about'),
    path('feedback', feedback, name='feedback'),
    path('success', success, name='success'),
    path('error', error, name='error'),
    path('privacy-policy', privacy_policy, name='privacy_policy'),
]
