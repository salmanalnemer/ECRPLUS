from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from .region_scope import apply_region_scope


class RegionScopedQuerysetMixin:
    """
    Mixin عام:
    - ضع region_lookup حسب علاقة الموديل
    - ثم استخدم filter_queryset(request, qs)
    """

    region_lookup: str = "region"

    def filter_queryset(self, request, qs):
        return apply_region_scope(qs, request.user, region_lookup=self.region_lookup)


class RegionScopedAdminMixin(RegionScopedQuerysetMixin):
    """
    للاستخدام داخل Django Admin:
    class MyModelAdmin(RegionScopedAdminMixin, admin.ModelAdmin):
        region_lookup = "region"
    """

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return self.filter_queryset(request, qs)
