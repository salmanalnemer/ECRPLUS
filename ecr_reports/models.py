from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone



class MedicalConditionCatalog(models.Model):
    name = models.CharField("نوع الحالة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)

    # ✅ رجّعها لتفادي مشاكل قديمة (اختياري لكن مفيد)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class ServiceCatalog(models.Model):
    name = models.CharField("اسم الخدمة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)

    # ✅ هذا هو المهم لحل خطأ NOT NULL
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    name = models.CharField("نوع الحالة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)

    class Meta:
        verbose_name = "نوع حالة"
        verbose_name_plural = "أنواع الحالات"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ServiceCatalog(models.Model):
    """كتالوج الخدمات المقدمة."""

    name = models.CharField("اسم الخدمة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)

    class Meta:
        verbose_name = "خدمة"
        verbose_name_plural = "الخدمات"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MobileReport(models.Model):
    """بلاغ مبسط: (المستجيب + نوع الحالة + الخدمات + الموقع + الجنس + ملاحظات)."""

    class Gender(models.TextChoices):
        MALE = "male", "ذكر"
        FEMALE = "female", "أنثى"

    # ✅ المستجيب (منشئ البلاغ)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mobile_reports",
        verbose_name="المستجيب",
    )
    created_at = models.DateTimeField("تاريخ الإنشاء", default=timezone.now)

    # نوع الحالة
    medical_condition = models.ForeignKey(
        MedicalConditionCatalog,
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="نوع الحالة",
    )

    # الخدمات المقدمة
    services = models.ManyToManyField(
        ServiceCatalog,
        related_name="reports",
        verbose_name="الخدمات المقدمة",
        blank=True,
    )

    # الموقع (الخريطة)
    latitude = models.DecimalField(
        "خط العرض",
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-90), MaxValueValidator(90)],
    )
    longitude = models.DecimalField(
        "خط الطول",
        max_digits=9,
        decimal_places=6,
        validators=[MinValueValidator(-180), MaxValueValidator(180)],
    )

    # الجنس
    gender = models.CharField(
        "الجنس",
        max_length=10,
        choices=Gender.choices,
        default=Gender.MALE,
    )

    # ✅ ملاحظات
    notes = models.TextField("ملاحظات", blank=True, default="")

    class Meta:
        verbose_name = "بلاغ"
        verbose_name_plural = "البلاغات"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["created_by", "created_at"]),
            models.Index(fields=["medical_condition"]),
            models.Index(fields=["gender"]),
        ]

    def __str__(self) -> str:
        return f"بلاغ #{self.pk}"