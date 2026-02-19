from __future__ import annotations

from typing import Optional
from django.db.models import QuerySet


def user_can_view_all_regions(user) -> bool:
    """
    True إذا كانت مجموعة المستخدم تسمح برؤية جميع المناطق.
    - يعتمد على user.user_group.data_scope
    - يعتبر superuser أيضًا يرى الكل (احتياط)
    """
    try:
        if not user or not getattr(user, "is_authenticated", False):
            return False

        if getattr(user, "is_superuser", False):
            return True

        ug = getattr(user, "user_group", None)
        if not ug:
            return False

        return ug.data_scope == "ALL"
    except Exception:
        return False


def apply_region_scope(
    qs: QuerySet,
    user,
    region_lookup: str = "region",
) -> QuerySet:
    """
    يطبق نطاق البيانات على QuerySet:
    - إن كانت المجموعة ALL: لا يفلتر
    - غير ذلك: يفلتر على منطقة المستخدم عبر region_lookup
      مثال region_lookup:
        - "region" (افتراضي)
        - "organization__region"
        - "report__region"
    """
    if user_can_view_all_regions(user):
        return qs

    user_region_id: Optional[int] = getattr(getattr(user, "region", None), "id", None)
    if not user_region_id:
        # في حال مستخدم ليس له منطقة (يفترض ألا يحدث لغير ALL حسب clean)
        return qs.none()

    return qs.filter(**{f"{region_lookup}_id": user_region_id})
