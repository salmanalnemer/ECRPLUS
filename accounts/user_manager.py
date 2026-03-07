# accounts/user_manager.py
from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager
from django.core.exceptions import ValidationError
from django.utils import timezone


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(
        self,
        email: str,
        national_id: str,
        full_name: str,
        phone: str,
        organization=None,
        organization_id: int | None = None,
        password: str | None = None,
        **extra_fields,
    ):
        if not email:
            raise ValueError("email is required")
        if not national_id:
            raise ValueError("national_id is required")
        if not full_name:
            raise ValueError("full_name is required")
        if not phone:
            raise ValueError("phone is required")

        email = self.normalize_email(email).strip().lower()
        national_id = str(national_id).strip()
        phone = str(phone).strip()

        # organization إلزامي (حسب موديلك)
        if organization is None and not organization_id:
            raise ValueError("organization (or organization_id) is required")

        user = self.model(
            email=email,
            national_id=national_id,
            full_name=full_name.strip(),
            phone=phone,
            organization=organization,
            organization_id=organization_id,
            **extra_fields,
        )

        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()

        if hasattr(user, "date_joined") and not getattr(user, "date_joined", None):
            user.date_joined = timezone.now()

        # نفّذ clean() وتحقق القيود (زي تحقق رقم الجوال/المنطقة)
        user.full_clean()

        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, national_id: str, full_name: str, phone: str, password: str, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        return self.create_user(email, national_id, full_name, phone, password=password, **extra_fields)