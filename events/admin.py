from django.contrib import admin

from .models import Event_Booking, Event_Company


class Event_BookingAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    list_display = ('name', 'event_company_name', 'event_type', 'event_booking_date', 'status', 'created_at')
    list_filter = ('status', 'event_type', 'event_booking_date')
    search_fields = ('name', 'email', 'event_company_name', 'event_location')


class Event_CompanyAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    list_display = ('event_name', 'event_type', 'event_price', 'location', 'created_at')
    list_filter = ('event_type', 'location')
    search_fields = ('event_name', 'event_type', 'location')
    fieldsets = (
        (None, {
            'fields': (
                'event_name', 'event_type', 'event_price', 'location',
                'event_description', 'event_mobile_number', 'event_img',
            ),
        }),
        ('Packages included', {
            'fields': ('package1', 'package2', 'package3', 'package4'),
        }),
        ('Meta', {
            'fields': ('mob_number', 'created_at'),
        }),
    )


admin.site.register(Event_Company, Event_CompanyAdmin)
admin.site.register(Event_Booking, Event_BookingAdmin)
