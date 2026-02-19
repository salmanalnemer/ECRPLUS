from django.contrib import admin

from .models import Region


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    list_display = (
        "name_ar",
        "code",
        "is_active",
        "center_lat",
        "center_lng",
        "default_zoom",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name_ar", "name_en", "code")
    ordering = ("name_ar",)

    fieldsets = (
        ("بيانات المنطقة", {"fields": ("code", "name_ar", "name_en", "is_active")}),
        ("إعدادات الخريطة", {"fields": ("center_lat", "center_lng", "default_zoom")}),
        (
            "حدود المنطقة (للتطبيق)",
            {
                "fields": (
                    "boundary_geojson",
                    ("bbox_min_lat", "bbox_min_lng", "bbox_max_lat", "bbox_max_lng"),
                ),
                "description": "اختياري: عند تعبئة الحدود سيتم منع حفظ البلاغ إذا كان الموقع خارج المنطقة.",
            },
        ),
    )
