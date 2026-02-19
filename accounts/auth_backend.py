# accounts/auth_backend.py
from __future__ import annotations

from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()


class NationalIdOrEmailBackend(ModelBackend):
    """
    يسمح بتسجيل الدخول باستخدام:
    - رقم الهوية national_id
    - أو البريد الإلكتروني email
    مع كلمة المرور.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None

        identifier = (username or "").strip()
        if not identifier:
            return None

        try:
            user = User.objects.get(Q(email__iexact=identifier) | Q(national_id=identifier))
        except User.DoesNotExist:
            return None

        if not user.check_password(password):
            return None

        if not self.user_can_authenticate(user):
            return None

        return user
