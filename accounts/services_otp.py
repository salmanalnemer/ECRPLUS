"""accounts.services_otp

خدمات OTP لتسجيل الدخول وإعادة تعيين كلمة المرور.
- تخزين OTP في Cache لمدة محددة
- إرسال OTP عبر البريد الإلكتروني
- في وضع DEBUG: عند فشل الإرسال يتم طباعة OTP في الكونسول لتسهيل التطوير
"""

import random
import logging
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

OTP_EXPIRE_SECONDS = 300  # 5 دقائق


def _generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def _cache_key(purpose: str, user_id: int) -> str:
    return f"otp:{purpose}:{user_id}"


def store_otp(purpose: str, user_id: int, otp: str) -> None:
    cache.set(_cache_key(purpose, user_id), otp, OTP_EXPIRE_SECONDS)


def get_otp(purpose: str, user_id: int):
    return cache.get(_cache_key(purpose, user_id))


def clear_otp(purpose: str, user_id: int) -> None:
    cache.delete(_cache_key(purpose, user_id))


def _send_email(subject: str, message: str, recipient: str, *, ip=None) -> bool:
    """Try to send email. Returns True if sent, False if failed."""
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=[recipient],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("OTP email send failed", extra={"recipient": recipient, "ip": ip})
        return False


def send_login_otp(user, ip=None) -> bool:
    otp = _generate_otp()
    store_otp("login", user.id, otp)

    subject = "رمز التحقق لتسجيل الدخول - ECR"
    message = (
        f"مرحبًا {getattr(user, 'full_name', '')}\n\n"
        f"رمز التحقق الخاص بك هو:\n\n{otp}\n\n"
        "صالح لمدة 5 دقائق.\n"
        "إذا لم تطلب تسجيل الدخول تجاهل الرسالة."
    )

    sent = _send_email(subject, message, user.email, ip=ip)
    if not sent and getattr(settings, "DEBUG", False):
        print(f"[ECR][DEBUG] LOGIN OTP for {user.email} = {otp}")
    return sent


def send_password_reset_otp(user, ip=None) -> bool:
    otp = _generate_otp()
    store_otp("reset", user.id, otp)

    subject = "رمز إعادة تعيين كلمة المرور - ECR"
    message = (
        f"مرحبًا {getattr(user, 'full_name', '')}\n\n"
        f"رمز إعادة تعيين كلمة المرور:\n\n{otp}\n\n"
        "صالح لمدة 5 دقائق.\n"
        "إذا لم تطلب إعادة التعيين تجاهل الرسالة."
    )

    sent = _send_email(subject, message, user.email, ip=ip)
    if not sent and getattr(settings, "DEBUG", False):
        print(f"[ECR][DEBUG] RESET OTP for {user.email} = {otp}")
    return sent


def send_email_verification_otp(user, ip=None, user_agent: str = "") -> bool:
    """Send OTP for email verification (account activation)."""
    otp = _generate_otp()
    store_otp("verify", user.id, otp)

    subject = "رمز تفعيل الحساب - ECR"
    message = (
        f"مرحبًا {getattr(user, 'full_name', '')}\n\n"
        f"رمز تفعيل حسابك هو:\n\n{otp}\n\n"
        "صالح لمدة 5 دقائق.\n"
        "إذا لم تطلب إنشاء حساب تجاهل الرسالة."
    )

    sent = _send_email(subject, message, user.email, ip=ip)
    if not sent and getattr(settings, "DEBUG", False):
        print(f"[ECR][DEBUG] VERIFY OTP for {user.email} = {otp}")
    return sent
