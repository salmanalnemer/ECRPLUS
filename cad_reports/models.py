from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator



class CaseType(models.Model):
    """كتلوج أنواع الحالات (يُستخدم في بلاغات CAD)."""

    name = models.CharField("اسم نوع الحالة", max_length=200, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "نوع حالة (CAD)"
        verbose_name_plural = "كتلوج أنواع الحالات (CAD)"
        ordering = ["name"]

    def __str__(self) -> str:  # pragma: no cover
        return self.name


class CADReport(models.Model):
    """بلاغ CAD.

    المتطلبات حسب وصفك:
    - إدخال رقم البلاغ CAD
    - عدد المصابين
    - نوع الحالة (من الكتلوج)
    - درجة الخطورة
    - العمر
    - واعي/غير واعي
    - تفاصيل البلاغ (يدوي)
    - إدخال الموقع من الخريطة (Lat/Lng)
    - أزمنة الأحداث:
        1) وقت إنشاء البلاغ (auto)
        2) وقت الترحيل (عند الضغط على زر الترحيل)
        3) وقت قبول المستجيب (من التطبيق)
        4) وقت الوصول (من التطبيق)
      ثم حساب إجمالي زمن الاستجابة.
    - منشئ البلاغ (المرحل)
    """

    class Severity(models.TextChoices):
        SIMPLE = "simple", "بسيطة"
        MEDIUM = "medium", "متوسطة"
        CRITICAL = "critical", "حرجة"

    cad_number = models.CharField(
        "رقم البلاغ CAD",
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(
                regex=r'^\d+$',
                message="رقم البلاغ يجب أن يكون أرقام فقط"
            )
          ],
        )
    injured_count = models.PositiveIntegerField("عدد المصابين", default=0)
    case_type = models.ForeignKey(
        "cad_reports.CaseType",
        on_delete=models.PROTECT,
        related_name="reports",
        verbose_name="نوع الحالة",
    )
    severity = models.CharField(
        "درجة الخطورة",
        max_length=20,
        choices=Severity.choices,
        default=Severity.MEDIUM,
        db_index=True,
    )

    age = models.PositiveIntegerField("العمر", null=True, blank=True)
    is_conscious = models.BooleanField("واعي؟", default=True)
    details = models.TextField("تفاصيل البلاغ", blank=True)

    # موقع البلاغ من الخريطة
    latitude = models.FloatField("خط العرض", null=True, blank=True)
    longitude = models.FloatField("خط الطول", null=True, blank=True)
    location_text = models.CharField(
        "وصف الموقع",
        max_length=255,
        blank=True,
        help_text="اختياري: عنوان/وصف نصي للموقع",
    )

    # المنشئ (المرحل)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cad_created_reports",
        verbose_name="المرحل",
    )

    # المستجيب المُعيّن للبلاغ (يتم اختياره من الخريطة عند الترحيل)
    assigned_responder = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cad_assigned_reports",
        verbose_name="المستجيب المُعيّن",
        null=True,
        blank=True,
    )

    # المنطقة (لتسهيل الفلترة — تُملأ تلقائياً من المستخدم إن وُجد)
    region = models.ForeignKey(
        "regions.Region",
        on_delete=models.PROTECT,
        related_name="cad_reports",
        verbose_name="المنطقة",
        null=True,
        blank=True,
    )

    # أزمنة الأحداث
    created_at = models.DateTimeField("وقت إنشاء البلاغ", auto_now_add=True)
    dispatched_at = models.DateTimeField("وقت الترحيل", null=True, blank=True)
    accepted_at = models.DateTimeField("وقت قبول المستجيب", null=True, blank=True)
    arrived_at = models.DateTimeField("وقت الوصول", null=True, blank=True)

    # مصدر تحديث الأوقات (للتفريق بين التطبيق والويب عند التعطل)
    class TimeSource(models.TextChoices):
        UNKNOWN = "unknown", "غير محدد"
        MOBILE = "mobile", "تطبيق المستجيب"
        WEB_MANUAL = "web_manual", "يدوي (لوحة الوِب)"

    dispatched_source = models.CharField(
        "مصدر وقت الترحيل",
        max_length=20,
        choices=TimeSource.choices,
        default=TimeSource.WEB_MANUAL,
    )
    accepted_source = models.CharField(
        "مصدر وقت القبول",
        max_length=20,
        choices=TimeSource.choices,
        default=TimeSource.UNKNOWN,
    )
    arrived_source = models.CharField(
        "مصدر وقت الوصول",
        max_length=20,
        choices=TimeSource.choices,
        default=TimeSource.UNKNOWN,
    )

    accepted_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cad_accepted_set_reports",
        verbose_name="تم تسجيل القبول بواسطة",
        null=True,
        blank=True,
    )
    arrived_set_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cad_arrived_set_reports",
        verbose_name="تم تسجيل الوصول بواسطة",
        null=True,
        blank=True,
    )

    # إغلاق البلاغ
    # - يدوي (من لوحة الوِب)
    # - يدوي (من جوال المستجيب)
    # - آلي (اختياري: عند الوصول أو حسب إعدادات)
    is_closed = models.BooleanField("مغلق؟", default=False, db_index=True)
    closed_at = models.DateTimeField("وقت الإغلاق", null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cad_closed_reports",
        verbose_name="أُغلق بواسطة",
        null=True,
        blank=True,
    )
    closed_source = models.CharField(
        "مصدر الإغلاق",
        max_length=20,
        choices=(
            ("web_manual", "يدوي (لوحة الوِب)"),
            ("mobile_manual", "يدوي (جوال المستجيب)"),
            ("auto", "آلي"),
        ),
        default="web_manual",
    )

    # مدد محسوبة
    time_to_dispatch = models.DurationField("الزمن حتى الترحيل", null=True, blank=True)
    time_to_accept = models.DurationField("الزمن حتى القبول", null=True, blank=True)
    time_to_arrive = models.DurationField("الزمن حتى الوصول", null=True, blank=True)
    total_response_time = models.DurationField("إجمالي زمن الاستجابة", null=True, blank=True)

    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "بلاغ CAD"
        verbose_name_plural = "بلاغات CAD"
        ordering = ["-created_at"]
        permissions = [
            ("can_create_cad_report", "يمكنه إنشاء بلاغ CAD"),
            ("can_dispatch_cad_report", "يمكنه ترحيل بلاغ CAD"),
            ("can_accept_cad_report", "يمكنه قبول بلاغ CAD"),
            ("can_mark_arrived_cad_report", "يمكنه تسجيل الوصول لبلاغ CAD"),
            ("can_close_cad_report", "يمكنه إغلاق بلاغ CAD"),
            ("can_view_cad_report", "يمكنه عرض بلاغات CAD"),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"CAD #{self.cad_number}"

    # -------------------------
    # Validation
    # -------------------------
    def clean(self) -> None:
        super().clean()

        if self.age is not None and self.age > 130:
            raise ValidationError({"age": "العمر غير منطقي."})

        # لو تم إدخال أحد الإحداثيات يجب إدخال الآخر
        if (self.latitude is None) ^ (self.longitude is None):
            raise ValidationError(
                {
                    "latitude": "يجب إدخال خط العرض والطول معاً.",
                    "longitude": "يجب إدخال خط العرض والطول معاً.",
                }
            )

        # ترتيب الزمن (عشان ما نصير نكتب وقت قبول قبل الترحيل مثلاً)
        if self.dispatched_at and self.created_at and self.dispatched_at < self.created_at:
            raise ValidationError({"dispatched_at": "وقت الترحيل لا يمكن أن يكون قبل وقت إنشاء البلاغ."})
        if self.accepted_at and self.dispatched_at and self.accepted_at < self.dispatched_at:
            raise ValidationError({"accepted_at": "وقت القبول لا يمكن أن يكون قبل وقت الترحيل."})
        if self.arrived_at and self.accepted_at and self.arrived_at < self.accepted_at:
            raise ValidationError({"arrived_at": "وقت الوصول لا يمكن أن يكون قبل وقت القبول."})

        if self.is_closed:
            # وقت الإغلاق يمكن تعديله يدوياً عند الحاجة (تعطل التطبيق/النت)، ويُعيَّن تلقائياً إذا كان فارغاً
            if not self.closed_at:
                self.closed_at = timezone.now()
            if self.arrived_at and self.closed_at and self.closed_at < self.arrived_at:
                raise ValidationError({"closed_at": "وقت الإغلاق لا يمكن أن يكون قبل وقت الوصول."})

    # -------------------------
    # Computed durations
    # -------------------------
    @staticmethod
    def _safe_delta(a: timezone.datetime | None, b: timezone.datetime | None) -> timedelta | None:
        if not a or not b:
            return None
        if b < a:
            return None
        return b - a

    def _recompute_durations(self) -> None:
        """إعادة حساب مدد الأوقات وإجمالي زمن الاستجابة."""

        # 1) من الإنشاء إلى الترحيل
        self.time_to_dispatch = self._safe_delta(self.created_at, self.dispatched_at)

        # 2) من الترحيل إلى القبول
        self.time_to_accept = self._safe_delta(self.dispatched_at, self.accepted_at)

        # 3) من القبول إلى الوصول
        self.time_to_arrive = self._safe_delta(self.accepted_at, self.arrived_at)

        # الإجمالي = مجموع المدد الموجودة (كما طلبت: جمع الأوقات)
        total = timedelta(0)
        any_part = False
        for part in (self.time_to_dispatch, self.time_to_accept, self.time_to_arrive):
            if part is not None:
                total += part
                any_part = True
        self.total_response_time = total if any_part else None

    def save(self, *args, **kwargs):
        # املأ المنطقة تلقائياً من منشئ البلاغ إن وجدت
        if self.region_id is None and getattr(self.created_by, "region_id", None):
            self.region_id = self.created_by.region_id

        creating = self._state.adding
        super().save(*args, **kwargs)

        # بعد الحفظ: نعيد الحساب ثم نحفظ فقط الحقول المحسوبة إذا تغيّرت
        before = (self.time_to_dispatch, self.time_to_accept, self.time_to_arrive, self.total_response_time)
        self._recompute_durations()
        after = (self.time_to_dispatch, self.time_to_accept, self.time_to_arrive, self.total_response_time)

        if before != after:
            # ملاحظة: عند الإنشاء أول مرة، قد يكون created_at تم توليده للتو
            # لذا نعيد كتابة الحقول المحسوبة.
            super().save(
                update_fields=[
                    "time_to_dispatch",
                    "time_to_accept",
                    "time_to_arrive",
                    "total_response_time",
                    "updated_at",
                ]
            )

    # -------------------------
    # Event setters
    # -------------------------
    def mark_dispatched(
        self,
        when: timezone.datetime | None = None,
        *,
        by=None,
        source: str = "web_manual",
        force: bool = False,
    ) -> None:
        """تسجيل وقت الترحيل.

        - by: المستخدم الذي نفّذ الترحيل (اختياري)
        - source: mobile | web_manual | unknown
        - force: يسمح بالتعديل حتى لو كان الوقت مسجلاً مسبقاً
        """
        if self.dispatched_at and not force:
            return
        self.dispatched_at = when or timezone.now()
        if by is not None:
            # لا نضيف حقل dispatched_by لتجنّب تغيير واسع، نكتفي بتركه في التاريخ/الملاحظات إن لزم
            pass
        if source in {"mobile", "web_manual", "unknown"}:
            self.dispatched_source = source
        self.full_clean()
        self.save(update_fields=["dispatched_at", "dispatched_source", "updated_at"])

    def mark_accepted(
        self,
        when: timezone.datetime | None = None,
        *,
        by=None,
        source: str = "mobile",
        force: bool = False,
    ) -> None:
        """تسجيل وقت القبول/التحرك.

        الهدف: في حال تعطل التطبيق/النت يمكن للمرحل تعديل الوقت يدوياً من لوحة الويب.

        - by: من قام بتسجيل القبول (اختياري)
        - source: mobile | web_manual | unknown
        - force: يسمح بالتعديل حتى لو كان الوقت مسجلاً مسبقاً
        """
        if self.accepted_at and not force:
            return
        self.accepted_at = when or timezone.now()
        if by is not None:
            self.accepted_set_by = by
        if source in {"mobile", "web_manual", "unknown"}:
            self.accepted_source = source
        self.full_clean()
        self.save(update_fields=["accepted_at", "accepted_source", "accepted_set_by", "updated_at"])

    def mark_arrived(
        self,
        when: timezone.datetime | None = None,
        *,
        by=None,
        source: str = "mobile",
        force: bool = False,
    ) -> None:
        """تسجيل وقت الوصول/المباشرة.

        - by: من قام بتسجيل الوصول (اختياري)
        - source: mobile | web_manual | unknown
        - force: يسمح بالتعديل حتى لو كان الوقت مسجلاً مسبقاً
        """
        if self.arrived_at and not force:
            return
        self.arrived_at = when or timezone.now()
        if by is not None:
            self.arrived_set_by = by
        if source in {"mobile", "web_manual", "unknown"}:
            self.arrived_source = source
        self.full_clean()
        self.save(update_fields=["arrived_at", "arrived_source", "arrived_set_by", "updated_at"])

        # إغلاق آلي (اختياري): عند الوصول
        # تفعيله عبر settings.py: CAD_AUTO_CLOSE_ON_ARRIVE = True
        try:
            auto_close = bool(getattr(settings, "CAD_AUTO_CLOSE_ON_ARRIVE", False))
        except Exception:
            auto_close = False
        if auto_close and not self.is_closed:
            self.mark_closed(by=self.assigned_responder, source="auto")

    def mark_closed(
        self,
        when: timezone.datetime | None = None,
        by=None,
        source: str = "web_manual",
        force: bool = False,
    ) -> None:
        """إغلاق البلاغ وحفظ وقت الإغلاق.

        - when: وقت الإغلاق (افتراضي الآن)
        - by: المستخدم الذي أغلق البلاغ (اختياري)
        - source: web_manual | mobile_manual | auto
        """
        if self.is_closed and not force:
            return
        self.is_closed = True
        self.closed_at = when or timezone.now()
        if by is not None:
            self.closed_by = by
        if source in {"web_manual", "mobile_manual", "auto"}:
            self.closed_source = source
        self.full_clean()
        self.save(update_fields=["is_closed", "closed_at", "closed_by", "closed_source", "updated_at"])



class UserDeviceToken(models.Model):
    """FCM device token per user (for CAD mobile background alerts)."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="device_tokens",
    )
    token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} — {self.platform}"
