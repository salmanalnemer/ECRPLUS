# accounts/models_auth.py
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import make_password, check_password


class EmailVerification(models.Model):
    """
    حالة تفعيل البريد للمستخدم - بدون تعديل جدول User.
    """
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_verification",
        verbose_name="المستخدم",
    )
    is_verified = models.BooleanField("مفعّل", default=False)
    verified_at = models.DateTimeField("تاريخ التفعيل", null=True, blank=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "تفعيل البريد"
        verbose_name_plural = "تفعيل البريد"

    def __str__(self) -> str:
        return f"{self.user} - {'مفعّل' if self.is_verified else 'غير مفعّل'}"

    def mark_verified(self) -> None:
        self.is_verified = True
        self.verified_at = timezone.now()
        self.save(update_fields=["is_verified", "verified_at", "updated_at"])


class EmailOTP(models.Model):
    """
    OTP مرتبط بمحاولة دخول:
    - نخزن الكود بشكل HASH (وليس نصًا صريحًا) لأمان أعلى.
    - صلاحية افتراضية: 10 دقائق
    - حد للمحاولات
    """
    user = models.ForeignKey(
        settings.AUTH_user_MODEL if hasattr(settings, "AUTH_user_MODEL") else settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_otps",
        verbose_name="المستخدم",
    )

    purpose = models.CharField("الغرض", max_length=30, default="login")  # login / reset / ...
    code_hash = models.CharField("تجزئة الكود", max_length=255)

    expires_at = models.DateTimeField("ينتهي في")
    max_attempts = models.PositiveIntegerField("الحد الأقصى للمحاولات", default=5)
    attempts = models.PositiveIntegerField("عدد المحاولات", default=0)

    is_used = models.BooleanField("مستخدم", default=False)
    used_at = models.DateTimeField("تاريخ الاستخدام", null=True, blank=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)

    class Meta:
        verbose_name = "رمز تحقق OTP"
        verbose_name_plural = "رموز التحقق OTP"
        indexes = [
            models.Index(fields=["user", "purpose", "is_used"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.user} - {self.purpose} - {'used' if self.is_used else 'pending'}"

    def clean(self) -> None:
        super().clean()
        if self.expires_at and self.expires_at <= timezone.now():
            # السماح بالحفظ، لكن منطقيًا هذا OTP منتهي
            return

    @classmethod
    def create_otp(cls, user, code: str, minutes_valid: int = 10, purpose: str = "login") -> "EmailOTP":
        if not code or len(code) < 4:
            raise ValidationError("OTP غير صالح.")
        return cls.objects.create(
            user=user,
            purpose=purpose,
            code_hash=make_password(code),
            expires_at=timezone.now() + timezone.timedelta(minutes=minutes_valid),
        )

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def verify(self, code: str) -> bool:
        """
        تحقق آمن:
        - يمنع المحاولات الزائدة
        - يمنع استخدام الكود أكثر من مرة
        """
        if self.is_used or self.is_expired():
            return False
        if self.attempts >= self.max_attempts:
            return False

        self.attempts += 1
        ok = check_password(code, self.code_hash)

        if ok:
            self.is_used = True
            self.used_at = timezone.now()
            self.save(update_fields=["attempts", "is_used", "used_at"])
            return True

        self.save(update_fields=["attempts"])
        return False
