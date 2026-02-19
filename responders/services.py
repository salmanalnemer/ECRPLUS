from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import QuerySet
from django.utils import timezone

from accounts.models import User
from .models import ResponderLocation


def online_cutoff():
    seconds = getattr(settings, "RESPONDER_ONLINE_WINDOW_SECONDS", 35)
    return timezone.now() - timedelta(seconds=int(seconds))


def online_locations_qs() -> QuerySet[ResponderLocation]:
    return ResponderLocation.objects.select_related(
        "responder",
        "responder__region",
        "responder__user_group",
    ).filter(last_seen__gte=online_cutoff())


def apply_viewer_scope(viewer: User, qs: QuerySet[ResponderLocation]) -> QuerySet[ResponderLocation]:
    """تطبيق نطاق البيانات حسب مجموعة المستخدم الذي يشاهد الخريطة."""
    ug = getattr(viewer, "user_group", None)
    if not ug:
        return qs.none()

    # مجموعات ترى كل المناطق
    if ug.code in {"SYSADMIN", "NEMSCC"}:
        return qs

    # إن كان DataScope موجود عندك بالموديل
    if getattr(ug, "data_scope", None) == "ALL":
        return qs

    # باقي المجموعات: منطقة المستخدم فقط
    if viewer.region_id:
        return qs.filter(responder__region_id=viewer.region_id)
    return qs.none()
