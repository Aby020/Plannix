"""
URL configuration for the Plannix project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from events.views import error_404, error_403, error_500

urlpatterns = [
    path('core-admin/', admin.site.urls),
    path('', include('themes.urls')),
    path('', include('events.urls')),
    path('', include('account_manager.urls')),
]

# Custom error pages
handler404 = 'events.views.error_404'
handler403 = 'events.views.error_403'
handler500 = 'events.views.error_500'

# For development purposes — serving static & media files directly.
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
