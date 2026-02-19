from django.contrib import admin
from .models import UserGroup


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "code", "data_scope", "is_mobile_group", "is_active")
    search_fields = ("name_ar", "code")
    list_filter = ("data_scope", "is_mobile_group", "is_active")