from rest_framework.permissions import BasePermission


class IsMobileResponder(BasePermission):
    """يسمح فقط لمجموعة المستجيبين (ECRMOBIL) بتحديث الموقع."""

    message = "غير مصرح: هذا المسار للمستجيبين (ECRMOBIL) فقط."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return False
        ug = getattr(user, "user_group", None)
        return bool(ug and ug.code == "ECRMOBIL")
