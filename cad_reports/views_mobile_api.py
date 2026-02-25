from __future__ import annotations

import logging

from django.utils.dateparse import parse_date

from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.db import models

from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import CADReport, UserDeviceToken

logger = logging.getLogger(__name__)

# نفس القيم المستخدمة في views.py
PRIVILEGED_GROUP_CODES = {"SYSADMIN", "NEMSCC"}


def _get_user_group_code(user) -> str:
    # نسخة خفيفة لتجنب circular imports
    try:
        # لو عندك user.group_code مباشرة
        code = getattr(user, "group_code", None)
        if code:
            return str(code)
    except Exception:
        pass

    try:
        # لو عندك user.groups (Django groups) واستخدمت أسم المجموعة كـ code
        g = user.groups.first()
        if g:
            return str(g.name).upper()
    except Exception:
        pass

    return ""


def _ensure_can_act(report: CADReport, user, *, allow_unassigned: bool = False) -> None:
    """تحقق صلاحية المستجيب على البلاغ.

    - المجموعات المميّزة (SYSADMIN/NEMSCC) مسموح لها دائماً.
    - الوضع الطبيعي: المستجيب يتصرف فقط في البلاغ المعيّن له.
    - عند allow_unassigned=True: يسمح بتنفيذ الإجراء إذا لم يكن البلاغ معيّناً لأحد بعد.
      (مطلوب لزر "قبول" في تطبيق الجوال عندما يظهر البلاغ للمستجيب قبل تعيينه)
    """
    group = _get_user_group_code(user)
    if group in PRIVILEGED_GROUP_CODES:
        return

    if allow_unassigned and report.assigned_responder_id is None:
        return

    if report.assigned_responder_id != user.id:
        raise PermissionDenied("not_assigned_to_you")


def _get_report_by_cad_for_user(cad_number: str, user, *, allow_unassigned: bool = False) -> CADReport:
    r = get_object_or_404(CADReport, cad_number=str(cad_number).strip())
    _ensure_can_act(r, user, allow_unassigned=allow_unassigned)
    return r


def _status_of(r: CADReport) -> str:
    """حالة نصية مبسطة (للتطبيق)."""
    if r.is_closed:
        return "CLOSED"
    if r.arrived_at:
        return "ARRIVED"
    if r.accepted_at:
        return "ACCEPTED"
    if r.dispatched_at:
        return "DISPATCHED"
    return "OPEN"


def _user_region_id(user):
    rid = getattr(user, "region_id", None)
    return rid


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_assigned_reports(request):
    """قائمة بلاغات CAD للتطبيق (JWT).

    سياسة الإظهار:
    - SYSADMIN/NEMSCC: كل البلاغات غير المغلقة.
    - غير ذلك:
        - البلاغات المعيّنة للمستخدم.
        - + البلاغات غير المعيّنة (assigned_responder=None) داخل منطقة المستخدم (إن وُجدت).
          إذا المستخدم بدون منطقة: نعرض غير المعيّن فقط (بدون تقييد منطقة) لتجنب فراغ الشاشة.
    """
    group = _get_user_group_code(request.user)

    qs = CADReport.objects.select_related("case_type", "region", "assigned_responder")
    qs = qs.filter(is_closed=False).order_by("-created_at")

    if group not in PRIVILEGED_GROUP_CODES:
        rid = _user_region_id(request.user)
        if rid:
            qs = qs.filter(
                (
                    # assigned to me
                    models.Q(assigned_responder=request.user)
                    |
                    # unassigned in my region
                    models.Q(assigned_responder__isnull=True, region_id=rid)
                )
            )
        else:
            qs = qs.filter(
                models.Q(assigned_responder=request.user) | models.Q(assigned_responder__isnull=True)
            )

    def _safe_str(v):
        return "-" if v is None else str(v)

    results = []
    for r in qs[:250]:
        results.append(
            {
                "id": r.id,
                "cad_number": r.cad_number,
                "case_type": getattr(r.case_type, "name", None) or getattr(r.case_type, "name_ar", None) or str(r.case_type),
                "severity": r.severity,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "injured_count": r.injured_count,
                "age": r.age,
                "is_conscious": r.is_conscious,
                "location_text": r.location_text,
                "details": r.details,
                "latitude": r.latitude,
                "longitude": r.longitude,
                "region": _safe_str(getattr(r.region, "name_ar", None) or getattr(r.region, "name_en", None) or r.region),
                "responder": _safe_str(getattr(r.assigned_responder, "get_full_name", lambda: None)() or getattr(r.assigned_responder, "username", None) or r.assigned_responder),
                "status": _status_of(r),
                "dispatched_at": r.dispatched_at.isoformat() if r.dispatched_at else None,
                "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
                "arrival_time": r.arrived_at.isoformat() if r.arrived_at else None,
                "is_closed": r.is_closed,
                "closed_at": r.closed_at.isoformat() if r.closed_at else None,
                # response_duration (اختياري)
                "response_duration": r.response_duration if hasattr(r, "response_duration") else None,
            }
        )

    return Response({"ok": True, "count": len(results), "results": results}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_accept(request, cad_number: str):
    """قبول البلاغ (موبايل) باستخدام JWT.

    ✅ يسمح بالقبول إذا كان البلاغ غير معيّن لأحد بعد، وفي هذه الحالة يتم تعيينه للمستخدم الحالي.
    """
    r = _get_report_by_cad_for_user(cad_number, request.user, allow_unassigned=True)
    try:
        # إذا البلاغ غير معيّن، نعيّنه لهذا المستجيب أولاً (Atomic قدر الإمكان)
        if r.assigned_responder_id is None:
            r.assigned_responder = request.user
            r.full_clean()
            r.save(update_fields=["assigned_responder", "updated_at"])

        r.mark_accepted(by=request.user, source="mobile", force=True)
    except Exception as e:
        logger.exception("cad_accept failed")
        return Response({"ok": False, "error": "accept_failed", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_reject(request, cad_number: str):
    """رفض البلاغ (موبايل) باستخدام JWT.

    المنطق الحالي بدون تغيير قاعدة البيانات:
    - إزالة assigned_responder حتى يرجع البلاغ للطابور/يُعاد ترحيله من الويب.
    - لا نغيّر cad_number ولا بيانات البلاغ الأخرى.
    """
    r = _get_report_by_cad_for_user(cad_number, request.user)
    try:
        # إذا كان مقبول/مباشر/مغلق نمنع الرفض (حماية عمل)
        if r.accepted_at or r.arrived_at or r.closed_at:
            return Response(
                {"ok": False, "error": "cannot_reject_after_progress", "detail": "لا يمكن رفض بلاغ بعد بدء المعالجة."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        r.assigned_responder = None
        r.full_clean()
        r.save(update_fields=["assigned_responder", "updated_at"])
    except Exception as e:
        logger.exception("cad_reject failed")
        return Response({"ok": False, "error": "reject_failed", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_arrive(request, cad_number: str):
    """وصول/مباشرة البلاغ (موبايل) باستخدام JWT."""
    r = _get_report_by_cad_for_user(cad_number, request.user)
    try:
        r.mark_arrived(by=request.user, source="mobile", force=True)
    except Exception as e:
        logger.exception("cad_arrive failed")
        return Response({"ok": False, "error": "arrive_failed", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_close(request, cad_number: str):
    """إغلاق البلاغ (موبايل) باستخدام JWT."""
    r = _get_report_by_cad_for_user(cad_number, request.user)
    try:
        r.mark_closed(by=request.user, source="mobile_manual", force=True)
    except Exception as e:
        logger.exception("cad_close failed")
        return Response({"ok": False, "error": "close_failed", "detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"ok": True}, status=status.HTTP_200_OK)


@api_view(["POST"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def register_device_token(request):
    """Register/refresh FCM device token for this user."""
    token = str(request.data.get('token') or '').strip()
    platform = str(request.data.get('platform') or '').strip()
    if not token:
        return Response({'ok': False, 'error': 'token_required'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        obj, _created = UserDeviceToken.objects.update_or_create(
            token=token,
            defaults={'user': request.user, 'platform': platform, 'is_active': True},
        )
    except Exception as e:
        logger.exception('register_device_token failed')
        return Response({'ok': False, 'error': 'save_failed', 'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    return Response({'ok': True}, status=status.HTTP_200_OK)


@api_view(["GET"])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def cad_my_reports(request):
    """قائمة بلاغات CAD الخاصة بالمستجيب (المعيّنة له) مع فلترة بالتاريخ.

    Query params:
      - from=YYYY-MM-DD
      - to=YYYY-MM-DD
      - year=YYYY
    """
    qs = (
        CADReport.objects
        .select_related("case_type", "region", "assigned_responder")
        .filter(assigned_responder=request.user)
        .order_by("-created_at")
    )

    year = request.query_params.get("year")
    dfrom = request.query_params.get("from")
    dto = request.query_params.get("to")

    if year:
        try:
            y = int(year)
            qs = qs.filter(created_at__year=y)
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

    def safe_str(v):
        return "" if v is None else str(v)

    data = []
    for r in qs[:500]:  # سقف حماية
        data.append({
            "id": r.id,
            "cad_number": safe_str(r.cad_number),
            "case_type": safe_str(getattr(r.case_type, "name", "")),
            "severity": safe_str(getattr(r, "severity", "")),
            "status": _status_of(r),
            "created_at": r.created_at.isoformat() if getattr(r, "created_at", None) else None,
            "dispatched_at": r.dispatched_at.isoformat() if getattr(r, "dispatched_at", None) else None,
            "accepted_at": r.accepted_at.isoformat() if getattr(r, "accepted_at", None) else None,
            "arrived_at": r.arrived_at.isoformat() if getattr(r, "arrived_at", None) else None,
            "is_closed": bool(getattr(r, "is_closed", False)),
        })

    return Response({"results": data, "count": qs.count()}, status=status.HTTP_200_OK)
