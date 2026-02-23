from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AbstractBaseUser
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

logger = logging.getLogger(__name__)
UserModel = get_user_model()


class NationalIdTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    JWT login باستخدام:
      - national_id + password فقط

    ملاحظة مهمة:
      TokenObtainPairSerializer الافتراضي يضيف حقل USERNAME_FIELD (عندك = email)
      وهذا يسبب رسالة: "هذا الحقل مطلوب" (email required).
      لذلك هنا نحذف حقل البريد من الـ serializer ونستبدله بحقل national_id.
    """

    national_id = serializers.CharField(required=True, allow_blank=False, write_only=True)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # ✅ احذف حقل username_field الافتراضي (عندك email) حتى مايصير مطلوب في الطلب
        # TokenObtainPairSerializer يضيفه تلقائياً بناءً على UserModel.USERNAME_FIELD
        self.fields.pop(self.username_field, None)

        # ✅ نؤكد على بقاء password فقط (بدون إعادة تعريف مزدوجة)
        if "password" in self.fields:
            self.fields["password"].required = True
            self.fields["password"].allow_blank = False

    def validate(self, attrs: Dict[str, Any]) -> Dict[str, Any]:
        national_id = (attrs.get("national_id") or "").strip()
        password = attrs.get("password")

        if not national_id:
            raise serializers.ValidationError({"national_id": _("هذا الحقل مطلوب.")})

        if not password:
            raise serializers.ValidationError({"password": _("هذا الحقل مطلوب.")})

        user: Optional[AbstractBaseUser] = None

        # لازم يكون موديل المستخدم عندك فيه حقل national_id
        if not hasattr(UserModel, "national_id"):
            raise serializers.ValidationError(
                {"non_field_errors": [_("حقل national_id غير موجود في موديل المستخدم.")]},
            )

        try:
            user = UserModel.objects.filter(national_id=national_id).first()
        except Exception as e:
            logger.exception("Query by national_id failed: %s", e)

        if user is None:
            raise serializers.ValidationError({
                "national_id": "المستخدم غير مسجل في النظام. فضلاً قم بإنشاء حساب أو تواصل مع الدعم الفني."
            })

        # لو موجود لكن غير نشط (اختياري)
        if not getattr(user, "is_active", True):
            raise serializers.ValidationError({
                "non_field_errors": ["الحساب غير نشط. تواصل مع الدعم الفني."]
            })

        if not user.check_password(password):
            raise serializers.ValidationError({
                "password": "كلمة المرور غير صحيحة."
            })

        self.user = user  # type: ignore[assignment]

        # ✅ نمرر للـ SimpleJWT قيمة USERNAME_FIELD الحقيقية (email) من المستخدم
        # حتى يبني التوكن داخلياً بشكل صحيح
        data = super().validate({"password": password, self.username_field: user.get_username()})
        data["user_id"] = getattr(user, "id", None)
        data["full_name"] = getattr(user, "full_name", "")
        data["national_id"] = getattr(user, "national_id", "")
        return data


class NationalIdTokenObtainPairView(TokenObtainPairView):
    permission_classes = [AllowAny]
    serializer_class = NationalIdTokenObtainPairSerializer

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        # ✅ يقرأ JSON صح
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)