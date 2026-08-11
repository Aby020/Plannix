from django.urls import path

from . import views

urlpatterns = [
    # Public catalogue
    path('events', views.events, name='events'),
    path('readmore/<int:pk>', views.readmore, name='readmore'),
    path('search', views.searching_events, name='searching_events'),

    # Booking
    path('event-booking-form/<int:pk>', views.selected_event, name='selected_event'),
    path('event-booking-form', views.event_booking, name='event_booking'),

    # Dashboards
    path('dashboard', views.dashboard, name='dashboard'),
    path('customer-dashboard', views.customer_dashboard, name='customer_dashboard'),
    path('staff-dashboard', views.staff_dashboard, name='staff_dashboard'),
    path('admin-dashboard', views.admin_dashboard, name='admin_dashboard'),

    # Customer bookings
    path('my-bookings', views.my_bookings, name='my_bookings'),
    path('cancel-booking/<int:pk>', views.cancel_booking, name='cancel_booking'),

    # Management — events
    path('manage/events', views.manage_events, name='manage_events'),
    path('manage/events/add', views.add_event, name='add_event'),
    path('manage/events/edit/<int:pk>', views.edit_event, name='edit_event'),
    path('manage/events/delete/<int:pk>', views.delete_event, name='delete_event'),

    # Management — bookings
    path('manage/bookings', views.manage_bookings, name='manage_bookings'),
    path('manage/bookings/<int:pk>/status', views.update_booking_status, name='update_booking_status'),
    path('manage/bookings/delete/<int:pk>', views.delete_booking, name='delete_booking'),

    # Management — feedback
    path('manage/feedback', views.manage_feedback, name='manage_feedback'),
    path('manage/feedback/delete/<int:pk>', views.delete_feedback, name='delete_feedback'),

    # Management — users (admin)
    path('manage/users', views.manage_users, name='manage_users'),
    path('manage/users/<int:pk>/toggle', views.toggle_user_active, name='toggle_user_active'),
    path('manage/users/delete/<int:pk>', views.delete_user, name='delete_user'),
]
