from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import (
    SUPPORT_GROUP_NAME,
    PauseReason,
    SupportTicket,
    TicketComment,
    TicketPause,
    TicketStatus,
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

    # superuser يسمح له دائماً
    if getattr(user, "is_superuser", False):
        return True

    # مجموعات الدعم/المميزة
    privileged_names = {"ITS", "SYSADMIN", "NEMSCC"}

    try:
        return user.groups.filter(name__in=list(privileged_names)).exists()
    except Exception:
        # احتياطاً: في حال user أو groups غير متوقعين
        return False


@dataclass(frozen=True)
class WorkflowResult:
    ok: bool
    message: str
    ticket_id: int
    extra: dict[str, Any] | None = None


class TicketWorkflow:
    """Workflow layer for SupportTicket operations (reply/pause/resume/close/comment).

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
        if not user.is_authenticated:
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
        if ticket.requester_id != user.id:
            raise PermissionDenied("لا تملك صلاحية على هذه التذكرة.")

    @staticmethod
    def _ensure_not_closed(ticket: SupportTicket) -> None:
        if ticket.status == TicketStatus.CLOSED:
            raise ValidationError("التذكرة مغلقة ولا يمكن تعديلها.")

    # -----------------------
    # Actions
    # -----------------------
    @staticmethod
    @transaction.atomic
    def add_requester_comment(*, user, ticket: SupportTicket, body: str) -> WorkflowResult:
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        body = (body or "").strip()
        if not body:
            raise ValidationError("نص التعليق مطلوب.")

        TicketComment.objects.create(
            ticket=ticket,
            author=user,
            body=body,
            is_support_reply=False,
        )

        logger.info("Requester comment added: ticket=%s user=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم إضافة التعليق.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def add_support_reply(*, user, ticket: SupportTicket, body: str) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        body = (body or "").strip()
        if not body:
            raise ValidationError("نص الرد مطلوب.")

        TicketComment.objects.create(
            ticket=ticket,
            author=user,
            body=body,
            is_support_reply=True,
        )

        # إذا كانت OPEN نرفعها لـ IN_PROGRESS (والـ first_response_at سيتم ضبطه في TicketComment.save())
        if ticket.status == TicketStatus.OPEN:
            SupportTicket.objects.filter(pk=ticket.id).update(status=TicketStatus.IN_PROGRESS)

        logger.info("Support reply added: ticket=%s support_user=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم إضافة رد الدعم.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def pause_ticket(*, user, ticket: SupportTicket, reason: str) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        if reason not in PauseReason.values:
            raise ValidationError("سبب التعليق غير صحيح.")

        # لا نسمح بأكثر من Pause مفتوح
        if ticket.pauses.filter(ended_at__isnull=True).exists():
            raise ValidationError("التذكرة معلّقة بالفعل.")

        TicketPause.objects.create(ticket=ticket, reason=reason, started_at=timezone.now())
        ticket.status = TicketStatus.PAUSED
        ticket.last_pause_reason = reason
        ticket.save(update_fields=["status", "last_pause_reason"])

        logger.info("Ticket paused: ticket=%s reason=%s by=%s", ticket.code, reason, user.id)
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

        if ticket.status == TicketStatus.PAUSED:
            ticket.status = TicketStatus.IN_PROGRESS
            ticket.save(update_fields=["status"])

        logger.info("Ticket resumed: ticket=%s by=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم استئناف التذكرة.", ticket_id=ticket.id)

    @staticmethod
    @transaction.atomic
    def close_ticket(*, user, ticket: SupportTicket, closing_note: Optional[str] = None) -> WorkflowResult:
        TicketWorkflow._require_support(user)
        TicketWorkflow._require_ticket_access(user, ticket)
        TicketWorkflow._ensure_not_closed(ticket)

        # اقفل أي pause مفتوح
        TicketPause.objects.filter(ticket=ticket, ended_at__isnull=True).update(ended_at=timezone.now())

        note = (closing_note or "").strip()
        if note:
            TicketComment.objects.create(
                ticket=ticket,
                author=user,
                body=f"ملاحظة الإغلاق: {note}",
                is_support_reply=True,
            )

        ticket.mark_closed()
        ticket.save(update_fields=["status", "closed_at"])

        logger.info("Ticket closed: ticket=%s by=%s", ticket.code, user.id)
        return WorkflowResult(ok=True, message="تم إغلاق التذكرة.", ticket_id=ticket.id)