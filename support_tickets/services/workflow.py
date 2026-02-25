from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    SUPPORT_GROUP_NAME,
    SupportTicket,
    TicketComment,
    TicketPause,
    TicketPauseReasonCatalog,
    TicketSolutionCatalog,
    TicketStatusCatalog,
    TicketStatusLog,
)

logger = logging.getLogger(__name__)


def is_support(user) -> bool:
    """
    يعتبر المستخدم "دعم" إذا:
    - مسجل دخول
    - superuser
    - أو ضمن مجموعة الدعم المحددة في SUPPORT_GROUP_NAME
    - أو ضمن مجموعات نظام ECR المميزة (SYSADMIN / NEMSCC)
    """
    if not getattr(user, "is_authenticated", False):
        return False

    if getattr(user, "is_superuser", False):
        return True

    privileged_names = {SUPPORT_GROUP_NAME, "SYSADMIN", "NEMSCC"}
    try:
        return user.groups.filter(name__in=list(privileged_names)).exists()
    except Exception:
        return False


@dataclass(frozen=True)
class WorkflowResult:
    ok: bool
    message: str
    ticket_id: int
    extra: dict[str, Any] | None = None


def _get_status(code: str) -> TicketStatusCatalog:
    st = TicketStatusCatalog.objects.filter(code=code, is_active=True).first()
    if not st:
        raise ValidationError(f"حالة غير موجودة بالكتلوج: {code}")
    return st


class TicketWorkflow:
    """Workflow layer for SupportTicket operations (reply/pause/resume/close/assign/status).

    الهدف:
    - توحيد منطق الانتقالات (Status transitions)
    - توحيد الصلاحيات
    - تسجيل Logs
    - ضمان atomicity للعمليات
    """

    # -----------------------
    # Guards
    # -----------------------
    @staticmethod
    def _require_authenticated(user) -> None:
        if not getattr(user, "is_authenticated", False):
            raise PermissionDenied("يجب تسجيل الدخول.")

    @staticmethod
    def _require_support(user) -> None:
        TicketWorkflow._require_authenticated(user)
        if not is_support(user):
            raise PermissionDenied("هذه العملية مخصصة لموظفي الدعم الفني فقط.")

    @staticmethod
    def _require_ticket_access(user, ticket: SupportTicket) -> None:
        TicketWorkflow._require_authenticated(user)
        if is_support(user):
            return
        if ticket.requester_id != getattr(user, "id", None):
            raise PermissionDenied("لا تملك صلاحية على هذه التذكرة.")

    @staticmethod
    def _ensure_not_closed(ticket: SupportTicket) -> None:
        if ticket.status_id and ticket.status.is_closed:
            raise ValidationError("التذكرة مغلقة ولا يمكن تعديلها.")

    # -----------------------
    # Internal helpers
    # -----------------------
    @staticmethod
    def _log_status_change(*, ticket: SupportTicket, from_status: Optional[TicketStatusCatalog], to_status: TicketStatusCatalog, user) -> None:
        TicketStatusLog.objects.create(
            ticket=ticket,
            from_status=from_status,
            to_status=to_status,
            changed_by=getattr(user, "is_authenticated", False) and user or None,
            changed_at=timezone.now(),
        )

    @staticmethod
    def _set_status(*, ticket: SupportTicket, to_status: TicketStatusCatalog, user, pause_reason: TicketPauseReasonCatalog | None = None) -> None:
        from_status = ticket.status if ticket.status_id else None

        # requirements
        if to_status.requires_pause_reason and not pause_reason:
            raise ValidationError("يجب اختيار سبب التعليق من الكتلوج عند تعليق التذكرة.")

        ticket.status = to_status
        ticket.pause_reason = pause_reason if to_status.requires_pause_reason else None
        ticket.last_status_changed_at = timezone.now()
        ticket.save(update_fields=["status", "pause_reason", "last_status_changed_at"])

        TicketWorkflow._log_status_change(ticket=ticket, from_status=from_status, to_status=to_status, user=user)

    # -----------------------
    # Actions
    # -----------------------
    @staticmethod
    @transaction.atomic
    def add_comment(*, user, ticket: SupportTicket, body: str, is_internal: bool = False) -> WorkflowResult:
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        text = (body or "").strip()
        if not text:
            raise ValidationError("نص الرد/التعليق مطلوب.")

        TicketComment.objects.create(
            ticket=ticket,
            author=user,
            body=text,
            is_support_reply=is_support(user),
            is_internal=bool(is_internal),
        )

        # أول رد من الدعم
        if is_support(user) and not ticket.first_response_at:
            ticket.first_response_at = timezone.now()
            ticket.save(update_fields=["first_response_at"])

        # تحويل إلى قيد العمل إن كانت الحالة OPEN
        try:
            open_st = _get_status("OPEN")
            in_prog = _get_status("IN_PROGRESS")
            if ticket.status_id == open_st.id:
                TicketWorkflow._set_status(ticket=ticket, to_status=in_prog, user=user)
        except Exception:
            pass

        return WorkflowResult(ok=True, message="تمت إضافة الرد.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def assign_ticket(*, user, ticket: SupportTicket, assignee) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        ticket.assignee = assignee
        if not ticket.assigned_at:
            ticket.assigned_at = timezone.now()
        ticket.save(update_fields=["assignee", "assigned_at"])

        return WorkflowResult(ok=True, message="تم إسناد التذكرة.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def pause_ticket(*, user, ticket: SupportTicket, reason_id: int) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        # لا نسمح بأكثر من Pause مفتوح
        if ticket.pauses.filter(ended_at__isnull=True).exists():
            raise ValidationError("التذكرة معلّقة بالفعل.")

        reason = TicketPauseReasonCatalog.objects.filter(pk=reason_id, is_active=True).first()
        if not reason:
            raise ValidationError("سبب التعليق غير صحيح أو غير مفعّل.")

        TicketPause.objects.create(ticket=ticket, reason=reason, started_at=timezone.now())

        paused_status = _get_status("PAUSED")
        TicketWorkflow._set_status(ticket=ticket, to_status=paused_status, user=user, pause_reason=reason)

        logger.info("Ticket paused: ticket=%s reason=%s by=%s", ticket.code, reason_id, user.id)
        return WorkflowResult(ok=True, message="تم تعليق التذكرة مؤقتًا.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def resume_ticket(*, user, ticket: SupportTicket) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        pause = ticket.pauses.filter(ended_at__isnull=True).order_by("-started_at").first()
        if not pause:
            raise ValidationError("لا يوجد تعليق مفتوح لاستئنافه.")

        pause.ended_at = timezone.now()
        pause.save(update_fields=["ended_at"])

        in_prog = _get_status("IN_PROGRESS")
        TicketWorkflow._set_status(ticket=ticket, to_status=in_prog, user=user)

        logger.info("Ticket resumed: ticket=%s by=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم استئناف التذكرة.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def change_status(*, user, ticket: SupportTicket, status_id: int, pause_reason_id: Optional[int] = None) -> WorkflowResult:
        """تغيير حالة التذكرة مع التحقق من كتلوج الحالة/الأسباب."""
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        st = TicketStatusCatalog.objects.filter(pk=status_id, is_active=True).first()
        if not st:
            raise ValidationError("الحالة غير صحيحة أو غير مفعّلة.")

        reason = None
        if st.requires_pause_reason:
            if not pause_reason_id:
                raise ValidationError("اختر سبب التعليق من الكتلوج.")
            reason = TicketPauseReasonCatalog.objects.filter(pk=pause_reason_id, is_active=True).first()
            if not reason:
                raise ValidationError("سبب التعليق غير صحيح أو غير مفعّل.")

            # افتح Pause
            if not ticket.pauses.filter(ended_at__isnull=True).exists():
                TicketPause.objects.create(ticket=ticket, reason=reason, started_at=timezone.now())
        else:
            # اقفل Pause المفتوح إن وُجد
            ticket.pauses.filter(ended_at__isnull=True).update(ended_at=timezone.now())

        TicketWorkflow._set_status(ticket=ticket, to_status=st, user=user, pause_reason=reason)
        return WorkflowResult(ok=True, message="تم تعديل الحالة.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def close_ticket(*, user, ticket: SupportTicket, solution_catalog_id: int, solution_notes: str) -> WorkflowResult:
        """إغلاق نهائي من الدعم (يجب اختيار نوع حل + ملاحظات حل)."""
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        sol = TicketSolutionCatalog.objects.filter(pk=solution_catalog_id, is_active=True).first()
        if not sol:
            raise ValidationError("نوع الحل غير صحيح أو غير مفعّل.")

        notes = (solution_notes or "").strip()
        if not notes:
            raise ValidationError("ملاحظات الحل إلزامية.")

        # اقفل أي pause مفتوح
        ticket.pauses.filter(ended_at__isnull=True).update(ended_at=timezone.now())

        ticket.solution_catalog = sol
        ticket.solution_notes = notes

        closed_status = _get_status("CLOSED")
        ticket.closed_at = timezone.now()
        ticket.save(update_fields=["solution_catalog", "solution_notes", "closed_at"])

        TicketWorkflow._set_status(ticket=ticket, to_status=closed_status, user=user)

        TicketComment.objects.create(
            ticket=ticket,
            author=user,
            body=f"✅ تم إغلاق التذكرة.\nنوع الحل: {sol}\nملاحظات: {notes}",
            is_support_reply=True,
            is_internal=False,
        )

        logger.info("Ticket closed: ticket=%s by=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم إغلاق التذكرة.", ticket_id=ticket.id)
