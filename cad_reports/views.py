from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model  # ✅ NEW
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import Http404, HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from ecr_reports.models import MobileReport
from responders.models import ResponderLocation
from regions.models import Region  # ✅ NEW

from .models import CADReport, CADReportActivity, CaseType, UserDeviceToken
from .services.fcm import send_fcm_to_tokens

from django.views.decorators.cache import cache_control
from django.utils.timezone import now

logger = logging.getLogger(__name__)

def _actor_name(user) -> str:
    """Return a safe display name for custom User models that may not have `username`."""
    if not user:
        return "النظام"
    for attr in ("full_name", "name", "display_name"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    try:
        v = user.get_full_name()
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    try:
        v = user.get_username()
        if isinstance(v, str) and v.strip():
            return v.strip()
    except Exception:
        pass
    for attr in ("email", "phone", "phone_number", "mobile"):
        v = getattr(user, attr, None)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return str(user)


User = get_user_model()  # ✅ NEW

# ==========================
# Helpers
# ==========================

# ✅ تقسيم الصلاحيات حسب المجموعات
# - SUPER: يشوف كل المناطق/كامل المملكة
# - BRANCH: يشوف منطقته فقط
SUPER_GROUP_CODES = {"SYSADMIN", "NEMSCC"}
BRANCH_GROUP_CODES = {"BOCM", "ORRB", "BVM", "ITS"}

# ⚠️ ملاحظة: PRIVILEGED_GROUP_CODES نستخدمها هنا فقط لمعنى "SUPER" (على مستوى المملكة)
# حتى لا تنفتح باقي الشاشات (ECR/Responders/Region dropdown) لمدراء الفروع.
PRIVILEGED_GROUP_CODES = set(SUPER_GROUP_CODES)


def _get_user_group_code(user) -> str:
    # حسب نموذجك: عندك user_group بكود، أو group_code، أو groups (Django)
    try:
        code = getattr(getattr(user, "user_group", None), "code", None)
        if code:
            return str(code)
    except Exception:
        pass

    code = getattr(user, "group_code", None)
    if code:
        return str(code)

    # fallback: أول مجموعة من Django Groups
    try:
        g = user.groups.first()
        if g:
            return str(g.name)
    except Exception:
        pass

    return ""


def _is_super_user(user) -> bool:
    return _get_user_group_code(user) in SUPER_GROUP_CODES


def _is_branch_user(user) -> bool:
    return _get_user_group_code(user) in BRANCH_GROUP_CODES


def _json_body(request: HttpRequest) -> dict[str, Any]:
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _bool_from_any(v: Any, default: bool = True) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on", "aware"):
        return True
    if s in ("0", "false", "no", "n", "off", "unaware"):
        return False
    return default


def _format_dt(dt) -> str:
    if not dt:
        return ""
    try:
        local = timezone.localtime(dt)
        return local.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(dt)


def _format_duration(d: timedelta | None) -> str:
    if not d:
        return ""
    try:
        total = int(d.total_seconds())
        if total < 0:
            total = 0
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"
    except Exception:
        return ""


#   =========================
#   Online responders cutoff
#   =========================
def _online_cutoff() -> timezone.datetime:
    # يعتبر المستجيب Online إذا آخر تحديث خلال 10 دقائق
    return timezone.now() - timedelta(minutes=10)


#   =========================
#   Map center helper
#   =========================
def _parse_when_param(request: HttpRequest) -> timezone.datetime | None:
    """Parse optional 'when' parameter from POST for manual overrides.

    Accepts:
    - 'YYYY-MM-DD HH:MM:SS'
    - ISO 8601 'YYYY-MM-DDTHH:MM(:SS)'
    Returns aware datetime in current timezone.
    """
    raw = (request.POST.get("when") or request.POST.get("at") or "").strip()
    if not raw:
        return None
    try:
        raw2 = raw.replace("T", " ")
        dt = timezone.datetime.fromisoformat(raw2)
    except Exception:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _bool_param(request: HttpRequest, name: str) -> bool:
    v = (request.POST.get(name) or "").strip().lower()
    return v in {"1", "true", "yes", "y", "on"}


def _safe_when_not_before_created(report: CADReport, when_dt: timezone.datetime | None) -> timezone.datetime:
    """
    ✅ يمنع dispatched_at يكون قبل created_at (حسب Validation عندك).
    - إذا when_dt None -> now
    - إذا when_dt < created_at -> created_at
    """
    if when_dt is None:
        return timezone.now()

    if timezone.is_naive(when_dt):
        when_dt = timezone.make_aware(when_dt, timezone.get_current_timezone())

    created = getattr(report, "created_at", None)
    if not created:
        return when_dt

    if timezone.is_naive(created):
        created = timezone.make_aware(created, timezone.get_current_timezone())

    return created if when_dt < created else when_dt


def _report_to_dict(r: CADReport) -> dict[str, Any]:
    def _dur_seconds(d):
        return int(d.total_seconds()) if d else None

    assigned_responder = None
    try:
        if getattr(r, "assigned_responder_id", None):
            assigned_responder = {
                "id": r.assigned_responder_id,
                "name": getattr(getattr(r, "assigned_responder", None), "full_name", None)
                or getattr(getattr(r, "assigned_responder", None), "username", None),
            }
    except Exception:
        assigned_responder = None

    return {
        "id": r.id,
        "cad_number": r.cad_number,
        "injured_count": r.injured_count,
        "case_type_id": r.case_type_id,
        "case_type": (r.case_type.name if r.case_type_id else None),
        "severity": r.severity,
        "age": r.age,
        "is_conscious": r.is_conscious,
        "details": r.details,
        "latitude": float(r.latitude) if r.latitude is not None else None,
        "longitude": float(r.longitude) if r.longitude is not None else None,
        "location_text": r.location_text,
        "region_id": r.region_id,
        "created_by": {"id": r.created_by_id, "name": getattr(r.created_by, "full_name", None)},
        "assigned_responder": assigned_responder,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "dispatched_at": r.dispatched_at.isoformat() if r.dispatched_at else None,
        "accepted_at": r.accepted_at.isoformat() if r.accepted_at else None,
        "arrived_at": r.arrived_at.isoformat() if r.arrived_at else None,
        "is_closed": bool(getattr(r, "is_closed", False)),
        "closed_at": r.closed_at.isoformat() if getattr(r, "closed_at", None) else None,
        "closed_source": getattr(r, "closed_source", None),
        "closed_by": {
            "id": getattr(r, "closed_by_id", None),
            "name": getattr(getattr(r, "closed_by", None), "full_name", None),
        }
        if getattr(r, "closed_by_id", None)
        else None,
        "time_to_dispatch_seconds": _dur_seconds(r.time_to_dispatch),
        "time_to_accept_seconds": _dur_seconds(r.time_to_accept),
        "time_to_arrive_seconds": _dur_seconds(r.time_to_arrive),
        "total_response_seconds": _dur_seconds(r.total_response_time),
    }


def _get_report_by_cad(cad_number: str) -> CADReport:
    cad = str(cad_number or "").strip()
    return get_object_or_404(
        CADReport.objects.select_related("case_type", "region", "assigned_responder"),
        cad_number=cad,
    )


def _get_user_map_center(user):
    """
    مركز الخريطة يعتمد على منطقة المستخدم في Django فقط:
    - region.center_lat
    - region.center_lng
    - region.default_zoom
    fallback: المملكة
    """
    center_lat = None
    center_lng = None
    zoom = 9

    region = getattr(user, "region", None)
    if region:
        try:
            if getattr(region, "center_lat", None) is not None:
                center_lat = float(region.center_lat)
        except Exception:
            center_lat = None
        try:
            if getattr(region, "center_lng", None) is not None:
                center_lng = float(region.center_lng)
        except Exception:
            center_lng = None
        try:
            if getattr(region, "default_zoom", None) is not None:
                zoom = int(region.default_zoom)
        except Exception:
            zoom = 9

    if center_lat is None or center_lng is None:
        # السعودية بالكامل
        center_lat = 23.8859
        center_lng = 45.0792
        zoom = 5

    return center_lat, center_lng, zoom


# ==========================
# Pages
# ==========================

@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def reports_cad_page(request):
    case_types = CaseType.objects.filter(is_active=True)

    user_group_code = _get_user_group_code(request.user)
    all_regions = None
    if user_group_code in PRIVILEGED_GROUP_CODES:
        all_regions = Region.objects.all().order_by("name_ar")

    region = getattr(request.user, "region", None)

    center_lat = None
    center_lng = None
    zoom = 13

    user_region_name = ""
    if region:
        user_region_name = getattr(region, "name_ar", None) or str(region)

        try:
            if getattr(region, "center_lat", None) is not None:
                center_lat = float(region.center_lat)
        except Exception:
            center_lat = None

        try:
            if getattr(region, "center_lng", None) is not None:
                center_lng = float(region.center_lng)
        except Exception:
            center_lng = None

        try:
            if getattr(region, "default_zoom", None) is not None:
                zoom = int(region.default_zoom)
        except Exception:
            zoom = 13

    map_config = {
        "lat": center_lat,
        "lng": center_lng,
        "zoom": zoom,
        "regionName": user_region_name,
    }

    return render(
        request,
        "cad_reports/reports_cad.html",
        {
            "case_types": case_types,
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "map_config": map_config,
            "user_group_code": user_group_code,
            "privileged_group_codes": PRIVILEGED_GROUP_CODES,
            "all_regions": all_regions,
        },
    )


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def reports_cad_ecr(request):
    """Dashboard (الخريطة الحية) - ECR Mobile Reports"""
    viewer_region_id = getattr(request.user, "region_id", None)

    # MobileReport ما عنده region_id نهائياً، المنطقة عند user (created_by.region)
    ecr_qs = (
        MobileReport.objects.select_related("medical_condition", "created_by", "created_by__region")
        .prefetch_related("services")
        .order_by("-created_at")
    )

    if not _is_super_user(request.user):
        if not viewer_region_id:
            ecr_qs = ecr_qs.none()
        else:
            ecr_qs = ecr_qs.filter(created_by__region_id=viewer_region_id)

    def _user_display(u):
        if not u:
            return ""
        # User عندك فيه full_name وليس get_full_name()
        return (getattr(u, "full_name", None) or getattr(u, "email", None) or str(u)).strip()

    cases_json = []
    for r in ecr_qs[:500]:
        region_obj = getattr(getattr(r, "created_by", None), "region", None)
        region_name = (
            getattr(region_obj, "name_ar", None)
            or getattr(region_obj, "name", None)
            or "-"
        )

        cases_json.append(
            {
                "id": r.id,
                "case_number": r.id,
                "created": _format_dt(r.created_at),
                "status": "جديد",

                # المنطقة من created_by.region وليس من report
                "region": region_name,

                "lat": float(r.latitude) if r.latitude is not None else None,
                "lng": float(r.longitude) if r.longitude is not None else None,

                # MobileReport لا يحتوي بيانات مريض؛ نعرض اسم المستجيب كمعلومة بديلة
                "patient_name": _user_display(getattr(r, "created_by", None)),

                # حقول غير موجودة في MobileReport: نعطي defaults آمنة عشان الـ JS ما ينكسر
                "nationality": "-",
                "age": None,
                "phone": "",
                "phone_number": "",

                # موجود
                "gender": r.get_gender_display() if hasattr(r, "get_gender_display") else (getattr(r, "gender", "") or "-"),
                "case_type": (r.medical_condition.name if r.medical_condition else "-"),
                "services": [s.name for s in r.services.all()],

                # غير موجودة: defaults
                "ambulance_requested": False,
                "ambulance_caller": "-",

                # اسم المستجيب
                "responder": _user_display(getattr(r, "created_by", None)),
                "patient_status": "-",

                # ملاحظات (موجودة)
                "notes": getattr(r, "notes", "") or "",
            }
        )

    # باقي الكود عندك للمستجيبين المتصلين يبقى كما هو…
    cutoff = _online_cutoff()
    resp_qs = (
        ResponderLocation.objects.select_related("responder", "responder__region", "responder__user_group")
        .filter(last_seen__gte=cutoff)
        .filter(responder__user_group__code="ECRMOBIL")
        .filter(responder__region_id__isnull=False)
        .order_by("-last_seen")
    )
    if not _is_super_user(request.user):
        if not viewer_region_id:
            resp_qs = resp_qs.none()
        else:
            resp_qs = resp_qs.filter(responder__region_id=viewer_region_id)

    responders_json = []
    for loc in resp_qs[:500]:
        u = getattr(loc, "responder", None)
        rg = getattr(u, "region", None) if u else None
        responders_json.append(
            {
                "id": getattr(u, "id", None),
                "name": _user_display(u),
                "region": getattr(rg, "name_ar", None) or getattr(rg, "name", None) or "-",
                "lat": float(loc.latitude) if loc.latitude is not None else None,
                "lng": float(loc.longitude) if loc.longitude is not None else None,
                "last_seen": _format_dt(loc.last_seen),
            }
        )

    center_lat, center_lng, zoom = _get_user_map_center(request.user)

    return render(
        request,
        "dashboard/reports_cad_ecr.html",
        {
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "map_center_lat": center_lat,
            "map_center_lng": center_lng,
            "map_zoom": zoom,
            "cases_json": cases_json,
            "responders_json": responders_json,
        },
    )
@login_required
def cad_reports_reports_page(request):
    context = {
        "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
        "case_types": CaseType.objects.filter(is_active=True).order_by("name"),
        "case_types_json": list(CaseType.objects.filter(is_active=True).values("id", "name")),
    }
    return render(request, "dashboard/reports_cad.html", context)


# ==========================
# ✅ NEW: Main dashboard (KPIs + charts)
# Template: dashboard/main_dashboard.html
# ==========================


def _apply_viewer_region_filter(qs, user, region_field: str = "region_id"):
    """Apply region restriction.

    - SUPER groups: no restriction (can see all).
    - All other groups (including branch managers): restricted to user's region.
    """
    if _is_super_user(user):
        return qs

    viewer_region_id = getattr(user, "region_id", None)
    if not viewer_region_id:
        return qs.none()
    return qs.filter(**{region_field: viewer_region_id})


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def main_dashboard_page(request):
    return render(request, "dashboard/main_dashboard.html")


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def api_dashboard_summary(request):
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    days_7_start = today_start - timedelta(days=6)
    days_30_start = today_start - timedelta(days=29)

    cad_qs = _apply_viewer_region_filter(CADReport.objects.all(), request.user, "region_id")
    ecr_qs = _apply_viewer_region_filter(
    MobileReport.objects.select_related("created_by", "created_by__region"),
    request.user,
    "created_by__region_id",
    )

    cad_today = cad_qs.filter(created_at__gte=today_start).count()
    ecr_today = ecr_qs.filter(created_at__gte=today_start).count()
    active_cad = cad_qs.filter(is_closed=False).count()
    closed_30d = cad_qs.filter(is_closed=True, closed_at__gte=days_30_start).count()

    cutoff = _online_cutoff()
    online_qs = (
        ResponderLocation.objects.select_related("responder", "responder__region", "responder__user_group")
        .filter(last_seen__gte=cutoff)
        .filter(responder__user_group__code="ECRMOBIL")
        .filter(responder__region_id__isnull=False)
    )
    online_qs = _apply_viewer_region_filter(online_qs, request.user, "responder__region_id")
    responders_online = online_qs.count()

    cad_7d_rows = (
        cad_qs.filter(created_at__gte=days_7_start)
        .annotate(d=TruncDate("created_at"))
        .values("d")
        .annotate(c=Count("id"))
        .order_by("d")
    )
    cad_7d_map = {r["d"]: int(r["c"]) for r in cad_7d_rows}
    labels_7d = []
    data_7d = []
    for i in range(7):
        day = (days_7_start + timedelta(days=i)).date()
        labels_7d.append(day.strftime("%Y-%m-%d"))
        data_7d.append(int(cad_7d_map.get(day, 0)))

    types_rows = (
        cad_qs.filter(created_at__gte=days_30_start)
        .values("case_type__name")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    types_labels = [r["case_type__name"] or "-" for r in types_rows[:12]]
    types_data = [int(r["c"]) for r in types_rows[:12]]

    region_rows = (
        cad_qs.filter(created_at__gte=days_30_start)
        .values("region__name_ar", "region__name_en")
        .annotate(c=Count("id"))
        .order_by("-c")
    )
    region_labels = []
    region_data = []
    for r in region_rows[:13]:
        name = r.get("region__name_ar") or r.get("region__name_en") or "-"
        region_labels.append(name)
        region_data.append(int(r["c"]))

    return JsonResponse(
        {
            "kpi": {
                "cad_today": cad_today,
                "ecr_today": ecr_today,
                "active_cad": active_cad,
                "closed_30d": closed_30d,
                "responders_online": responders_online,
            },
            "charts": {
                "cad_7d": {"labels": labels_7d, "data": data_7d},
                "types_30d": {"labels": types_labels, "data": types_data},
                "regions_30d": {"labels": region_labels, "data": region_data},
            },
            "meta": {
                "generated_at": now.isoformat(),
                "timezone": str(timezone.get_current_timezone()),
            },
        }
    )


# ==========================
# ✅ NEW: Separate CAD Dashboard (template: dashboard/reports_cad.html)
# ==========================

@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def reports_cad_dashboard(request):
    center_lat, center_lng, zoom = _get_user_map_center(request.user)

    case_types_json = list(CaseType.objects.filter(is_active=True).values("id", "name"))

    viewer_group = _get_user_group_code(request.user)
    viewer_region_id = getattr(request.user, "region_id", None)
    show_region_filter = (viewer_group in PRIVILEGED_GROUP_CODES) and (not viewer_region_id)

    regions_json = []
    if show_region_filter:
        qs = Region.objects.all().order_by("id")
        for rg in qs:
            regions_json.append(
                {
                    "id": rg.id,
                    "name": getattr(rg, "name_ar", None) or getattr(rg, "name", None) or str(rg),
                }
            )

    return render(
        request,
        "dashboard/reports_cad.html",
        {
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "map_center_lat": center_lat,
            "map_center_lng": center_lng,
            "map_zoom": zoom,
            "case_types_json": case_types_json,
            "show_region_filter": show_region_filter,
            "regions_json": regions_json,
        },
    )


# ==========================
# ✅ NEW: Separate ECR Dashboard (template: dashboard/reports_ecr.html)
# ==========================

@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def reports_ecr_dashboard(request):
    viewer_group = _get_user_group_code(request.user)
    viewer_region_id = getattr(request.user, "region_id", None)

    qs = (
        MobileReport.objects.select_related("medical_condition", "created_by")
        .prefetch_related("services")
        .order_by("-created_at")
    )

    if not _is_super_user(request.user):
        if not viewer_region_id:
            qs = qs.none()
        else:
            qs = qs.filter(region_id=viewer_region_id)

    cases_json = []
    for r in qs[:800]:
        cases_json.append(
            {
                "id": r.id,
                "created": _format_dt(r.created_at),
                "region": getattr(getattr(r, "region", None), "name_ar", None)
                or getattr(getattr(r, "region", None), "name", None)
                or "-",
                "lat": float(r.latitude) if r.latitude is not None else None,
                "lng": float(r.longitude) if r.longitude is not None else None,
                "patient_name": getattr(r.created_by, "username", "") if r.created_by_id else "",                "national_id": getattr(r, "national_id", None),
                "phone": r.patient_phone,
                "age": r.age,
                "nationality": r.get_nationality_display(),
                "gender": r.get_gender_display(),
                "case_type": (r.medical_condition.name if r.medical_condition else "-"),
                "services": [s.name for s in r.services.all()],
                "ambulance_requested": bool(r.called_ambulance),
                "ambulance_caller": r.get_ambulance_called_by_display() if r.ambulance_called_by else "-",
                "responder": (
                    getattr(getattr(r, "created_by", None), "full_name", None)
                    or getattr(getattr(r, "created_by", None), "username", None)
                    or "-"
                ),
                "send_to_997": bool(getattr(r, "send_to_997", False)),
            }
        )

    cond_names = (
        qs.exclude(medical_condition__isnull=True)
        .values_list("medical_condition__name", flat=True)
        .distinct()
    )
    conditions_json = [{"name": n} for n in cond_names if n]

    center_lat, center_lng, zoom = _get_user_map_center(request.user)

    return render(
        request,
        "dashboard/reports_ecr.html",
        {
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "map_center_lat": center_lat,
            "map_center_lng": center_lng,
            "map_zoom": zoom,
            "cases_json": cases_json,
            "conditions_json": conditions_json,
        },
    )


# ==========================
# Dashboard JSON (CAD)
# ==========================

from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication


@api_view(["GET"])
@authentication_classes([JWTAuthentication, SessionAuthentication])
@permission_classes([IsAuthenticated])
def assigned_reports_json(request):
    """Dashboard JSON for CAD reports.

    سياسة العرض:
    - SUPER (SYSADMIN/NEMSCC): يرى جميع المناطق، ويستطيع فلترة region_id من الـ GET.
    - BRANCH (BOCM/ORRB/BVM/ITS): يرى بلاغات منطقته فقط (strict) ولا يرى NULL.
    - غير ذلك (مثل المستجيب): يرى البلاغات المسندة له فقط ضمن منطقته (strict).
    """
    viewer_group = _get_user_group_code(request.user)
    viewer_region_id = getattr(request.user, "region_id", None)

    qs = CADReport.objects.select_related("case_type", "region", "assigned_responder").order_by("-created_at")

    if _is_super_user(request.user):
        # فلترة اختيارية من الـ UI (تظهر فقط للـ SUPER بدون region على المستخدم)
        region_filter = (request.GET.get("region_id") or "").strip()
        if region_filter:
            try:
                qs = qs.filter(region_id=int(region_filter))
            except Exception:
                pass

    elif _is_branch_user(request.user):
        # ✅ مدير/مشرف فرع: منطقة واحدة فقط + لا نظهر NULL
        if viewer_region_id:
            qs = qs.filter(region_id=viewer_region_id)
        else:
            qs = qs.none()

    else:
        # ✅ مستخدم عادي/مستجيب: بلاغاته المسندة له فقط ضمن منطقته
        qs = qs.filter(assigned_responder_id=request.user.id)
        if viewer_region_id:
            qs = qs.filter(region_id=viewer_region_id)
        else:
            qs = qs.none()

    data = []
    for r in qs[:800]:
        data.append(
            {
                "id": r.id,
                "cad_number": r.cad_number,
                "case_type_id": r.case_type_id,
                "type": getattr(getattr(r, "case_type", None), "name", None) or "-",
                "case_type": getattr(getattr(r, "case_type", None), "name", None) or "-",
                "severity": r.severity,
                "created_at": _format_dt(r.created_at),
                "injured_count": r.injured_count,
                "age": r.age,
                "is_conscious": bool(r.is_conscious),
                "location_text": r.location_text or "",
                "location_description": r.location_text or "",
                "details": r.details or "",
                "latitude": float(r.latitude) if r.latitude is not None else None,
                "longitude": float(r.longitude) if r.longitude is not None else None,
                "region_id": r.region_id,
                "region": getattr(getattr(r, "region", None), "name_ar", None)
                or getattr(getattr(r, "region", None), "name", None)
                or "-",
                "responder": getattr(getattr(r, "assigned_responder", None), "full_name", None)
                or str(getattr(r, "assigned_responder", None) or "-"),
                "status": "مغلق" if bool(getattr(r, "is_closed", False)) else "مفتوح",
                "notes": "",
                "dispatched_at": _format_dt(r.dispatched_at),
                "accepted_at": _format_dt(r.accepted_at),
                "arrival_time": _format_dt(r.arrived_at),
                "response_duration": _format_duration(r.total_response_time),
                "closed": bool(getattr(r, "is_closed", False)),
                "is_closed": bool(getattr(r, "is_closed", False)),
                "closed_at": _format_dt(getattr(r, "closed_at", None)),
            }
        )

    return Response(data, status=status.HTTP_200_OK)
    
# ==========================
# CRUD-ish
# ==========================

@login_required
@permission_required("cad_reports.can_create_cad_report", raise_exception=True)
@require_POST
def create_report(request: HttpRequest) -> JsonResponse:
    """
    ✅ تعديل مطلوب حسب طلبك:
    - إنشاء البلاغ + الترحيل (dispatch) يكونون عملية واحدة داخل transaction.
    - إذا فشل الترحيل => نلغي إنشاء البلاغ (rollback) ونرجع السبب للمستخدم.
    - نعرض السبب الحقيقي دائمًا (validation_error / permission / ...).
    """
    if request.content_type and "application/json" in request.content_type:
        data = _json_body(request)
    else:
        data = request.POST.dict()

    cad_number = str(data.get("cad_number", "")).strip()
    case_type_id = data.get("case_type_id") or data.get("case_type")

    if not cad_number:
        return JsonResponse({"ok": False, "error": "cad_number_required", "detail": "رقم البلاغ مطلوب."}, status=400)
    if not case_type_id:
        return JsonResponse({"ok": False, "error": "case_type_required", "detail": "نوع الحالة مطلوب."}, status=400)

    case_type = get_object_or_404(CaseType, pk=case_type_id, is_active=True)

    injured_count = data.get("injured_count") or 0
    age_val = data.get("age")
    lat = data.get("latitude")
    lng = data.get("longitude")

    is_conscious = _bool_from_any(data.get("is_conscious", data.get("awareness")), default=True)
    location_text = str(data.get("location_text") or data.get("location_description") or "").strip()

    viewer_group = _get_user_group_code(request.user)
    chosen_region_id = None

    if viewer_group in PRIVILEGED_GROUP_CODES:
        chosen_region_id = (data.get("region") or data.get("region_id") or "").strip()
        if not chosen_region_id:
            return JsonResponse({"ok": False, "error": "region_required", "detail": "يجب تحديد المنطقة."}, status=400)
        try:
            chosen_region_id_int = int(chosen_region_id)
        except Exception:
            return JsonResponse({"ok": False, "error": "region_invalid", "detail": "معرّف المنطقة غير صحيح."}, status=400)

        region_obj = get_object_or_404(Region, id=chosen_region_id_int)
        chosen_region_id = region_obj.id
    else:
        chosen_region_id = getattr(request.user, "region_id", None)

    def _clean_decimal_field_for_create(value, field_name: str):
        from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

        if value in (None, "", "null"):
            return None
        try:
            raw = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None
        try:
            f = CADReport._meta.get_field(field_name)
            dp = int(getattr(f, "decimal_places", 6) or 6)
        except Exception:
            dp = 6
        quant = Decimal("1").scaleb(-dp)
        return raw.quantize(quant, rounding=ROUND_HALF_UP)

    # ✅ المستجيب المختار
    responder_obj = None
    responder_id_raw = str(data.get("responder_id") or "").strip()
    if responder_id_raw:
        try:
            responder_id_int = int(responder_id_raw)
            responder_obj = get_object_or_404(User, pk=responder_id_int)
        except Exception:
            responder_obj = None

    # ✅ هل نلزم الترحيل؟
    must_dispatch = _bool_from_any(data.get("must_dispatch"), default=True)

    if must_dispatch and not responder_obj:
        return JsonResponse(
            {"ok": False, "error": "responder_required", "detail": "لا يمكن إنشاء البلاغ بدون اختيار مستجيب للترحيل."},
            status=400,
        )

    # ✅ بناء البلاغ
    r = CADReport(
        cad_number=cad_number,
        injured_count=int(injured_count) if str(injured_count).strip() else 0,
        case_type=case_type,
        severity=(data.get("severity") or CADReport.Severity.MEDIUM),
        age=int(age_val) if age_val not in (None, "", "null") else None,
        is_conscious=is_conscious,
        details=str(data.get("details") or ""),
        latitude=_clean_decimal_field_for_create(lat, "latitude"),
        longitude=_clean_decimal_field_for_create(lng, "longitude"),
        location_text=location_text,
        created_by=request.user,
        region_id=chosen_region_id,
        assigned_responder=responder_obj,
    )

    # ✅ إنشاء + ترحيل داخل Transaction واحد
    try:
        with transaction.atomic():
            # 1) إنشاء
            r.full_clean()
            r.save()

            # 2) ترحيل (إجباري إذا must_dispatch)
            if responder_obj and must_dispatch:
                if not request.user.has_perm("cad_reports.can_dispatch_cad_report"):
                    # rollback
                    raise PermissionError("ليس لديك صلاحية ترحيل البلاغ.")

                when = _parse_when_param(request)
                when = _safe_when_not_before_created(r, when)
                force = True
                source = "web_create"

                # mark_dispatched قد يرمي ValidationError إذا when قبل created_at
                r.mark_dispatched(when=when, by=request.user, source=source, force=force)

    except PermissionError as e:
        logger.warning("create_report blocked due to permission: %s", str(e))
        return JsonResponse({"ok": False, "error": "permission_denied", "detail": str(e)}, status=403)

    except ValidationError as e:
        # ✅ نرجع أخطاء الفاليديشن بشكل مفهوم
        logger.exception("create_report validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": e.message_dict}, status=400)

    except Exception as e:
        logger.exception("create_report failed")
        return JsonResponse({"ok": False, "error": "create_failed", "detail": str(e)}, status=400)

    # ✅ FCM بعد نجاح الـ commit فقط (عشان ما نرسل لو صار rollback)
    def _send_fcm_on_commit(report_id: int, assigned_user_id: int | None, cad_no: str):
        try:
            if not assigned_user_id:
                return
            tokens = list(
                UserDeviceToken.objects.filter(user_id=assigned_user_id, is_active=True)
                .values_list("token", flat=True)
            )
            if not tokens:
                return
            send_fcm_to_tokens(
                tokens,
                title="بلاغ CAD جديد",
                body=f"رقم البلاغ: {cad_no}",
                data={"cad_number": cad_no, "status": "مفتوح", "report_id": report_id},
            )
        except Exception:
            logger.exception("FCM push failed (non-blocking)")

    transaction.on_commit(lambda: _send_fcm_on_commit(r.id, getattr(r, "assigned_responder_id", None), r.cad_number))

    return JsonResponse({"ok": True, "report": _report_to_dict(r)}, status=201)


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def report_detail(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport.objects.select_related("case_type", "created_by"), pk=report_id)
    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def list_reports(request: HttpRequest) -> JsonResponse:
    qs = CADReport.objects.select_related("case_type", "created_by").all().order_by("-created_at")
    region_id = request.GET.get("region_id")
    if region_id:
        qs = qs.filter(region_id=region_id)
    return JsonResponse({"ok": True, "results": [_report_to_dict(r) for r in qs[:500]]})


# ==========================
# Workflow (web by report_id)
# ==========================

@login_required
@require_POST
def dispatch_report(request: HttpRequest, report_id: int) -> JsonResponse:
    """Dispatch/assign report to a responder (Web dashboard). Return JSON always."""
    if not request.user.has_perm("cad_reports.can_dispatch_cad_report"):
        return JsonResponse(
            {"ok": False, "error": "permission_denied", "detail": "ليس لديك صلاحية ترحيل البلاغ."},
            status=403,
        )

    r = get_object_or_404(CADReport, pk=report_id)
    try:
        when = _parse_when_param(request)
        when = _safe_when_not_before_created(r, when)
        force = _bool_param(request, "force")
        source = (request.POST.get("source") or "web_manual").strip() or "web_manual"
        r.mark_dispatched(when=when, by=request.user, source=source, force=force)
    except ValidationError as e:
        logger.exception("dispatch_report validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": e.message_dict}, status=400)
    except Exception as e:
        logger.exception("dispatch_report error")
        return JsonResponse({"ok": False, "error": "dispatch_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


@login_required
@permission_required("cad_reports.can_accept_cad_report", raise_exception=True)
@require_POST
def accept_report(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        when = _parse_when_param(request)
        force = _bool_param(request, "force")
        r.mark_accepted(when=when, by=request.user, source="web_manual", force=force)
    except ValidationError as e:
        logger.exception("accept_report validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": e.message_dict}, status=400)
    except Exception as e:
        logger.exception("accept_report error")
        return JsonResponse({"ok": False, "error": "accept_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


@login_required
@permission_required("cad_reports.can_mark_arrived_cad_report", raise_exception=True)
@require_POST
def arrive_report(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        when = _parse_when_param(request)
        force = _bool_param(request, "force")
        r.mark_arrived(when=when, by=request.user, source="web_manual", force=force)
    except ValidationError as e:
        logger.exception("arrive_report validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": e.message_dict}, status=400)
    except Exception as e:
        logger.exception("arrive_report error")
        return JsonResponse({"ok": False, "error": "arrive_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


@login_required
@permission_required("cad_reports.can_close_cad_report", raise_exception=True)
@require_POST
def close_report(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        when = _parse_when_param(request)
        force = _bool_param(request, "force")
        r.mark_closed(when=when, by=request.user, source="web_manual", force=force)
    except ValidationError as e:
        logger.exception("close_report validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": e.message_dict}, status=400)
    except Exception as e:
        logger.exception("close_report error")
        return JsonResponse({"ok": False, "error": "close_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


# ==========================
# API (app by report_id)
# ==========================

@login_required
@require_POST
def api_accept_report(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        r.mark_accepted(by=request.user, source="mobile", force=True)
    except Exception as e:
        logger.exception("api_accept_report error")
        return JsonResponse({"ok": False, "error": "accept_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_mark_arrived(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        r.mark_arrived(by=request.user, source="mobile", force=True)
    except Exception as e:
        logger.exception("api_mark_arrived error")
        return JsonResponse({"ok": False, "error": "arrive_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def api_close_report(request: HttpRequest, report_id: int) -> JsonResponse:
    r = get_object_or_404(CADReport, pk=report_id)
    try:
        r.mark_closed(by=request.user, source="mobile_manual", force=True)
    except Exception as e:
        logger.exception("api_close_report error")
        return JsonResponse({"ok": False, "error": "close_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


# ==========================
# ✅ API (dashboard by cad_number) - matches template
# ==========================

@login_required
@permission_required("cad_reports.can_accept_cad_report", raise_exception=True)
@require_POST
def api_assigned_accept(request: HttpRequest, cad_number: str) -> JsonResponse:
    r = _get_report_by_cad(cad_number)
    try:
        r.mark_accepted(by=request.user, source="web_manual", force=False)
    except Exception as e:
        logger.exception("api_assigned_accept error")
        return JsonResponse({"ok": False, "error": "accept_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


@login_required
@permission_required("cad_reports.can_mark_arrived_cad_report", raise_exception=True)
@require_POST
def api_assigned_arrive(request: HttpRequest, cad_number: str) -> JsonResponse:
    r = _get_report_by_cad(cad_number)
    try:
        r.mark_arrived(by=request.user, source="web_manual", force=False)
    except Exception as e:
        logger.exception("api_assigned_arrive error")
        return JsonResponse({"ok": False, "error": "arrive_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


@login_required
@permission_required("cad_reports.can_close_cad_report", raise_exception=True)
@require_POST
def api_assigned_close(request: HttpRequest, cad_number: str) -> JsonResponse:
    r = _get_report_by_cad(cad_number)
    try:
        r.mark_closed(by=request.user, source="web_manual", force=False)
    except Exception as e:
        logger.exception("api_assigned_close error")
        return JsonResponse({"ok": False, "error": "close_failed", "detail": str(e)}, status=400)
    return JsonResponse({"ok": True})


from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


@login_required
@permission_required("cad_reports.can_dispatch_cad_report", raise_exception=True)
@require_http_methods(["PATCH", "PUT"])
def api_assigned_update(request: HttpRequest, cad_number: str) -> JsonResponse:
    """تعديل كامل بيانات CAD (بدون تعديل الأوقات)."""
    r = _get_report_by_cad(cad_number)
    data = _json_body(request)

    forbidden = {"dispatched_at", "accepted_at", "arrived_at", "arrival_time", "closed_at", "is_closed", "closed"}
    if any(k in data for k in forbidden):
        return JsonResponse(
            {
                "ok": False,
                "error": "times_readonly",
                "detail": "لا يمكن تعديل الأوقات من نموذج التعديل — استخدم الأزرار فقط.",
            },
            status=400,
        )

    def _clean_int(v):
        if v in (None, "", "null"):
            return None
        try:
            return int(v)
        except Exception:
            return None

    def _clean_str(v):
        return str(v or "").strip()

    def _clean_decimal_field(value, field_name: str):
        if value in (None, "", "null"):
            return None
        try:
            raw = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return None

        try:
            f = r._meta.get_field(field_name)
            dp = int(getattr(f, "decimal_places", 6) or 6)
        except Exception:
            dp = 6

        quant = Decimal("1").scaleb(-dp)
        return raw.quantize(quant, rounding=ROUND_HALF_UP)

    if bool(getattr(r, "is_closed", False)):
        return JsonResponse({"ok": False, "error": "closed_readonly", "detail": "لا يمكن تعديل بلاغ مغلق."}, status=400)

    if "injured_count" in data:
        v = _clean_int(data.get("injured_count"))
        if v is not None:
            r.injured_count = v

    if "case_type_id" in data and data["case_type_id"]:
        ct = get_object_or_404(CaseType, pk=int(data["case_type_id"]), is_active=True)
        r.case_type = ct

    if "severity" in data and data["severity"]:
        r.severity = str(data["severity"])

    if "age" in data:
        r.age = _clean_int(data.get("age"))

    if "is_conscious" in data:
        r.is_conscious = _bool_from_any(data["is_conscious"], default=True)

    if "latitude" in data:
        r.latitude = _clean_decimal_field(data.get("latitude"), "latitude")

    if "longitude" in data:
        r.longitude = _clean_decimal_field(data.get("longitude"), "longitude")

    if "location_text" in data:
        r.location_text = _clean_str(data.get("location_text"))

    if "details" in data:
        r.details = str(data.get("details") or "")

    try:
        r.full_clean()
        r.save()
    except Exception as e:
        logger.exception("api_assigned_update validation error")
        return JsonResponse({"ok": False, "error": "validation_error", "detail": str(e)}, status=400)

    return JsonResponse({"ok": True, "report": _report_to_dict(r)})


@login_required
@permission_required("cad_reports.can_view_cad_report", raise_exception=True)
@require_GET
def responders_online_json(request: HttpRequest) -> JsonResponse:
    viewer_group = _get_user_group_code(request.user)
    viewer_region_id = getattr(request.user, "region_id", None)

    cutoff = _online_cutoff()

    qs = (
        ResponderLocation.objects.select_related("responder", "responder__region", "responder__user_group")
        .filter(last_seen__gte=cutoff)
        .filter(responder__region_id__isnull=False)
        .order_by("-last_seen")
    )

    qs = qs.filter(responder__user_group__code="ECRMOBIL")

    if not _is_super_user(request.user):
        if not viewer_region_id:
            qs = qs.none()
        else:
            qs = qs.filter(responder__region_id=viewer_region_id)

    region_filter = (request.GET.get("region_id") or "").strip()
    if region_filter and (viewer_group in PRIVILEGED_GROUP_CODES) and (not viewer_region_id):
        try:
            qs = qs.filter(responder__region_id=int(region_filter))
        except Exception:
            pass

    data = []
    for loc in qs[:1500]:
        u = loc.responder
        data.append(
            {
                "id": u.id,
                "name": getattr(u, "full_name", "") or getattr(u, "username", "") or str(u),
                "phone": getattr(u, "phone", "") or "",
                "lat": float(loc.latitude) if loc.latitude is not None else None,
                "lng": float(loc.longitude) if loc.longitude is not None else None,
                "region_id": getattr(u, "region_id", None),
                "region": getattr(getattr(u, "region", None), "name_ar", None)
                or getattr(getattr(u, "region", None), "name", None)
                or "-",
                "last_seen": _format_dt(loc.last_seen),
            }
        )

    return JsonResponse({"ok": True, "count": len(data), "results": data})


# ==========================
# ✅ NEW: AI Hotspots Page (FIX: تعريف واحد فقط)
# ==========================

@login_required
def ai_hotspots_page(request):
    user = request.user
    allowed = user.groups.filter(name__in=["NEMSCC", "SYSADMIN"]).exists()

    return render(
        request,
        "live_map_view/ai_hotspots_map.html",
        {
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "can_see_cad_dashboard_link": allowed,
        },
    )

@login_required
def cad_activities_json(request, cad_number):
    report = get_object_or_404(CADReport, cad_number=cad_number)

    activities = CADReportActivity.objects.filter(
        report=report
    ).select_related("user").order_by("created_at")

    data = [
        {
            "id": a.id,
            "message": a.message,
            "user": a.user.get_full_name() if a.user else "System",
            "created_at": a.created_at.strftime("%H:%M:%S"),
        }
        for a in activities
    ]
    return JsonResponse(data, safe=False)

from django.http import JsonResponse
from cad_reports.models import CADReportActivity
@login_required
@require_GET
def cad_activity_history(request, report_id: int):
    limit = request.GET.get("limit", "120")
    try:
        limit_i = int(limit)
    except Exception:
        limit_i = 120
    limit_i = max(1, min(limit_i, 300))

    qs = (
        CADReportActivity.objects
        .filter(report_id=report_id)
        .select_related("user")
        .order_by("-created_at")[:limit_i]
    )

    items = []
    for a in reversed(list(qs)):
        items.append({
            "kind": a.kind,
            "action": a.action,
            "message": a.message or "",
            "created_at": a.created_at.isoformat(),
            "actor_name": (_actor_name(a.user) if a.user_id else "النظام"),
        })

    return JsonResponse({"items": items})
# ==========================
# CAD Report Print View
# ==========================
# ==========================
# CAD Report Print View
# ==========================
@login_required
@cache_control(no_store=True)
def cad_report_print(request, report_id: int):
    from .models import CADReport  # الاسم الصحيح

    # ✅ العلاقات الصحيحة حسب موديلك
    report = get_object_or_404(
        CADReport.objects.select_related("region", "assigned_responder", "created_by"),
        pk=report_id,
    )

    return render(
        request,
        "dashboard/print_report.html",
        {"r": report, "printed_at": now()},
    )