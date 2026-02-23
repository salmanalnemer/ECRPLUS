from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .services_otp import get_otp, clear_otp, send_password_reset_otp

logger = logging.getLogger(__name__)
User = get_user_model()

# محاولات إدخال OTP (خلال نافذة صلاحية OTP)
MAX_OTP_ATTEMPTS = 5
OTP_ATTEMPTS_TTL_SECONDS = 300  # 5 دقائق (نفس OTP_EXPIRE_SECONDS في services_otp غالبًا)


def _attempts_key(user_id: int) -> str:
    return f"otp:reset_attempts:{user_id}"


def _inc_attempts(user_id: int) -> int:
    key = _attempts_key(user_id)
    current = cache.get(key, 0) or 0
    current = int(current) + 1
    cache.set(key, current, OTP_ATTEMPTS_TTL_SECONDS)
    return current


def _reset_attempts(user_id: int) -> None:
    cache.delete(_attempts_key(user_id))


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/request/
    Body: { "national_id": "..." }

    المطلوب منك:
    - إذا الهوية غير موجودة: نرجع رسالة صريحة (404)
    - إذا ما عنده ايميل: 400
    """

    permission_classes = [AllowAny]

    def post(self, request):
        national_id = (request.data.get("national_id") or "").strip()
        if not national_id:
            return Response({"national_id": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(national_id=national_id).first()

        # ✅ إظهار تنبيه صريح (حسب طلبك)
        if not user:
            return Response(
                {"detail": "المستخدم غير مسجل في النظام. يرجى إنشاء حساب أو التواصل مع الدعم الفني."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if not getattr(user, "email", None):
            return Response(
                {"detail": "لا يوجد بريد إلكتروني مرتبط بالحساب. يرجى التواصل مع الدعم الفني."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        _reset_attempts(user.id)

        sent = send_password_reset_otp(user, ip=request.META.get("REMOTE_ADDR"))
        if not sent:
            return Response(
                {"detail": "حدث خطأ أثناء إرسال الرمز. حاول لاحقاً."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {"detail": "تم إرسال رمز التحقق إلى بريدك الإلكتروني."},
            status=status.HTTP_200_OK,
        )


class PasswordResetVerifyView(APIView):
    """
    POST /api/auth/password-reset/verify/
    Body: { "national_id": "...", "otp": "123456" }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        national_id = (request.data.get("national_id") or "").strip()
        otp = (request.data.get("otp") or "").strip()

        if not national_id:
            return Response({"national_id": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)
        if not otp:
            return Response({"otp": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(national_id=national_id).first()
        if not user:
            # حسب طلبك: صريح
            return Response(
                {"detail": "المستخدم غير مسجل في النظام. يرجى إنشاء حساب أو التواصل مع الدعم الفني."},
                status=status.HTTP_404_NOT_FOUND,
            )

        attempts = cache.get(_attempts_key(user.id), 0) or 0
        if int(attempts) >= MAX_OTP_ATTEMPTS:
            return Response({"detail": "تجاوزت عدد المحاولات."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cached = get_otp("reset", user.id)
        if not cached:
            return Response({"detail": "انتهت صلاحية الرمز أو لم يتم إرساله."}, status=status.HTTP_400_BAD_REQUEST)

        if str(cached) != str(otp):
            now_attempts = _inc_attempts(user.id)
            if now_attempts >= MAX_OTP_ATTEMPTS:
                return Response({"detail": "تجاوزت عدد المحاولات."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response({"detail": "رمز التحقق غير صحيح."}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"detail": "تم التحقق بنجاح."}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/
    Body: { "national_id": "...", "otp": "123456", "new_password": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request):
        national_id = (request.data.get("national_id") or "").strip()
        otp = (request.data.get("otp") or "").strip()
        new_password = request.data.get("new_password") or ""

        if not national_id:
            return Response({"national_id": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)
        if not otp:
            return Response({"otp": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)
        if not new_password:
            return Response({"new_password": ["هذا الحقل مطلوب."]}, status=status.HTTP_400_BAD_REQUEST)
        if len(new_password) < 8:
            return Response({"new_password": ["كلمة المرور يجب أن تكون 8 أحرف على الأقل."]}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.filter(national_id=national_id).first()
        if not user:
            return Response(
                {"detail": "المستخدم غير مسجل في النظام. يرجى إنشاء حساب أو التواصل مع الدعم الفني."},
                status=status.HTTP_404_NOT_FOUND,
            )

        attempts = cache.get(_attempts_key(user.id), 0) or 0
        if int(attempts) >= MAX_OTP_ATTEMPTS:
            return Response({"detail": "تجاوزت عدد المحاولات."}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        cached = get_otp("reset", user.id)
        if not cached:
            return Response({"detail": "انتهت صلاحية الرمز أو لم يتم إرساله."}, status=status.HTTP_400_BAD_REQUEST)

        if str(cached) != str(otp):
            now_attempts = _inc_attempts(user.id)
            if now_attempts >= MAX_OTP_ATTEMPTS:
                return Response({"detail": "تجاوزت عدد المحاولات."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
            return Response({"detail": "رمز التحقق غير صحيح."}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            user.set_password(new_password)
            user.save(update_fields=["password"])

            # نلغي OTP ومحاولاته بعد نجاح التغيير
            clear_otp("reset", user.id)
            _reset_attempts(user.id)

        return Response({"detail": "تم تغيير كلمة المرور بنجاح."}, status=status.HTTP_200_OK)