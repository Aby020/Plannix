from django.contrib import admin
from . models import *

class FeedbackAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)

admin.site.register(Feedback, FeedbackAdmin)