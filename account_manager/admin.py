from django.contrib import admin

from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'status', 'is_verified', 'submitted_at', 'approved_at')
    list_filter = ('status', 'is_verified')
    search_fields = ('name', 'owner__username', 'owner__email')
    list_select_related = ('owner',)
    readonly_fields = ('slug', 'submitted_at', 'approved_at', 'created_at', 'updated_at')

    def has_approve_permission(self, request):
        return request.user.is_superuser or request.user.groups.filter(name='Admin').exists()
