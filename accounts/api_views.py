from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

User = get_user_model()


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        return Response(
            {
                "id": u.id,
                "national_id": getattr(u, "national_id", ""),
                "full_name": getattr(u, "full_name", ""),
                "email": getattr(u, "email", ""),
                "phone": getattr(u, "phone", ""),
                "organization": getattr(u, "organization_id", None),
                "organization_name": getattr(getattr(u, "organization", None), "name", None),
                "user_group": getattr(u, "user_group_id", None),
                "user_group_name": getattr(getattr(u, "user_group", None), "code", None),
                "region": getattr(u, "region_id", None),
                "region_name": getattr(getattr(u, "region", None), "name", None),
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def patch(self, request):
        u = request.user
        email = (request.data.get("email") or "").strip()
        phone = (request.data.get("phone") or "").strip()

        errors = {}
        if not email:
            errors["email"] = ["هذا الحقل مطلوب."]
        if not phone:
            errors["phone"] = ["هذا الحقل مطلوب."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        if User.objects.filter(email=email).exclude(pk=u.pk).exists():
            return Response({"email": ["البريد مستخدم مسبقاً."]}, status=status.HTTP_409_CONFLICT)

        if hasattr(User, "phone") and User.objects.filter(phone=phone).exclude(pk=u.pk).exists():
            return Response({"phone": ["رقم الجوال مستخدم مسبقاً."]}, status=status.HTTP_409_CONFLICT)

        u.email = email
        if hasattr(u, "phone"):
            u.phone = phone
            u.save(update_fields=["email", "phone"])
        else:
            u.save(update_fields=["email"])

        return Response({"email": u.email, "phone": getattr(u, "phone", "")}, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        old_password = request.data.get("old_password") or ""
        new_password = request.data.get("new_password") or ""
        confirm_password = request.data.get("confirm_password") or ""

        errors = {}
        if not old_password:
            errors["old_password"] = ["هذا الحقل مطلوب."]
        if not new_password:
            errors["new_password"] = ["هذا الحقل مطلوب."]
        if not confirm_password:
            errors["confirm_password"] = ["هذا الحقل مطلوب."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"confirm_password": ["غير مطابق."]}, status=status.HTTP_400_BAD_REQUEST)

        u = request.user
        if not u.check_password(old_password):
            return Response({"detail": "كلمة المرور الحالية غير صحيحة."}, status=status.HTTP_403_FORBIDDEN)

        if len(new_password) < 8:
            return Response({"new_password": ["8 أحرف على الأقل."]}, status=status.HTTP_400_BAD_REQUEST)

        u.set_password(new_password)
        u.save(update_fields=["password"])
        return Response({"detail": "تم تغيير كلمة المرور."}, status=status.HTTP_200_OK)


class LocationSharingView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        enabled = request.data.get("enabled", None)
        if enabled is None:
            return Response({"enabled": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ تحويل enabled إلى Boolean بشكل آمن (يدعم true/false و 1/0 و yes/no)
        def _to_bool(v):
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return bool(int(v))
            s = str(v).strip().lower()
            if s in {"true", "1", "yes", "y", "on"}:
                return True
            if s in {"false", "0", "no", "n", "off"}:
                return False
            # أي قيمة أخرى تعتبر خطأ في الإدخال
            raise ValueError("قيمة enabled غير صالحة. استخدم true/false أو 1/0.")

        try:
            enabled_bool = _to_bool(enabled)
        except ValueError as e:
            return Response({"enabled": [str(e)]}, status=status.HTTP_400_BAD_REQUEST)

        # ✅ حفظ الحالة في قاعدة البيانات إذا كان الحقل موجوداً في User
        if hasattr(request.user, "location_sharing_enabled"):
            try:
                request.user.location_sharing_enabled = enabled_bool
                request.user.save(update_fields=["location_sharing_enabled"])
            except Exception:
                # لا نكسر الـ API لو حصل خطأ غير متوقع أثناء الحفظ
                return Response({"detail": "تعذر حفظ حالة مشاركة الموقع."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            # إن لم يكن الحقل موجوداً، نرجّع رسالة واضحة
            return Response(
                {"detail": "حقل location_sharing_enabled غير موجود في نموذج المستخدم. أضفه في accounts/models.py ثم نفّذ migrations."},
                status=status.HTTP_501_NOT_IMPLEMENTED,
            )

        return Response({"enabled": enabled_bool}, status=status.HTTP_200_OK)