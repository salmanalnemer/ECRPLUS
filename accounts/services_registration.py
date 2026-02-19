# accounts/services_registration.py
from __future__ import annotations

import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.core.cache import cache

from accounts.services_otp import send_login_otp

logger = logging.getLogger(__name__)
User = get_user_model()


@dataclass(frozen=True)
class RegistrationResult:
    user_id: int
    otp_id: int
    otp_expires_at: timezone.datetime


def _cache_key_reg_ip(ip: str) -> str:
    return f"reg:ip:{ip}"


def _rate_limit_ip(ip: str, limit: int = 20, window_seconds: int = 10 * 60) -> bool:
    """
    Rate limit للتسجيل حسب IP لتخفيف السبام:
    - 20 تسجيل/10 دقائق لكل IP (تقدر تغيرها)
    """
    if not ip:
        return True
    key = _cache_key_reg_ip(ip)
    current = cache.get(key)
    if current is None:
        cache.set(key, 1, timeout=window_seconds)
        return True
    if int(current) >= limit:
        return False
    try:
        cache.incr(key)
    except Exception:
        cache.set(key, int(current) + 1, timeout=window_seconds)
    return True


def register_user_and_send_otp(
    *,
    national_id: str,
    full_name: str,
    email: str,
    phone: str,
    organization_id: int,
    user_group_id: int,
    region_id: int | None,
    password: str,
    ip: str = "unknown",
    user_agent: str = "",
) -> RegistrationResult:
    """
    ينشئ مستخدم جديد + يرسل OTP إلى بريده مباشرة.
    - لا يغيّر موديل User
    - يعتمد على clean() داخل User (مثل إلزام المنطقة إلا SYSADMIN)
    """
    if not _rate_limit_ip(ip):
        raise ValidationError("تم تجاوز حد التسجيل من هذا الاتصال. حاول لاحقًا.")

    # تنظيف بسيط قبل الدخول للموديل
    national_id = (national_id or "").strip()
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()
    phone = (phone or "").strip()

    if not national_id:
        raise ValidationError({"national_id": "رقم الهوية مطلوب."})
    if not full_name:
        raise ValidationError({"full_name": "الاسم الكامل مطلوب."})
    if not email:
        raise ValidationError({"email": "البريد الإلكتروني مطلوب."})
    if not phone:
        raise ValidationError({"phone": "رقم الجوال مطلوب."})
    if not password or len(password) < 8:
        raise ValidationError({"password": "كلمة المرور مطلوبة ويجب ألا تقل عن 8 أحرف."})

    with transaction.atomic():
        user = User(
            national_id=national_id,
            full_name=full_name,
            email=email,
            phone=phone,
            organization_id=organization_id,
            user_group_id=user_group_id,
            region_id=region_id,
            is_active=True,
            is_staff=False,
        )
        user.set_password(password)

        # هذا سيستدعي clean() ويطبق قواعدك (مثل إلزام المنطقة لغير SYSADMIN)
        user.full_clean()
        user.save()

        # بعد الإنشاء: إرسال OTP
        otp_res = send_login_otp(user, ip=ip, user_agent=user_agent)

    logger.info("User registered user_id=%s email=%s ip=%s", user.id, user.email, ip)

    return RegistrationResult(
        user_id=user.id,
        otp_id=otp_res.otp_id,
        otp_expires_at=otp_res.expires_at,
    )
