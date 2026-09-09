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
    path('attendee-dashboard', views.attendee_dashboard, name='attendee_dashboard'),
    path('customer-dashboard', views.attendee_dashboard, name='customer_dashboard'),
    path('organizer-dashboard', views.organizer_dashboard, name='organizer_dashboard'),
    path('admin-dashboard', views.admin_dashboard, name='admin_dashboard'),

    # Customer bookings
    path('my-bookings', views.my_bookings, name='my_bookings'),
    path('cancel-booking/<int:pk>', views.cancel_booking, name='cancel_booking'),

    # Advance payment (Razorpay)
    path('payments/<int:pk>/initiate', views.initiate_advance, name='initiate_advance'),
    path('payments/verify', views.verify_advance, name='verify_advance'),
    path('payments/webhook', views.razorpay_webhook, name='razorpay_webhook'),

    # Organizer — events
    path('my-events', views.my_events, name='my_events'),
    path('events/create', views.create_event, name='create_event'),
    path('events/<int:pk>/edit', views.edit_event, name='edit_event'),
    path('events/<int:pk>/submit', views.submit_event, name='submit_event'),
    path('events/<int:pk>/status', views.event_approval_status, name='event_approval_status'),
    path('events/<int:pk>/registrations', views.event_registrations, name='event_registrations'),
    path('events/<int:pk>/pulse', views.event_pulse_view, name='event_pulse_view'),
    path('events/<int:pk>/cancel', views.cancel_event, name='cancel_event'),

    # Management — events (legacy compat routes)
    path('manage/events', views.manage_events, name='manage_events'),
    path('manage/events/add', views.create_event, name='add_event'),
    path('manage/events/edit/<int:pk>', views.edit_event, name='edit_event_old'),
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

    # Admin — lifecycle
    path('admin/approval-queue', views.approval_queue, name='approval_queue'),
    path('admin/approve/<int:pk>', views.approve_event, name='approve_event'),
    path('admin/reject/<int:pk>', views.reject_event, name='reject_event'),
    path('admin/publish/<int:pk>', views.publish_event, name='publish_event'),
    path('admin/go-live/<int:pk>', views.go_live_event, name='go_live_event'),
    path('admin/approve-and-go-live/<int:pk>', views.approve_event_go_live, name='approve_event_go_live'),
    path('admin/publish-and-go-live/<int:pk>', views.publish_event_go_live, name='publish_event_go_live'),

    # Admin — organizer management
    path('manage/organizers', views.manage_organizers, name='manage_organizers'),

    # Admin — category management
    path('manage/categories', views.manage_categories, name='manage_categories'),
]
