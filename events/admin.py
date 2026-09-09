from django.contrib import admin

from .models import Event, EventAuditLog, EventBooking, EventCategory, EventImage, EventInclusion, Review


@admin.register(EventCategory)
class EventCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active', 'sort_order', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('sort_order', 'name')


class EventInclusionInline(admin.TabularInline):
    model = EventInclusion
    extra = 1
    fields = ('name', 'sort_order')


class EventImageInline(admin.TabularInline):
    model = EventImage
    extra = 0
    fields = ('image', 'caption', 'sort_order')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at', 'updated_at', 'slug')
    list_display = ('title', 'category', 'status', 'owner', 'price', 'location', 'start_at', 'is_active')
    list_filter = ('status', 'category', 'is_active', 'featured')
    search_fields = ('title', 'description', 'location', 'owner__username')
    raw_id_fields = ('owner',)
    list_select_related = ('category', 'owner')
    inlines = [EventInclusionInline, EventImageInline]
    fieldsets = (
        (None, {
            'fields': ('owner', 'title', 'slug', 'category', 'description', 'price'),
        }),
        ('Event details', {
            'fields': ('venue', 'location', 'start_at', 'end_at', 'capacity', 'contact_number'),
        }),
        ('Media', {
            'fields': ('featured_image',),
        }),
        ('Status & lifecycle', {
            'fields': (
                'status', 'featured', 'is_active',
                'submitted_at', 'approved_at', 'publish_at',
                'review_notes', 'rejection_reason',
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )
    ordering = ('-created_at',)


@admin.register(EventBooking)
class EventBookingAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    list_display = ('name', 'event_title', 'attendee', 'event_date', 'price', 'status', 'created_at')
    list_filter = ('status', 'event_date')
    search_fields = ('name', 'email', 'event_title', 'event_location', 'attendee__username')
    raw_id_fields = ('attendee', 'event')
    list_select_related = ('attendee', 'event')


@admin.register(EventInclusion)
class EventInclusionAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'sort_order')
    list_filter = ('event',)
    search_fields = ('name', 'event__title')
    raw_id_fields = ('event',)
    list_select_related = ('event',)


@admin.register(EventImage)
class EventImageAdmin(admin.ModelAdmin):
    list_display = ('event', 'caption', 'sort_order')
    raw_id_fields = ('event',)
    list_select_related = ('event',)


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('event', 'attendee', 'rating', 'moderation_status', 'created_at')
    list_filter = ('moderation_status', 'rating')
    search_fields = ('event__title', 'attendee__username', 'comment')
    raw_id_fields = ('event', 'attendee', 'booking')
    list_select_related = ('event', 'attendee')


@admin.register(EventAuditLog)
class EventAuditLogAdmin(admin.ModelAdmin):
    readonly_fields = ('created_at',)
    list_display = ('event', 'actor', 'action', 'from_status', 'to_status', 'created_at')
    list_filter = ('action', 'from_status', 'to_status')
    search_fields = ('event__title', 'actor__username', 'reason')
    raw_id_fields = ('event', 'actor')
    ordering = ('-created_at',)
    list_select_related = ('event', 'actor')
