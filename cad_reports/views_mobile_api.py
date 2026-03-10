from __future__ import annotations

import logging

from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404
from django.db import models

from rest_framework.exceptions import PermissionDenied
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from .services.fcm import send_fcm_to_tokens
from .models import CADReport, CADReportActivity, UserDeviceToken

logger = logging.getLogger(__name__)


def _user_display_name(user) -> str:
    try:
        full_name = (user.get_full_name() or "").strip()
        if full_name:
            return full_name
    except Exception:
        pass

    for attr in ("full_name", "name", "username"):
        try:
            value = getattr(user, attr, "")
            value = str(value).strip()
            if value:
                return value
        except Exception:
            pass

    return "مستخدم غير معروف"


def _log_activity(report: CADReport, *, user, kind: str, action: str, message: str = "") -> None:
    """سجل إجراء/ملاحظة في Timeline/Chat للبلاغ."""
    try:
        CADReportActivity.objects.create(
            report=report,
            user=user if getattr(user, "is_authenticated", False) else None,
            kind=kind,
            action=action,
            message=message or "",
        )
    except Exception:
        logger.exception("CADReportActivity create failed")


PRIVILEGED_GROUP_CODES = {"SYSADMIN", "NEMSCC"}


def _get_user_group_code(user) -> str:
    """
    جلب كود مجموعة المستخدم مع دعم:
    - user.group_code
    - user.user_group.code
    - Django auth groups
    """
    try:
        code = getattr(user, "group_code", None)
        if code:
            return str(code).strip().upper()
    except Exception:
        pass

    try:
        user_group = getattr(user, "user_group", None)
        if user_group:
            code = getattr(user_group, "code", None)
            if code:
                return str(code).strip().upper()
    except Exception:
        pass

    try:
        g = user.groups.first()
        if g and getattr(g, "name", None):
            return str(g.name).strip().upper()
    except Exception:
        pass

    return ""


def _ensure_can_act(report: CADReport, user, *, allow_unassigned: bool = False) -> None:
    """تحقق صلاحية المستجيب على البلاغ."""
    group = _get_user_group_code(user)
    if group in PRIVILEGED_GROUP_CODES:
        return

    user_region_id = _user_region_id(user)

    # السماح للبلاغات غير المعينة إذا كانت ضمن نفس المنطقة
    if allow_unassigned and report.assigned_responder_id is None:
        if user_region_id is None or report.region_id == user_region_id:
            return

    if report.assigned_responder_id != user.id:
        raise PermissionDenied("not_assigned_to_you")


def _get_report_by_cad_for_user(cad_number: str, user, *, allow_unassigned: bool = False) -> CADReport:
    report = get_object_or_404(CADReport, cad_number=str(cad_number).strip())
    _ensure_can_act(report, user, allow_unassigned=allow_unassigned)
    return report


def _status_of(report: CADReport) -> str:
    if report.is_closed:
        return "CLOSED"
    if report.arrived_at:
        return "ARRIVED"
    if report.accepted_at:
        return "ACCEPTED"
    if report.dispatched_at:
        return "DISPATCHED"
    return "OPEN"


def _user_region_id(user):
    return getattr(user, "region_id", None)


def _safe_str(value):
    return "-" if value is None else str(value)


def _serialize_report(report: CADReport) -> dict:
    return {
        "id": report.id,
        "cad_number": report.cad_number,
        "case_type": getattr(report.case_type, "name", None)
        or getattr(report.case_type, "name_ar", None)
        or str(report.case_type),

        "severity": report.severity,

        "created_at": report.created_at.isoformat()
        if report.created_at else None,

        "injured_count": report.injured_count,
        "age": report.age,
        "is_conscious": report.is_conscious,

        "location_text": report.location_text,
        "details": report.details,

        "latitude": report.latitude,
        "longitude": report.longitude,

        "region": _safe_str(
            getattr(report.region, "name_ar", None)
            or getattr(report.region, "name_en", None)
            or report.region
        ),

        "responder": _safe_str(
            getattr(report.assigned_responder, "get_full_name", lambda: None)()
            or getattr(report.assigned_responder, "username", None)
            or report.assigned_responder
        ),

        "status": _status_of(report),

        "dispatched_at": report.dispatched_at.isoformat()
        if report.dispatched_at else None,

        "accepted_at": report.accepted_at.isoformat()
        if report.accepted_at else None,

        "arrival_time": report.arrived_at.isoformat()
        if report.arrived_at else None,

        "is_closed": report.is_closed,

        "closed_at": report.closed_at.isoformat()
        if report.closed_at else None,

        "response_duration": report.response_duration
        if hasattr(report, "response_duration") else None,
    }


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_assigned_reports(request):
    """
    قائمة بلاغات CAD للتطبيق (JWT):
    - البلاغات المعينة للمستخدم
    - البلاغات غير المعينة ضمن منطقة المستخدم
    """
    user_region_id = _user_region_id(request.user)

    qs = (
        CADReport.objects
        .select_related("case_type", "region", "assigned_responder")
        .filter(is_closed=False)
    )

    if user_region_id:
        qs = qs.filter(
            models.Q(assigned_responder=request.user) |
            models.Q(assigned_responder__isnull=True, region_id=user_region_id)
        )
    else:
        qs = qs.filter(
            models.Q(assigned_responder=request.user) |
            models.Q(assigned_responder__isnull=True)
        )

    qs = qs.order_by("-created_at").distinct()

    results = [_serialize_report(report) for report in qs[:250]]

    return Response(
        {"ok": True, "count": len(results), "results": results},
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_accept(request, cad_number: str):
    """قبول البلاغ (موبايل) باستخدام JWT."""
    report = _get_report_by_cad_for_user(cad_number, request.user, allow_unassigned=True)
    try:
        if report.assigned_responder_id is None:
            report.assigned_responder = request.user
            report.full_clean()
            report.save(update_fields=["assigned_responder", "updated_at"])

        report.mark_accepted(by=request.user, source="mobile", force=True)
    except Exception as exc:
        logger.exception("cad_accept failed")
        return Response(
            {"ok": False, "error": "accept_failed", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _log_activity(
        report,
        user=request.user,
        kind=CADReportActivity.Kind.SYSTEM,
        action=CADReportActivity.Action.ACCEPTED,
        message="",
    )
    return Response({"ok": True, "cad_number": report.cad_number}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_reject(request, cad_number: str):
    """رفض البلاغ (موبايل) باستخدام JWT."""
    report = _get_report_by_cad_for_user(cad_number, request.user)
    rejector_name = _user_display_name(request.user)
    try:
        if report.accepted_at or report.arrived_at or report.closed_at:
            return Response(
                {
                    "ok": False,
                    "error": "cannot_reject_after_progress",
                    "detail": "لا يمكن رفض بلاغ بعد بدء المعالجة.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        report.assigned_responder = None
        report.full_clean()
        report.save(update_fields=["assigned_responder", "updated_at"])
    except Exception as exc:
        logger.exception("cad_reject failed")
        return Response(
            {"ok": False, "error": "reject_failed", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    reject_message = f"تم رفض البلاغ رقم {report.cad_number} من قبل {rejector_name}"
    _log_activity(
        report,
        user=request.user,
        kind=CADReportActivity.Kind.SYSTEM,
        action=CADReportActivity.Action.REJECTED,
        message=reject_message,
    )

    return Response({"ok": True, "message": reject_message}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_arrive(request, cad_number: str):
    """وصول/مباشرة البلاغ (موبايل) باستخدام JWT."""
    report = _get_report_by_cad_for_user(cad_number, request.user)
    try:
        report.mark_arrived(by=request.user, source="mobile", force=True)
    except Exception as exc:
        logger.exception("cad_arrive failed")
        return Response(
            {"ok": False, "error": "arrive_failed", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _log_activity(
        report,
        user=request.user,
        kind=CADReportActivity.Kind.SYSTEM,
        action=CADReportActivity.Action.ARRIVED,
        message="",
    )
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_close(request, cad_number: str):
    """إغلاق البلاغ (موبايل) باستخدام JWT."""
    report = _get_report_by_cad_for_user(cad_number, request.user)
    try:
        report.mark_closed(by=request.user, source="mobile_manual", force=True)
    except Exception as exc:
        logger.exception("cad_close failed")
        return Response(
            {"ok": False, "error": "close_failed", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _log_activity(
        report,
        user=request.user,
        kind=CADReportActivity.Kind.SYSTEM,
        action=CADReportActivity.Action.CLOSED,
        message="",
    )
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def register_device_token(request):
    """Register/refresh FCM device token for this user."""
    token = str(request.data.get("token") or "").strip()
    platform = str(request.data.get("platform") or "").strip()
    if not token:
        return Response({"ok": False, "error": "token_required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        UserDeviceToken.objects.update_or_create(
            token=token,
            defaults={"user": request.user, "platform": platform},
        )
    except Exception as exc:
        logger.exception("register_device_token failed")
        return Response(
            {"ok": False, "error": "save_failed", "detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_my_reports(request):
    """قائمة بلاغات CAD الخاصة بالمستجيب مع فلترة بالتاريخ."""
    qs = (
        CADReport.objects.select_related("case_type", "region", "assigned_responder")
        .filter(assigned_responder=request.user)
        .order_by("-created_at")
    )

    year = request.query_params.get("year")
    dfrom = request.query_params.get("from")
    dto = request.query_params.get("to")

    if year:
        try:
            qs = qs.filter(created_at__year=int(year))
        except Exception:
            pass

    if dfrom:
        d = parse_date(dfrom)
        if d:
            qs = qs.filter(created_at__date__gte=d)

    if dto:
        d = parse_date(dto)
        if d:
            qs = qs.filter(created_at__date__lte=d)

    data = []
    for report in qs[:500]:
        data.append(
            {
                "id": report.id,
                "cad_number": "" if report.cad_number is None else str(report.cad_number),
                "case_type": "" if getattr(report.case_type, "name", None) is None else str(getattr(report.case_type, "name", "")),
                "severity": "" if getattr(report, "severity", None) is None else str(getattr(report, "severity", "")),
                "status": _status_of(report),
                "created_at": report.created_at.isoformat() if getattr(report, "created_at", None) else None,
                "dispatched_at": report.dispatched_at.isoformat() if getattr(report, "dispatched_at", None) else None,
                "accepted_at": report.accepted_at.isoformat() if getattr(report, "accepted_at", None) else None,
                "arrived_at": report.arrived_at.isoformat() if getattr(report, "arrived_at", None) else None,
                "is_closed": bool(getattr(report, "is_closed", False)),
            }
        )

    return Response({"results": data, "count": qs.count()}, status=status.HTTP_200_OK)


@api_view(["GET", "POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_chat(request, cad_number: str):
    """Chat/Notes for mobile app (JWT) using CADReportActivity."""
    report = _get_report_by_cad_for_user(cad_number, request.user, allow_unassigned=True)

    if request.method == "GET":
        limit = request.GET.get("limit", "120")
        try:
            limit_i = int(limit)
        except Exception:
            limit_i = 120
        limit_i = max(1, min(limit_i, 300))

        qs = (
            CADReportActivity.objects.filter(report=report)
            .select_related("user")
            .order_by("-created_at")[:limit_i]
        )

        def _actor_name(user):
            if not user:
                return "النظام"

            try:
                full_name = user.get_full_name()
                if full_name and full_name.strip():
                    return full_name.strip()
            except Exception:
                pass

            for field in ("full_name", "name", "first_name", "username"):
                try:
                    value = getattr(user, field, None)
                    if value and str(value).strip():
                        return str(value).strip()
                except Exception:
                    continue

            return "مستخدم"

        items = []
        for activity in reversed(list(qs)):
            items.append(
                {
                    "id": activity.id,
                    "kind": activity.kind,
                    "action": activity.action,
                    "text": activity.message or "",
                    "created_at": activity.created_at.isoformat(),
                    "sender": _actor_name(activity.user) if activity.user_id else "النظام",
                }
            )
        return Response({"ok": True, "items": items}, status=status.HTTP_200_OK)

    msg = str(request.data.get("message") or "").strip()
    if not msg:
        return Response(
            {"ok": False, "error": "message_required"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    _log_activity(
        report,
        user=request.user,
        kind=CADReportActivity.Kind.MESSAGE,
        action=CADReportActivity.Action.NOTE,
        message=msg,
    )

    try:
        target_user_ids = set()

        # إذا المرسل هو المستجيب، أرسل للجهات الإدارية/المتابعة المرتبطة بالبلاغ
        if report.assigned_responder_id == request.user.id:
            if getattr(report, "created_by_id", None):
                target_user_ids.add(report.created_by_id)

            if getattr(report, "dispatcher_id", None):
                target_user_ids.add(report.dispatcher_id)

            if getattr(report, "updated_by_id", None):
                target_user_ids.add(report.updated_by_id)

        # إذا المرسل ليس المستجيب، أرسل للمستجيب المعيّن
        else:
            if report.assigned_responder_id:
                target_user_ids.add(report.assigned_responder_id)

        # لا ترسل لنفس المرسل
        target_user_ids.discard(request.user.id)

        if target_user_ids:
            tokens = list(
                UserDeviceToken.objects.filter(user_id__in=target_user_ids)
                .exclude(token__isnull=True)
                .exclude(token__exact="")
                .values_list("token", flat=True)
                .distinct()
            )

            if tokens:
                sender_name = _user_display_name(request.user)
                send_fcm_to_tokens(
                    tokens,
                    title=f"رسالة جديدة - البلاغ {report.cad_number}",
                    body=f"{sender_name}: {msg[:120]}",
                    data={
                        "type": "chat",
                        "report_id": report.id,
                        "cad_number": report.cad_number,
                        "message": msg[:250],
                        "sender": sender_name,
                    },
                )
    except Exception:
        logger.exception("cad_chat push failed")

    return Response({"ok": True}, status=status.HTTP_200_OK)