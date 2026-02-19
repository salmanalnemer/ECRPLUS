from django.contrib import admin
from .models import Organization


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    ordering = ("name",)
    readonly_fields = ("code", "created_at", "updated_at")  # الكود للعرض فقط

    fieldsets = (
        ("بيانات الجهة", {"fields": ("name", "code", "is_active")}),
        ("معلومات النظام", {"fields": ("created_at", "updated_at")}),
    )
