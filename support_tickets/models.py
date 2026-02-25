from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .services.time_metrics import between

logger = logging.getLogger(__name__)

SUPPORT_GROUP_NAME = "ITS"  # اسم مجموعة الدعم الفني


# =========================
# Enums / Constants
# =========================

class TicketSource(models.TextChoices):
    SYSTEM = "SYSTEM", "النظام"
    MOBILE = "MOBILE", "تطبيق الجوال"


class TicketKind(models.TextChoices):
    INC = "INC", "عطل / مشكلة"
    REQ = "REQ", "طلب خدمة"


# =========================
# Catalog Models
# =========================

class TicketStatusCatalog(models.Model):
    """كتلوج حالات التذكرة (بدلاً من TextChoices)."""

    code = models.CharField("الرمز", max_length=40, primary_key=True, serialize=False)
    name = models.CharField("اسم الحالة", max_length=150)
    is_active = models.BooleanField("مفعّل", default=True)

    # إذا كانت الحالة تعليق (Paused) يجب اختيار سبب من كتلوج الأسباب
    requires_pause_reason = models.BooleanField("يتطلب سبب تعليق", default=False)

    # علامات لتسهيل المنطق/العرض
    is_closed = models.BooleanField("مغلقة نهائياً", default=False)
    sort_order = models.PositiveIntegerField("ترتيب", default=100)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "حالة تذكرة"
        verbose_name_plural = "كتلوج حالات التذاكر"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class TicketPauseReasonCatalog(models.Model):
    """كتلوج أسباب تعليق التذكرة."""

    code = models.CharField("الرمز", max_length=40, primary_key=True, serialize=False)
    name = models.CharField("سبب التعليق", max_length=200, unique=True)

    is_active = models.BooleanField("مفعّل", default=True)
    sort_order = models.PositiveIntegerField("ترتيب", default=100)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "سبب تعليق"
        verbose_name_plural = "كتلوج أسباب تعليق التذكرة"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class TicketSolutionCatalog(models.Model):
    """كتلوج الحلول (قسم معلومات الحل)."""

    name = models.CharField("نوع الحل", max_length=200, unique=True)
    is_active = models.BooleanField("مفعّل", default=True)
    sort_order = models.PositiveIntegerField("ترتيب", default=100)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "حل"
        verbose_name_plural = "كتلوج الحلول"

    def __str__(self) -> str:
        return self.name


class TicketMainCategory(models.Model):
    """كتلوج التصنيف الرئيسي (مفصول حسب kind: REQ/INC)."""

    kind = models.CharField("نوع الكتلوج", max_length=5, choices=TicketKind.choices, db_index=True)
    name = models.CharField("اسم التصنيف الرئيسي", max_length=150)
    is_active = models.BooleanField("مفعّل", default=True)

    # SLA الافتراضي للتصنيف الرئيسي (بالدقائق) — يمكن احتسابه من يوم/ساعات عند الإدخال
    sla_minutes = models.PositiveIntegerField("SLA (بالدقائق) للتصنيف الرئيسي", default=60)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        unique_together = (("kind", "name"),)
        ordering = ["kind", "name"]
        verbose_name = "تصنيف رئيسي"
        verbose_name_plural = "التصنيفات الرئيسية"

    def __str__(self) -> str:
        return f"{self.kind} - {self.name}"


class TicketSubCategory(models.Model):
    """كتلوج التصنيف الفرعي المرتبط بالرئيسي."""

    main_category = models.ForeignKey(
        TicketMainCategory,
        on_delete=models.CASCADE,
        related_name="sub_categories",
        verbose_name="التصنيف الرئيسي",
    )
    name = models.CharField("اسم التصنيف الفرعي", max_length=150)
    is_active = models.BooleanField("مفعّل", default=True)

    # SLA خاص للفرعي (إن تُرك فارغ => يعتمد SLA الرئيسي)
    sla_minutes_override = models.PositiveIntegerField("SLA (بالدقائق) للفرعي (اختياري)", blank=True, null=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        unique_together = (("main_category", "name"),)
        ordering = ["main_category__kind", "main_category__name", "name"]
        verbose_name = "تصنيف فرعي"
        verbose_name_plural = "التصنيفات الفرعية"

    def __str__(self) -> str:
        return f"{self.main_category.kind} - {self.main_category.name} / {self.name}"

    def effective_sla_minutes(self) -> int:
        return int(self.sla_minutes_override or self.main_category.sla_minutes)


class TicketSequence(models.Model):
    """تسلسل أكواد التذاكر لضمان REQ/INC متسلسل (REQ000001 / INC000001)."""

    prefix = models.CharField("البادئة", max_length=10, unique=True, db_index=True)
    last_number = models.PositiveIntegerField("آخر رقم", default=0)

    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        ordering = ["prefix"]
        verbose_name = "تسلسل التذاكر"
        verbose_name_plural = "تسلسلات أرقام التذاكر"

    def __str__(self) -> str:
        return f"{self.prefix} -> {self.last_number}"


# =========================
# Ticket Models
# =========================
@property
def created_by_name(self) -> str:
    # غيّر أسماء الحقول حسب الموجود عندك:
    u = getattr(self, "created_by", None) or getattr(self, "created_by_user", None) or getattr(self, "requester_user", None)
    if u:
        full = (u.get_full_name() or "").strip()
        return full or getattr(u, "username", "") or getattr(u, "email", "") or "—"
    # fallback لو ما فيه user
    return (getattr(self, "requester_name", "") or "").strip() or (getattr(self, "requester_email", "") or "").strip() or "—"
class SupportTicket(models.Model):
    """
    الترميز الجديد (متسلسل):
    - إذا kind=REQ => REQ000001 ...
    - إذا kind=INC => INC000001 ...
    """

    code = models.CharField("رقم البلاغ", max_length=20, unique=True, db_index=True)

    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="support_tickets",
        verbose_name="مقدم التذكرة",
    )

    # Snapshot (يظهر تلقائياً من حساب المستخدم عند الإنشاء)
    requester_name = models.CharField("اسم مقدم التذكرة", max_length=200, blank=True)
    requester_national_id = models.CharField("رقم الهوية", max_length=50, blank=True)
    requester_phone = models.CharField("رقم الجوال", max_length=50, blank=True)
    requester_email = models.EmailField("البريد الإلكتروني", blank=True)

    source = models.CharField("تم الرفع عن طريق", max_length=10, choices=TicketSource.choices, default=TicketSource.SYSTEM)

    # يُحدد تلقائياً بناءً على main_category.kind
    kind = models.CharField("نوع البلاغ", max_length=5, choices=TicketKind.choices, editable=False, db_index=True)

    main_category = models.ForeignKey(
        TicketMainCategory,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="التصنيف الرئيسي",
    )
    sub_category = models.ForeignKey(
        TicketSubCategory,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="التصنيف الفرعي",
    )

    description = models.TextField("وصف المشكلة/الطلب", blank=True)
    image = models.ImageField("صورة (اختياري)", upload_to="support_tickets/%Y/%m/", blank=True, null=True)

    # مجموعة الإسناد (منطقة المستخدم) — للصلاحيات العليا تظهر جميع المناطق
    region = models.ForeignKey(
        "regions.Region",  # lazy import (يتطلب وجود app regions بالمشروع)
        on_delete=models.PROTECT,
        related_name="support_tickets",
        verbose_name="منطقة/مجموعة الإسناد",
        blank=True,
        null=True,
    )

    # الإسناد لموظف دعم فني (يُفضّل أن يكون ضمن نفس المنطقة)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="assigned_support_tickets",
        verbose_name="الإسناد (موظف الدعم الفني)",
        blank=True,
        null=True,
    )
    assigned_at = models.DateTimeField("وقت الإسناد", blank=True, null=True)

    # الحالة من كتلوج خاص
    status = models.ForeignKey(
        TicketStatusCatalog,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="حالة التذكرة",
    )

    # في حال تم اختيار التعليق يجب اختيار السبب من الكتلوج
    pause_reason = models.ForeignKey(
        TicketPauseReasonCatalog,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="سبب التعليق",
        blank=True,
        null=True,
    )

    # قسم معلومات الحل
    solution_catalog = models.ForeignKey(
        TicketSolutionCatalog,
        on_delete=models.PROTECT,
        related_name="tickets",
        verbose_name="نوع الحل (كتلوج)",
        blank=True,
        null=True,
    )
    
    solution_notes = models.TextField("ملاحظات الحل", blank=True)

    created_at = models.DateTimeField("وقت الاستلام/الإنشاء", auto_now_add=True)
    last_status_changed_at = models.DateTimeField("وقت تعديل الحالة", blank=True, null=True)
    first_response_at = models.DateTimeField("وقت أول رد", blank=True, null=True)
    closed_at = models.DateTimeField("وقت الإغلاق", blank=True, null=True)

    # SLA / Deadline
    sla_minutes = models.PositiveIntegerField("SLA المعتمد (بالدقائق)", default=60)
    deadline_at = models.DateTimeField("موعد الاستحقاق (Deadline)", blank=True, null=True)

    
    class Meta:
        ordering = ["-created_at"]
        verbose_name = "تذكرة دعم فني"
        verbose_name_plural = "تذاكر الدعم الفني"

    def __str__(self) -> str:
        status_name = getattr(self.status, "name", "") if self.status_id else ""
        return f"{self.code} - {status_name}"

    # -----------------------
    # Derived helpers
    # -----------------------
    def _desired_prefix(self) -> str:
        return "REQ" if self.kind == TicketKind.REQ else "INC"

    @transaction.atomic
    def ensure_code(self) -> None:
        if self.code:
            return
        prefix = self._desired_prefix()
        from .services.ticket_codes import next_sequential_ticket_code
        self.code = next_sequential_ticket_code(prefix=prefix)

    def _ensure_deadline(self) -> None:
        base = self.created_at or timezone.now()
        minutes = int(self.sla_minutes or 60)
        self.deadline_at = base + timedelta(minutes=minutes)

    @staticmethod
    def _sla_stops_during_pause() -> bool:
        return bool(getattr(settings, "SUPPORT_TICKETS_SLA_STOP_DURING_PAUSE", False))

    # -----------------------
    # Validation / Bootstrapping
    # -----------------------
    def _snapshot_requester_fields(self) -> None:
        """املأ بيانات مقدم التذكرة تلقائياً (اسم/هوية/جوال/ايميل) من حساب المستخدم إن توفرت."""
        u = self.requester
        if not u:
            return

        # name
        name = (
            getattr(u, "get_full_name", lambda: "")() or
            getattr(u, "full_name", "") or
            getattr(u, "name", "") or
            getattr(u, "username", "")
        )
        if not self.requester_name:
            self.requester_name = (name or "").strip()

        # national id / phone (قد تختلف أسماء الحقول حسب مشروعك)
        if not self.requester_national_id:
            self.requester_national_id = (
                getattr(u, "national_id", "") or getattr(u, "id_number", "") or getattr(u, "nationalId", "") or ""
            )

        if not self.requester_phone:
            self.requester_phone = (
                getattr(u, "phone", "") or getattr(u, "mobile", "") or getattr(u, "phone_number", "") or ""
            )

        if not self.requester_email:
            self.requester_email = (getattr(u, "email", "") or "").strip()

        # region (إن كان user لديه منطقة)
        if self.region_id is None:
            region = getattr(u, "region", None)
            if getattr(region, "pk", None):
                self.region = region

    def clean(self) -> None:
        # 1) تحقق من علاقة الرئيسي/الفرعي
        if self.sub_category_id and self.main_category_id:
            if self.sub_category.main_category_id != self.main_category_id:
                raise ValidationError({"sub_category": "التصنيف الفرعي لا يتبع التصنيف الرئيسي المختار."})

        # 2) تحديد kind من الكتلوج
        if self.main_category_id:
            self.kind = self.main_category.kind

        # 3) تحديد SLA المعتمد
        if self.sub_category_id:
            self.sla_minutes = self.sub_category.effective_sla_minutes()
        elif self.main_category_id:
            self.sla_minutes = int(self.main_category.sla_minutes or 60)

        # 4) قواعد الحالة/التعليق
        if self.status_id:
            if self.status.requires_pause_reason:
                if not self.pause_reason_id:
                    raise ValidationError({"pause_reason": "يجب اختيار سبب التعليق من الكتلوج عند تعليق التذكرة."})
            else:
                # لا نخزن سبب تعليق لو الحالة ليست تعليق
                self.pause_reason = None

        # 5) قواعد الحل
        if self.solution_catalog_id:
            if not (self.solution_notes or "").strip():
                raise ValidationError({"solution_notes": "ملاحظات الحل إلزامية عند اختيار نوع الحل من الكتلوج."})

        # 6) اغلاق نهائي
        if self.status_id and self.status.is_closed:
            if not self.closed_at:
                # لا نرفع ValidationError هنا حتى لا نعطل workflow الذي يضبط closed_at لاحقاً
                pass

    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Snapshot requester + kind/sla
        if self.requester_id:
            self._snapshot_requester_fields()

        # Ensure kind/sla computed
        if self.main_category_id:
            self.kind = self.main_category.kind
        if self.sub_category_id:
            self.sla_minutes = self.sub_category.effective_sla_minutes()
        elif self.main_category_id:
            self.sla_minutes = int(self.main_category.sla_minutes or 60)

        # Ensure code and deadline
        if is_new:
            self.ensure_code()

        super().save(*args, **kwargs)

        if is_new:
            # deadline after created_at is available
            if not self.deadline_at:
                self._ensure_deadline()
                super().save(update_fields=["deadline_at"])

    # -----------------------
    # SLA / Metrics
    # -----------------------
    def total_paused_seconds(self, until: Optional[timezone.datetime] = None) -> int:
        until = until or timezone.now()
        total = 0
        for p in self.pauses.all():
            total += p.duration_seconds(until=until)
        return int(total)

    def effective_deadline_at(self, at: Optional[timezone.datetime] = None) -> Optional[timezone.datetime]:
        if not self.deadline_at:
            return None
        if not self._sla_stops_during_pause():
            return self.deadline_at

        at = at or timezone.now()
        point = self.closed_at or at
        paused_seconds = self.total_paused_seconds(until=point)
        return self.deadline_at + timedelta(seconds=int(paused_seconds))

    def is_overdue(self, at: Optional[timezone.datetime] = None) -> bool:
        at = at or timezone.now()
        eff = self.effective_deadline_at(at=at)
        if not eff:
            return False
        point = self.closed_at or at
        return point > eff and not (self.status.is_closed if self.status_id else False)

    def overdue_seconds(self, at: Optional[timezone.datetime] = None) -> int:
        at = at or timezone.now()
        eff = self.effective_deadline_at(at=at)
        if not eff:
            return 0
        point = self.closed_at or at
        if point <= eff:
            return 0
        return int((point - eff).total_seconds())

    # زمن أول رد / زمن الحل / زمن الإغلاق ... (ثواني)
    def t_first_reply_seconds(self) -> int:
        return between(self.created_at, self.first_response_at)

    def t_solution_seconds(self) -> int:
        # الحل يعتبر عند تعبئة معلومات الحل أو عند الإغلاق — هنا نعتمد closed_at إن وُجد
        return between(self.created_at, self.closed_at)

    def t_close_seconds(self) -> int:
        return between(self.created_at, self.closed_at)


class TicketStatusLog(models.Model):
    """سجل تغييرات الحالة لأغراض SLA (زمن تعديل الحالة) والتدقيق."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="status_logs")
    from_status = models.ForeignKey(
        TicketStatusCatalog,
        on_delete=models.PROTECT,
        related_name="from_logs",
        verbose_name="من حالة",
        blank=True,
        null=True,
    )
    to_status = models.ForeignKey(
        TicketStatusCatalog,
        on_delete=models.PROTECT,
        related_name="to_logs",
        verbose_name="إلى حالة",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="ticket_status_changes",
        verbose_name="تم التغيير بواسطة",
        blank=True,
        null=True,
    )
    changed_at = models.DateTimeField("وقت التغيير", default=timezone.now)

    class Meta:
        ordering = ["-changed_at"]
        verbose_name = "سجل حالة التذكرة"
        verbose_name_plural = "سجلات حالات التذاكر"

    def __str__(self) -> str:
        return f"{self.ticket.code} {self.from_status_id}->{self.to_status_id} @ {self.changed_at}"


class TicketPause(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="pauses")
    reason = models.ForeignKey(
        TicketPauseReasonCatalog,
        on_delete=models.PROTECT,
        related_name="pauses",
        verbose_name="سبب التعليق",
    )
    started_at = models.DateTimeField("بدأ التعليق", default=timezone.now)
    ended_at = models.DateTimeField("انتهى التعليق", blank=True, null=True)

    class Meta:
        ordering = ["-started_at"]
        verbose_name = "تعليق تذكرة"
        verbose_name_plural = "تعليقات التذاكر (إيقاف مؤقت)"

    def __str__(self) -> str:
        return f"{self.ticket.code} - {self.reason}"

    def duration_seconds(self, until: Optional[timezone.datetime] = None) -> int:
        until = until or timezone.now()
        end = self.ended_at or until
        if end < self.started_at:
            return 0
        return int((end - self.started_at).total_seconds())

    def close(self) -> None:
        if not self.ended_at:
            self.ended_at = timezone.now()


class TicketComment(models.Model):
    """قسم التواصل: الردود بين الدعم الفني والمستخدم + التاريخ والوقت."""

    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ticket_comments")
    body = models.TextField("نص التعليق/الرد")
    created_at = models.DateTimeField("تاريخ ووقت الرد", auto_now_add=True)

    # رد دعم فني؟ (لتحديد أول رد وزمنه)
    is_support_reply = models.BooleanField("رد دعم فني", default=False)

    # تعليق داخلي (لا يظهر للمستخدم) — احتياطي، الافتراضي يظهر للطرفين
    is_internal = models.BooleanField("تعليق داخلي", default=False)

    class Meta:
        ordering = ["created_at"]
        verbose_name = "تعليق على تذكرة"
        verbose_name_plural = "تعليقات التذاكر"

    def __str__(self) -> str:
        return f"{self.ticket.code} - {self.author_id}"

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new and self.is_support_reply:
            # أول رد + تحويل لحالة قيد العمل إذا لم تكن مغلقة
            SupportTicket.objects.filter(pk=self.ticket_id, first_response_at__isnull=True).update(
                first_response_at=timezone.now(),
            )

            # محاولة تحويل الحالة تلقائياً إلى "قيد العمل" إذا كان هناك كود IN_PROGRESS بالكتلوج
            try:
                in_progress = TicketStatusCatalog.objects.filter(code="IN_PROGRESS", is_active=True).first()
                if in_progress:
                    SupportTicket.objects.filter(pk=self.ticket_id).update(status=in_progress)
            except Exception:
                # لا نكسر الحفظ بسبب إعدادات الكتلوج
                pass