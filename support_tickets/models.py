from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .services.ticket_codes import generate_ticket_code
from .services.time_metrics import between

logger = logging.getLogger(__name__)

SUPPORT_GROUP_NAME = "ITS"  # اسم مجموعة الدعم الفني


class TicketSource(models.TextChoices):
    WEB = "WEB", "الموقع الإلكتروني"
    MOBILE = "MOBILE", "تطبيق الجوال"


class TicketKind(models.TextChoices):
    INC = "INC", "عطل / مشكلة"
    REQ = "REQ", "طلب خدمة"


class TicketStatus(models.TextChoices):
    OPEN = "OPEN", "مفتوحة"
    IN_PROGRESS = "IN_PROGRESS", "قيد المعالجة"
    PAUSED = "PAUSED", "معلّقة (مؤقت)"
    CLOSED = "CLOSED", "مغلقة"


class PauseReason(models.TextChoices):
    GENERAL_OUTAGE = "GENERAL_OUTAGE", "عطل عام وجاري الحل"
    ASK_REQUESTER = "ASK_REQUESTER", "استفسار من صاحب الطلب"
    HIGHER_PRIV = "HIGHER_PRIV", "صلاحية عليا"


# =========================
# Catalog Models (REQ / INC)
# =========================

class TicketMainCategory(models.Model):
    """كتلوج التصنيف الرئيسي (مفصول حسب kind: REQ/INC)."""

    kind = models.CharField("نوع الكتلوج", max_length=5, choices=TicketKind.choices, db_index=True)
    name = models.CharField("اسم التصنيف الرئيسي", max_length=150)
    is_active = models.BooleanField("مفعّل", default=True)

    # زمن SLA الافتراضي للتصنيف الرئيسي (بالدقائق)
    sla_minutes = models.PositiveIntegerField("SLA (بالدقائق) للتصنيف الرئيسي", default=60)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        unique_together = (("kind", "name"),)
        ordering = ["kind", "name"]

    def __str__(self) -> str:
        return f"{self.kind} - {self.name}"


class TicketSubCategory(models.Model):
    """كتلوج التصنيف الفرعي المرتبط بالرئيسي."""

    main_category = models.ForeignKey(
        TicketMainCategory, on_delete=models.CASCADE, related_name="sub_categories", verbose_name="التصنيف الرئيسي"
    )
    name = models.CharField("اسم التصنيف الفرعي", max_length=150)
    is_active = models.BooleanField("مفعّل", default=True)

    # SLA خاص للفرعي (إن تُرك فارغ => يعتمد SLA الرئيسي)
    sla_minutes_override = models.PositiveIntegerField(
        "SLA (بالدقائق) للفرعي (اختياري)", blank=True, null=True
    )

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        unique_together = (("main_category", "name"),)
        ordering = ["main_category__kind", "main_category__name", "name"]

    def __str__(self) -> str:
        return f"{self.main_category.kind} - {self.main_category.name} / {self.name}"

    def effective_sla_minutes(self) -> int:
        return int(self.sla_minutes_override or self.main_category.sla_minutes)


# =========================
# Ticket Models
# =========================

class SupportTicket(models.Model):
    """
    قاعدة الترميز:
    - إذا kind=REQ => REQ + 8 أرقام عشوائية
    - إذا kind=INC:
        - إذا source=MOBILE => ECR + 8 أرقام عشوائية
        - إذا source=WEB => INC + 8 أرقام عشوائية
    """

    code = models.CharField("رقم التذكرة", max_length=16, unique=True, db_index=True)

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_tickets",
        verbose_name="صاحب الطلب",
    )

    # موظف الدعم الفني (للمحاسبة والتقارير)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_support_tickets",
        verbose_name="موظف الدعم الفني",
        blank=True,
        null=True,
    )

    source = models.CharField("المصدر", max_length=10, choices=TicketSource.choices, default=TicketSource.WEB)

    # يُحدد تلقائياً بناءً على main_category.kind
    kind = models.CharField("النوع", max_length=5, choices=TicketKind.choices, editable=False, db_index=True)

    main_category = models.ForeignKey(
        TicketMainCategory,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="تصنيف البلاغ الرئيسي",
    )
    sub_category = models.ForeignKey(
        TicketSubCategory,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="تصنيف البلاغ الفرعي",
    )

    description = models.TextField("وصف المشكلة", blank=True)
    image = models.ImageField("صورة (اختياري)", upload_to="support_tickets/%Y/%m/", blank=True, null=True)

    status = models.CharField("الحالة", max_length=20, choices=TicketStatus.choices, default=TicketStatus.OPEN)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    first_response_at = models.DateTimeField("أول رد من الدعم", blank=True, null=True)
    closed_at = models.DateTimeField("تاريخ الإغلاق", blank=True, null=True)

    # SLA / Deadline
    sla_minutes = models.PositiveIntegerField("SLA المعتمد (بالدقائق)", default=60)
    deadline_at = models.DateTimeField("موعد الاستحقاق (Deadline)", blank=True, null=True)

    # تسهيل العرض فقط (آخر سبب تعليق)
    last_pause_reason = models.CharField("سبب التعليق الأخير", max_length=30, choices=PauseReason.choices, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.code} - {self.get_status_display()}"

    def clean(self) -> None:
        # 1) تحقق من علاقة الرئيسي/الفرعي
        if self.sub_category_id and self.main_category_id:
            if self.sub_category.main_category_id != self.main_category_id:
                raise ValidationError({"sub_category": "التصنيف الفرعي لا يتبع التصنيف الرئيسي المختار."})

        # 2) تحديد kind من الكتلوج
        if self.main_category_id:
            self.kind = self.main_category.kind

        # 3) تحديد SLA المعتمد من الفرعي (إن وجد override) وإلا من الرئيسي
        if self.sub_category_id:
            self.sla_minutes = self.sub_category.effective_sla_minutes()
        elif self.main_category_id:
            self.sla_minutes = int(self.main_category.sla_minutes or 60)

        # 4) منطق الحالة مع التواريخ
        if self.status == TicketStatus.CLOSED and not self.closed_at:
            pass

    def _desired_prefix(self) -> str:
        if self.kind == TicketKind.REQ:
            return "REQ"
        if self.source == TicketSource.MOBILE:
            return "ECR"
        return "INC"

    @classmethod
    def _code_exists(cls, code: str) -> bool:
        return cls.objects.filter(code=code).exists()

    @transaction.atomic
    def ensure_code(self) -> None:
        if self.code:
            return
        prefix = self._desired_prefix()
        self.code = generate_ticket_code(prefix=prefix, exists_fn=self._code_exists, digits=8)

    def _ensure_deadline(self) -> None:
        base = self.created_at or timezone.now()
        minutes = int(self.sla_minutes or 60)
        self.deadline_at = base + timedelta(minutes=minutes)

    @staticmethod
    def _sla_stops_during_pause() -> bool:
        return bool(getattr(settings, "SUPPORT_TICKETS_SLA_STOP_DURING_PAUSE", False))

    def effective_deadline_at(self, at: timezone.datetime | None = None) -> timezone.datetime | None:
        if not self.deadline_at:
            return None
        if not self._sla_stops_during_pause():
            return self.deadline_at

        at = at or timezone.now()
        point = self.closed_at or at
        paused_seconds = self.total_paused_seconds(until=point)
        return self.deadline_at + timedelta(seconds=int(paused_seconds))

    def remaining_seconds(self, at: timezone.datetime | None = None) -> int:
        at = at or timezone.now()
        eff = self.effective_deadline_at(at=at)
        if not eff:
            return 0
        point = self.closed_at or at
        if point >= eff:
            return 0
        return int((eff - point).total_seconds())

    def _bootstrap_kind_and_sla(self) -> None:
        try:
            if self.main_category_id and self.main_category:
                self.kind = self.main_category.kind
        except Exception:
            pass

        try:
            if self.sub_category_id and self.sub_category:
                self.sla_minutes = int(self.sub_category.effective_sla_minutes())
            elif self.main_category_id and self.main_category:
                self.sla_minutes = int(self.main_category.sla_minutes or 60)
        except Exception:
            if not self.sla_minutes:
                self.sla_minutes = 60

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        self._bootstrap_kind_and_sla()

        if not self.code:
            self.ensure_code()

        self.full_clean()

        if is_new:
            super().save(*args, **kwargs)
            self._ensure_deadline()
            super().save(update_fields=["deadline_at"])
            return

        self._ensure_deadline()
        super().save(*args, **kwargs)

    def mark_closed(self) -> None:
        self.status = TicketStatus.CLOSED
        self.closed_at = timezone.now()

    def mark_first_response_if_needed(self) -> None:
        if not self.first_response_at:
            self.first_response_at = timezone.now()

    def total_paused_seconds(self, until: timezone.datetime | None = None) -> int:
        until = until or timezone.now()
        pauses = self.pauses.all()
        total = 0
        for p in pauses:
            total += p.duration_seconds(until=until)
        return max(0, total)

    def response_time_seconds(self) -> int:
        if not self.first_response_at:
            return 0
        raw = between(self.created_at, self.first_response_at)
        paused_before_first = self.total_paused_seconds(until=self.first_response_at)
        return max(0, raw - paused_before_first)

    def resolution_time_seconds(self) -> int:
        if not self.closed_at:
            return 0
        raw = between(self.created_at, self.closed_at)
        paused = self.total_paused_seconds(until=self.closed_at)
        return max(0, raw - paused)

    def is_overdue(self, at: timezone.datetime | None = None) -> bool:
        at = at or timezone.now()
        eff = self.effective_deadline_at(at=at)
        if not eff:
            return False
        point = self.closed_at or at
        return point > eff

    def overdue_seconds(self, at: timezone.datetime | None = None) -> int:
        at = at or timezone.now()
        eff = self.effective_deadline_at(at=at)
        if not eff:
            return 0
        point = self.closed_at or at
        if point <= eff:
            return 0
        return int((point - eff).total_seconds())


class TicketPause(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="pauses")
    reason = models.CharField("سبب التعليق", max_length=30, choices=PauseReason.choices)
    started_at = models.DateTimeField("بدأ التعليق", default=timezone.now)
    ended_at = models.DateTimeField("انتهى التعليق", blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.ticket.code} - {self.get_reason_display()}"

    def duration_seconds(self, until: timezone.datetime | None = None) -> int:
        until = until or timezone.now()
        end = self.ended_at or until
        if end < self.started_at:
            return 0
        return int((end - self.started_at).total_seconds())

    def close(self) -> None:
        if not self.ended_at:
            self.ended_at = timezone.now()


class TicketComment(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ticket_comments")
    body = models.TextField("نص التعليق")
    created_at = models.DateTimeField("تاريخ التعليق", auto_now_add=True)

    is_support_reply = models.BooleanField("رد دعم فني", default=False)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.ticket.code} - {self.author_id}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.is_support_reply:
            SupportTicket.objects.filter(pk=self.ticket_id, first_response_at__isnull=True).update(
                first_response_at=timezone.now(),
                status=TicketStatus.IN_PROGRESS,
            )