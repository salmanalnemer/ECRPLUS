from __future__ import annotations

from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError



class MedicalConditionCatalog(models.Model):
    """كتالوج تفاصيل الحالة المرضية."""

    name = models.CharField("اسم الحالة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "كتالوج الحالة المرضية"
        verbose_name_plural = "كتالوج الحالات المرضية"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ServiceCatalog(models.Model):
    """كتالوج الخدمات المقدمة للمريض."""

    name = models.CharField("اسم الخدمة", max_length=150, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "كتالوج الخدمات المقدمة"
        verbose_name_plural = "كتالوج الخدمات المقدمة"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class MobileReport(models.Model):
    """بلاغات تطبيق ECR (قادمة من الجوال فقط)."""

    class Nationality(models.TextChoices):
        SAUDI = "saudi", "سعودي"
        RESIDENT = "resident", "مقيم"

    class Gender(models.TextChoices):
        MALE = "male", "ذكر"
        FEMALE = "female", "أنثى"

    class AmbulanceCaller(models.TextChoices):
        SELF = "self", "أنا"
        OTHER = "other", "شخص آخر"

    # الحقول الأساسية حسب متطلبات التطبيق
    patient_name = models.CharField("اسم المريض", max_length=200)
    national_id = models.CharField("رقم الهوية", max_length=20, blank=True, default="")

    phone_validator = RegexValidator(
        regex=r"^\+?\d{7,15}$",
        message="رقم الجوال غير صالح. أدخل أرقام فقط ويمكن إضافة + في البداية.",
    )
    patient_phone = models.CharField("رقم الجوال", max_length=20, validators=[phone_validator])
    age = models.PositiveSmallIntegerField("العمر", null=True, blank=True, validators=[MinValueValidator(0)])
    nationality = models.CharField(
        "الجنسية",
        max_length=20,
        choices=Nationality.choices,
        default=Nationality.SAUDI,
    )
    gender = models.CharField(
        "الجنس",
        max_length=10,
        choices=Gender.choices,
        default=Gender.MALE,
    )

    medical_condition = models.ForeignKey(
        "ecr_reports.MedicalConditionCatalog",
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="تفاصيل الحالة المرضية",
        null=True,
        blank=True,
    )
    services = models.ManyToManyField(
        "ecr_reports.ServiceCatalog",
        related_name="reports",
        verbose_name="الخدمات المقدمة للمريض",
        blank=True,
    )

    called_ambulance = models.BooleanField("هل تم طلب إسعاف؟", default=False)
    ambulance_called_by = models.CharField(
        "من طلب الإسعاف",
        max_length=10,
        choices=AmbulanceCaller.choices,
        blank=True,
        default="",
        help_text="يظهر فقط إذا كان (هل تم طلب إسعاف؟) = نعم",
    )

    # الموقع
    latitude = models.DecimalField("خط العرض", max_digits=9, decimal_places=6)
    longitude = models.DecimalField("خط الطول", max_digits=9, decimal_places=6)

    # المنطقة الإدارية (لا يسمح بالحفظ خارج حدود منطقة المستخدم)
    region = models.ForeignKey(
        "regions.Region",
        on_delete=models.PROTECT,
        related_name="mobile_reports",
        verbose_name="المنطقة",
    )

    # تتبع الطلب
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="mobile_reports",
        verbose_name="المُبلّغ",
    )
    created_at = models.DateTimeField("تاريخ البلاغ", default=timezone.now)

    send_to_997 = models.BooleanField(
        "إرسال توثيق الحالة إلى 997",
        default=False,
        help_text="يوثق رغبة المستخدم (يتم إرجاع نص جاهز للمشاركة/الإبلاغ عبر التطبيق).",
    )

    class Meta:
        verbose_name = "بلاغ تطبيق"
        verbose_name_plural = "بلاغات التطبيق"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["region", "created_at"]),
            models.Index(fields=["created_by", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"بلاغ #{self.pk} - {self.patient_name}"


def clean(self) -> None:
    # منطق الاعتماد بين الحقول
    if self.called_ambulance and not self.ambulance_called_by:
        raise ValidationError({"ambulance_called_by": "حدد (أنا/شخص آخر) عند اختيار طلب إسعاف."})
    if not self.called_ambulance and self.ambulance_called_by:
        raise ValidationError({"ambulance_called_by": "لا يمكن تحديد هذا الحقل بدون اختيار طلب إسعاف."})