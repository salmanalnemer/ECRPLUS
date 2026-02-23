from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class PasswordResetOTP(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    attempts = models.PositiveIntegerField(default=0)
    is_used = models.BooleanField(default=False)

    class Meta:
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["created_at"]),
        ]

    def is_expired(self) -> bool:
        return timezone.now() > self.created_at + timedelta(minutes=10)

    @staticmethod
    def generate_otp() -> str:
        # 6 digits
        return f"{secrets.randbelow(1_000_000):06d}"

    @staticmethod
    def hash_otp(otp: str) -> str:
        return hashlib.sha256(otp.encode("utf-8")).hexdigest()