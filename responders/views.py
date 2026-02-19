from __future__ import annotations

from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import OuterRef, Subquery
from django.shortcuts import render
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ResponderLocation
from .permissions import IsMobileResponder


# ==========================
# Helpers
# ==========================

def _to_decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{field_name} غير صالح")


def _to_optional_decimal(value: Any) -> Optional[Decimal]:
    if value in (None, "", "null", "None"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _to_optional_int(value: Any) -> Optional[int]:
    if value in (None, "", "null", "None"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_str(value: Any, max_len: int) -> Optional[str]:
    s = (str(value).strip() if value is not None else "")
    if not s:
        return None
    return s[:max_len]


def _get_user_group_code(user) -> str:
    try:
        code = getattr(getattr(user, "user_group", None), "code", None)
        if code:
            return str(code).upper().strip()
    except Exception:
        pass

    try:
        code2 = getattr(user, "group_code", None)
        if code2:
            return str(code2).upper().strip()
    except Exception:
        pass

    return ""


def _get_full_name(user) -> str:
    for attr in ("full_name", "name"):
        try:
            v = getattr(user, attr, None)
            if v:
                return str(v).strip()
        except Exception:
            pass

    try:
        if hasattr(user, "get_full_name"):
            v = user.get_full_name()
            if v:
                return str(v).strip()
    except Exception:
        pass

    try:
        v = getattr(user, "username", None)
        return str(v).strip() if v else ""
    except Exception:
        return ""


def _region_display(region_obj) -> str:
    """
    يعالج اختلافات موديل Region عندك:
    - إذا عنده name_ar استخدمه
    - غير ذلك استخدم str(region_obj) (يعتمد على __str__)
    """
    if not region_obj:
        return ""
    try:
        v = getattr(region_obj, "name_ar", None)
        if v:
            return str(v)
    except Exception:
        pass
    return str(region_obj)


# ✅ المجموعات التي ترى كل المناطق (استثناء)
PRIVILEGED_GROUP_CODES = {"SYSADMIN", "NEMSCC"}


def _online_cutoff():
    window = int(getattr(settings, "RESPONDER_ONLINE_WINDOW_SECONDS", 35))
    return timezone.now() - timedelta(seconds=window)


# ==========================
# Pages (HTML)
# ==========================

@login_required
def show_all_responders(request):
    """
    يعرض جميع المستجيبين (ECRMOBIL) سواء متصل أو غير متصل
    + آخر موقع معروف إن وجد.
    """
    cutoff = _online_cutoff()
    User = get_user_model()

    # آخر سجل Location لكل مستخدم
    loc_qs = ResponderLocation.objects.filter(responder_id=OuterRef("pk")).order_by("-last_seen")

    users_qs = (
        User.objects.select_related("region", "user_group")
        .filter(user_group__code="ECRMOBIL")
        .filter(region_id__isnull=False)
        .annotate(
            last_seen=Subquery(loc_qs.values("last_seen")[:1]),
            latitude=Subquery(loc_qs.values("latitude")[:1]),
            longitude=Subquery(loc_qs.values("longitude")[:1]),
            accuracy_m=Subquery(loc_qs.values("accuracy_m")[:1]),
            speed_m_s=Subquery(loc_qs.values("speed_m_s")[:1]),
            heading_deg=Subquery(loc_qs.values("heading_deg")[:1]),
            device_id=Subquery(loc_qs.values("device_id")[:1]),
            platform=Subquery(loc_qs.values("platform")[:1]),
            app_version=Subquery(loc_qs.values("app_version")[:1]),
        )
        .order_by("id")
    )

    viewer_group = _get_user_group_code(request.user)

    # فلترة المستخدمين حسب المنطقة لغير الاستثناءات
    viewer_region_id = getattr(request.user, "region_id", None)
    if viewer_group not in PRIVILEGED_GROUP_CODES:
        if viewer_region_id:
            users_qs = users_qs.filter(region_id=viewer_region_id)
        else:
            users_qs = users_qs.none()

    responders = []
    for u in users_qs:
        region_obj = getattr(u, "region", None)
        last_seen = getattr(u, "last_seen", None)

        responders.append(
            {
                "id": u.id,
                "full_name": _get_full_name(u),
                "national_id": getattr(u, "national_id", "") or "",
                "phone": getattr(u, "phone", "") or "",
                "email": getattr(u, "email", "") or "",
                "group_code": getattr(getattr(u, "user_group", None), "code", "") or "",
                "region": _region_display(region_obj),
                "is_health_practitioner": bool(getattr(u, "is_health_practitioner", False)),
                "is_online": bool(last_seen and last_seen >= cutoff),
                "last_seen": last_seen,
                "lat": float(getattr(u, "latitude", None)) if getattr(u, "latitude", None) is not None else None,
                "lng": float(getattr(u, "longitude", None)) if getattr(u, "longitude", None) is not None else None,
                "accuracy": float(getattr(u, "accuracy_m", None)) if getattr(u, "accuracy_m", None) is not None else None,
                "speed": float(getattr(u, "speed_m_s", None)) if getattr(u, "speed_m_s", None) is not None else None,
                "heading": getattr(u, "heading_deg", None),
                "device_id": getattr(u, "device_id", None) or "",
                "platform": getattr(u, "platform", None) or "",
                "app_version": getattr(u, "app_version", None) or "",
            }
        )

    # ✅ مناطق للفلترة: تظهر فقط المسموح للمستخدم الحالي
    try:
        from regions.models import Region  # type: ignore

        if viewer_group in PRIVILEGED_GROUP_CODES:
            regions = Region.objects.all()
        else:
            regions = Region.objects.filter(id=viewer_region_id) if viewer_region_id else Region.objects.none()

    except Exception:
        regions = []

    return render(
        request,
        "responders/show_all_responders_.html",
        {"responders": responders, "regions": regions},
    )


# ==========================
# APIs (كما هي)
# ==========================

class UpdateMyLocationAPI(APIView):
    """تحديث موقع المستجيب (ECRMOBIL)."""
    permission_classes = [IsAuthenticated, IsMobileResponder]

    def post(self, request):
        data = request.data or {}

        try:
            lat = _to_decimal(data.get("lat"), "lat")
            lng = _to_decimal(data.get("lng"), "lng")
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        if lat < Decimal("-90") or lat > Decimal("90"):
            return Response({"detail": "lat خارج النطاق"}, status=status.HTTP_400_BAD_REQUEST)
        if lng < Decimal("-180") or lng > Decimal("180"):
            return Response({"detail": "lng خارج النطاق"}, status=status.HTTP_400_BAD_REQUEST)

        accuracy = _to_optional_decimal(data.get("accuracy"))
        speed = _to_optional_decimal(data.get("speed"))
        heading = _to_optional_int(data.get("heading"))

        device_id = _clean_str(data.get("device_id"), 128)
        platform = _clean_str(data.get("platform"), 32)
        app_version = _clean_str(data.get("app_version"), 32)

        now = timezone.now()

        obj, _created = ResponderLocation.objects.update_or_create(
            responder=request.user,
            defaults={
                "latitude": lat,
                "longitude": lng,
                "accuracy_m": accuracy,
                "speed_m_s": speed,
                "heading_deg": heading,
                "device_id": device_id,
                "platform": platform,
                "app_version": app_version,
                "last_seen": now,
            },
        )

        return Response({"ok": True, "last_seen": obj.last_seen.isoformat()}, status=status.HTTP_200_OK)


class OnlineRespondersAPI(APIView):
    """إرجاع قائمة المستجيبين المتصلين للخريطة."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        cutoff = _online_cutoff()

        qs = (
            ResponderLocation.objects.select_related("responder", "responder__region", "responder__user_group")
            .filter(last_seen__gte=cutoff)
            .filter(responder__user_group__code="ECRMOBIL")
            .filter(responder__region_id__isnull=False)
            .order_by("-last_seen")
        )

        viewer_group = _get_user_group_code(request.user)
        if viewer_group not in PRIVILEGED_GROUP_CODES:
            viewer_region_id = getattr(request.user, "region_id", None)
            if not viewer_region_id:
                return Response({"count": 0, "results": []}, status=status.HTTP_200_OK)
            qs = qs.filter(responder__region_id=viewer_region_id)

        results = []
        for loc in qs:
            r = loc.responder
            region_obj = getattr(r, "region", None)

            results.append(
                {
                    "id": getattr(r, "id", None),
                    "full_name": _get_full_name(r),
                    "national_id": getattr(r, "national_id", "") or "",
                    "phone": getattr(r, "phone", "") or "",
                    "is_health_practitioner": bool(getattr(r, "is_health_practitioner", False)),
                    "region": _region_display(region_obj),
                    "lat": float(loc.latitude) if loc.latitude is not None else None,
                    "lng": float(loc.longitude) if loc.longitude is not None else None,
                    "accuracy": float(loc.accuracy_m) if loc.accuracy_m is not None else None,
                    "last_seen": loc.last_seen.isoformat() if loc.last_seen else None,
                }
            )

        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)
