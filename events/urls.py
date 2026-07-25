from django.urls import path
from . views import *

urlpatterns = [
    path('events', events, name='events'),
    path('readmore/<int:pk>', readmore, name='readmore'),
    path('event-booking-form/<int:pk>', selected_event, name='selected_event'),
    path('event-booking-form', event_booking, name='event_booking'),
    path('search', searching_events, name='searching_events'),
]
