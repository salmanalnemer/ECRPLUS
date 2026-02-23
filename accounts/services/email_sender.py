from __future__ import annotations

import logging
from django.conf import settings
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)


def send_password_reset_otp_email(*, to_email: str, otp: str) -> None:
    subject = "رمز إعادة تعيين كلمة المرور - ECR"
    text_body = (
        "مرحباً،\n\n"
        f"رمز التحقق لإعادة تعيين كلمة المرور هو: {otp}\n"
        "صلاحية الرمز: 10 دقائق.\n\n"
        "إذا لم تطلب ذلك، تجاهل الرسالة.\n"
    )

    msg = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
        to=[to_email],
    )
    msg.send(fail_silently=False)
    logger.info("Password reset OTP email sent to=%s", to_email)