from django.contrib import admin
from django.contrib.auth.models import Group

from .models import UserGroup


# ✅ نخفي Django auth.Group الافتراضي من الأدمن حتى ما يظهر عندك "المجموعات" مرتين
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


@admin.register(UserGroup)
class UserGroupAdmin(admin.ModelAdmin):
    list_display = ("name_ar", "code", "data_scope", "is_mobile_group", "is_active")
    search_fields = ("name_ar", "code")
    list_filter = ("data_scope", "is_mobile_group", "is_active")
