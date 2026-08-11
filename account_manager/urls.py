from django.urls import path

from . import views

urlpatterns = [
    path('sign-up', views.sign_up, name='sign_up'),
    path('sign-in', views.sign_in, name='sign_in'),
    path('sign-out', views.sign_out, name='sign_out'),
    path('profile', views.profile, name='profile'),
    path('change-password', views.change_password, name='change_password'),
]
