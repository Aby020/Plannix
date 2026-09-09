from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views
from .forms import PlannixPasswordResetForm

urlpatterns = [
    path('sign-up', views.sign_up, name='sign_up'),
    path('sign-in', views.sign_in, name='sign_in'),
    path('sign-out', views.sign_out, name='sign_out'),
    path('profile', views.profile, name='profile'),
    path('change-password', views.change_password, name='change_password'),

    # Password reset (Django built-in, branded templates, email via Plannix service)
    path('password-reset', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        form_class=PlannixPasswordResetForm,
        success_url=reverse_lazy('password_reset_done'),
    ), name='password_reset'),
    path('password-reset/done', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html',
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete'),
    ), name='password_reset_confirm'),
    path('reset/done', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html',
    ), name='password_reset_complete'),

    # Organization (marketplace business entity)
    path('organization', views.my_organization, name='my_organization'),
    path('organization/submit', views.submit_organization, name='submit_organization'),
    path('manage/organizations', views.manage_organizations, name='manage_organizations'),
    path('manage/organizations/<int:pk>/approve', views.approve_organization, name='approve_organization'),
    path('manage/organizations/<int:pk>/reject', views.reject_organization, name='reject_organization'),
]