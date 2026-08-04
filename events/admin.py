from django.contrib import admin
from . models import *
# Register your models here.

class Event_BookingAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    
class Event_CompanyAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    
admin.site.register(Event_Company, Event_CompanyAdmin)
admin.site.register(Event_Booking, Event_BookingAdmin)
