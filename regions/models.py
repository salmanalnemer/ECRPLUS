from django.db import models


class Region(models.Model):
    """
    المناطق (13 منطقة)
    - code: كود ثابت مختصر (يفيد في التكامل مع أنظمة أخرى)
    - name_ar: الاسم بالعربية (العرض الأساسي)
    - name_en: الاسم بالإنجليزية (اختياري)
    - is_active: تفعيل/إيقاف المنطقة بدون حذف
    """

    code = models.CharField("كود المنطقة", max_length=10, unique=True)
    name_ar = models.CharField("اسم المنطقة (عربي)", max_length=100, unique=True)
    name_en = models.CharField("اسم المنطقة (إنجليزي)", max_length=100, blank=True, default="")
    is_active = models.BooleanField("مفعّلة", default=True)

    # ✅ إحداثيات مركز المنطقة (جديدة)
    center_lat = models.DecimalField(
        "خط العرض (مركز المنطقة)",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    center_lng = models.DecimalField(
        "خط الطول (مركز المنطقة)",
        max_digits=9,
        decimal_places=6,
        null=True,
        blank=True
    )

    default_zoom = models.PositiveSmallIntegerField(
        "Zoom افتراضي للخريطة",
        default=11
    )

    # ✅ حدود المنطقة (GeoJSON) لمنع اختيار موقع خارج نطاق المنطقة
    # يدعم: {"type":"Polygon","coordinates":[[[lng,lat],[lng,lat],...]]}
    boundary_geojson = models.JSONField(
        "حدود المنطقة (GeoJSON)",
        null=True,
        blank=True,
        help_text="اختياري. عند تعبئته يتم التحقق في API من أن الإحداثيات داخل حدود المنطقة.",
    )

    # تحسين أداء: حقل مساعد لحفظ Bounding Box (min/max) لتصفية أولية (اختياري)
    bbox_min_lat = models.DecimalField("BBox Min Lat", max_digits=9, decimal_places=6, null=True, blank=True)
    bbox_min_lng = models.DecimalField("BBox Min Lng", max_digits=9, decimal_places=6, null=True, blank=True)
    bbox_max_lat = models.DecimalField("BBox Max Lat", max_digits=9, decimal_places=6, null=True, blank=True)
    bbox_max_lng = models.DecimalField("BBox Max Lng", max_digits=9, decimal_places=6, null=True, blank=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "منطقة"
        verbose_name_plural = "المناطق"
        ordering = ["name_ar"]

    def __str__(self) -> str:
        return self.name_ar
