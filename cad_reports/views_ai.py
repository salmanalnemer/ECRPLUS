from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET

from cad_reports.models import CADReport
from responders.models import ResponderLocation

logger = logging.getLogger(__name__)


def _json_params(request) -> dict:
    """
    ✅ يطلع العربي طبيعي دائماً
    ✅ وإذا كتبت ?pretty=1 يطلع JSON مرتب بأسطر (indent)
    """
    params = {"ensure_ascii": False}
    if (request.GET.get("pretty") or "").strip() in {"1", "true", "yes", "on"}:
        params["indent"] = 2
    return params


def _safe_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    dt = parse_datetime(v)
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _fmt_duration_seconds(sec: float) -> str:
    sec = max(0, int(sec))
    h = sec // 3600
    m = (sec % 3600) // 60
    s = sec % 60
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _grid_key(lat: float, lng: float, cell: float = 0.01) -> Tuple[int, int]:
    return (int(lat / cell), int(lng / cell))


def _is_model_instance(v: Any) -> bool:
    return hasattr(v, "_meta") and hasattr(v, "pk")


def _case_type_value_label(report: Any) -> Tuple[str, str]:
    """
    يدعم:
    - FK إلى CaseType => يرجع (id, name)
    - choices/value عادي => يرجع (value, display/value)
    """
    if not hasattr(report, "case_type"):
        return ("", "")

    ct = getattr(report, "case_type", None)
    if ct is None:
        return ("", "")

    # FK object
    if _is_model_instance(ct):
        value = str(getattr(ct, "pk", "") or getattr(ct, "id", "") or "")
        label = (
            getattr(ct, "name", None)
            or getattr(ct, "title", None)
            or getattr(ct, "label", None)
            or getattr(ct, "code", None)
            or str(ct)
        )
        return (value, str(label))

    # choices / raw value
    value = str(ct)
    fn = getattr(report, "get_case_type_display", None)
    label = str(fn()) if callable(fn) else value
    return (value, label)


@login_required
def ai_hotspots_page(request):
    return render(
        request,
        "live_map_view/ai_hotspots_map.html",
        {"google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", "")},
    )


@login_required
@require_GET
def cad_api_case_types(request):
    items: List[Dict[str, str]] = []

    # 1) choices
    try:
        field = CADReport._meta.get_field("case_type")
        choices = getattr(field, "choices", None) or []
        if choices:
            for value, label in choices:
                items.append({"value": str(value), "label": str(label)})
    except Exception:
        pass

    # 2) FK -> CaseType (اختياري إن كان موجود)
    if not items:
        try:
            from cad_reports.models import CaseType  # type: ignore

            qs = CaseType.objects.all()
            if hasattr(CaseType, "_meta") and any(f.name == "name" for f in CaseType._meta.fields):
                qs = qs.order_by("name")

            for ct in qs[:500]:
                label = (
                    getattr(ct, "name", None)
                    or getattr(ct, "title", None)
                    or getattr(ct, "label", None)
                    or getattr(ct, "code", None)
                    or str(ct)
                )
                items.append({"value": str(ct.pk), "label": str(label)})
        except Exception:
            items = [
                {"value": "medical", "label": "طبي"},
                {"value": "trauma", "label": "إصابة"},
                {"value": "fire", "label": "حريق"},
                {"value": "other", "label": "أخرى"},
            ]

    return JsonResponse(
        {"items": items, "_source": "views_ai.py_v3"},
        json_dumps_params=_json_params(request),
    )


@login_required
@require_GET
def cad_api_ai_hotspots(request):
    """
    API:
    /cad/api/ai/hotspots/
    """
    try:
        dt_from = _safe_dt(request.GET.get("from"))
        dt_to = _safe_dt(request.GET.get("to"))
        status = (request.GET.get("status") or "").strip()
        case_type = (request.GET.get("case_type") or "").strip()

        now = datetime.now(timezone.utc)
        if dt_to is None:
            dt_to = now
        if dt_from is None:
            dt_from = dt_to - timedelta(days=7)

        qs = CADReport.objects.all()

        # فلترة زمنية
        if hasattr(CADReport, "created_at"):
            qs = qs.filter(created_at__gte=dt_from, created_at__lte=dt_to)

        # فلترة حالة
        if status and hasattr(CADReport, "status"):
            qs = qs.filter(status=status)

        # فلترة نوع الحالة (FK أو choices)
        if case_type and hasattr(CADReport, "case_type"):
            try:
                field = CADReport._meta.get_field("case_type")
                is_fk = getattr(field, "remote_field", None) is not None
            except Exception:
                is_fk = False

            if is_fk:
                qs = qs.filter(case_type_id=case_type)
            else:
                qs = qs.filter(case_type=case_type)

        # صلاحيات/منطقة
        user = request.user
        user_region = getattr(user, "region", None)
        can_all = False
        try:
            can_all = user.groups.filter(name__in=["SYSADMIN", "NEMSCC"]).exists()
        except Exception:
            can_all = False

        if user_region and (not can_all) and hasattr(CADReport, "region"):
            qs = qs.filter(region=user_region)

        # Points
        points: List[Dict[str, Any]] = []
        for r in qs[:20000]:
            lat = getattr(r, "latitude", None)
            lng = getattr(r, "longitude", None)
            if lat is None or lng is None:
                continue

            get_status_label = getattr(r, "get_status_display", None)
            ct_value, ct_label = _case_type_value_label(r)

            points.append(
                {
                    "id": getattr(r, "id", None),
                    "cad_number": getattr(r, "cad_number", "") or getattr(r, "cad_id", "") or "",
                    "lat": float(lat),
                    "lng": float(lng),
                    "case_type": ct_value,
                    "case_type_label": ct_label,
                    "status": getattr(r, "status", "") if hasattr(r, "status") else "",
                    "status_label": (
                        str(get_status_label()) if callable(get_status_label)
                        else (getattr(r, "status", "") if hasattr(r, "status") else "")
                    ),
                    "accepted_at": getattr(r, "accepted_at", None).isoformat() if getattr(r, "accepted_at", None) else None,
                    "closed_at": getattr(r, "closed_at", None).isoformat() if getattr(r, "closed_at", None) else None,
                }
            )

        # Responders
        responders: List[Dict[str, Any]] = []
        rqs = ResponderLocation.objects.all()

        if user_region and (not can_all) and hasattr(ResponderLocation, "region"):
            rqs = rqs.filter(region=user_region)

        recent_cutoff = now - timedelta(minutes=2)
        if hasattr(ResponderLocation, "updated_at"):
            rqs = rqs.filter(updated_at__gte=recent_cutoff)

        try:
            rqs = rqs.select_related("responder")
        except Exception:
            pass

        for x in rqs[:5000]:
            lat = getattr(x, "latitude", None)
            lng = getattr(x, "longitude", None)
            if lat is None or lng is None:
                continue

            resp = getattr(x, "responder", None)
            name = (
                getattr(resp, "full_name", None)
                or getattr(resp, "name", None)
                or getattr(resp, "username", None)
                or "مستجيب"
            )
            responders.append(
                {
                    "id": getattr(resp, "id", None),
                    "name": str(name),
                    "group": getattr(resp, "group_code", "") or getattr(resp, "group", "") or "",
                    "lat": float(lat),
                    "lng": float(lng),
                    "updated_at": getattr(x, "updated_at", None).isoformat() if getattr(x, "updated_at", None) else None,
                }
            )

        # Hotspots
        cell = 0.01
        buckets: Dict[Tuple[int, int], List[Dict[str, Any]]] = {}
        for p in points:
            k = _grid_key(p["lat"], p["lng"], cell=cell)
            buckets.setdefault(k, []).append(p)

        hotspots: List[Dict[str, Any]] = []
        for _, arr in buckets.items():
            if len(arr) < 2:
                continue

            lat_avg = sum(a["lat"] for a in arr) / len(arr)
            lng_avg = sum(a["lng"] for a in arr) / len(arr)

            freq: Dict[str, int] = {}
            dur_secs: List[float] = []

            for a in arr:
                ct = str(a.get("case_type_label") or a.get("case_type") or "")
                freq[ct] = freq.get(ct, 0) + 1

                acc = _safe_dt(a.get("accepted_at")) if a.get("accepted_at") else None
                clo = _safe_dt(a.get("closed_at")) if a.get("closed_at") else None
                if acc:
                    end = clo or now
                    dur_secs.append((end - acc).total_seconds())

            top_case = max(freq.items(), key=lambda x: x[1])[0] if freq else ""
            avg_sec = (sum(dur_secs) / len(dur_secs)) if dur_secs else 0.0

            hotspots.append(
                {
                    "lat": float(lat_avg),
                    "lng": float(lng_avg),
                    "count": len(arr),
                    "top_case_type": top_case,
                    "avg_duration": _fmt_duration_seconds(avg_sec),
                    "minutes": int(avg_sec // 60),
                    "label": "منطقة كثافة بلاغات",
                }
            )

        hotspots.sort(key=lambda h: h["count"], reverse=True)
        hotspots = hotspots[:12]

        return JsonResponse(
            {
                "_source": "views_ai.py_v3",
                "points": points,
                "responders": responders,
                "hotspots": hotspots,
            },
            json_dumps_params=_json_params(request),
        )

    except Exception as e:
        logger.exception("cad_api_ai_hotspots failed")
        return JsonResponse(
            {"_source": "views_ai.py_v3", "error": str(e)},
            status=500,
            json_dumps_params=_json_params(request),
        )
