from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsEcrMobileReporter(BasePermission):
    """يسمح فقط لمجموعة المستجيبين/التطبيق (ECRMOBIL) إن توفرت بنية المجموعات.

    ملاحظة: إذا لم تتوفر حقول المجموعات في نموذج المستخدم (اختلاف مشاريع/إصدارات)،
    يتم السماح للمستخدم المصادق عليه لتفادي كسر الـ API.
    """

    message = "هذا المسار مخصص لمستخدمي تطبيق ECR فقط."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False

        # محاولات شائعة: user.user_group.code / user.group.code / user.role
        for attr_path in ("user_group", "group"):
            grp = getattr(user, attr_path, None)
            if grp is not None:
                code = getattr(grp, "code", None) or getattr(grp, "slug", None)
                if code:
                    return str(code).upper() == "ECRMOBIL"

        role = getattr(user, "role", None)
        if role:
            return str(role).lower() in {"mobile", "ecrmobile", "ecrmobil"}

        # fallback permissive
        return True
