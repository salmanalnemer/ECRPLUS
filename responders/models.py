from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class ResponderLocation(models.Model):
    """آخر حالة/موقع للمستجيب.

    - يتم تحديثه من تطبيق المستجيب كل 10 ثواني.
    - لا نخزن تاريخ طويل لتقليل الحجم (نخزن آخر موقع فقط).
      لو احتجت مسار كامل لاحقاً نضيف جدول TrackingHistory منفصل.
    """

    responder = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="responder_location",
        verbose_name="المستجيب",
    )

    latitude = models.DecimalField("خط العرض", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("خط الطول", max_digits=9, decimal_places=6)

    accuracy_m = models.FloatField("الدقة (متر)", null=True, blank=True)
    speed_m_s = models.FloatField("السرعة (م/ث)", null=True, blank=True)
    heading_deg = models.FloatField("الاتجاه (درجة)", null=True, blank=True)

    device_id = models.CharField("معرّف الجهاز", max_length=128, null=True, blank=True)
    platform = models.CharField("النظام", max_length=32, null=True, blank=True)
    app_version = models.CharField("إصدار التطبيق", max_length=32, null=True, blank=True)

    last_seen = models.DateTimeField("آخر ظهور", default=timezone.now, db_index=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "موقع مستجيب"
        verbose_name_plural = "مواقع المستجيبين"
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"{self.responder} @ {self.latitude},{self.longitude}"
