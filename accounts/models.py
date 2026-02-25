from __future__ import annotations

from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.utils.translation import gettext_lazy as _

from .user_manager import UserManager
# في نهاية accounts/models.py
from .models_auth import EmailOTP, EmailVerification  # noqa: F401


class User(AbstractBaseUser, PermissionsMixin):
    """
    مستخدم نظام ECR:
    - يعتمد البريد الإلكتروني كـ USERNAME_FIELD
    - مرتبط بكتلوج المجموعات (UserGroup) لتحديد صلاحية الوصول (ويب/تطبيق/كلاهما)
    - مرتبط بكتلوج الجهات (Organization)
    - مرتبط بكتلوج المناطق (Region) (إجباري إلا لمدير النظام)
    """

    national_id = models.CharField("رقم الهوية", max_length=20, unique=True)
    full_name = models.CharField("الاسم الكامل", max_length=255)

    email = models.EmailField("البريد الإلكتروني", unique=True)
    phone = models.CharField("رقم الجوال", max_length=20)

    # كتلوج الجهات
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="الجهة",
    )

    # كتلوج المجموعات (مجموعة واحدة لكل مستخدم حسب المطلوب)
    user_group = models.ForeignKey(
        "usergroups.UserGroup",
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="المجموعة",
        null=True,
        blank=True,
    )

    # كتلوج المناطق (إجباري إلا عند SYSADMIN)
    region = models.ForeignKey(
        "regions.Region",
        on_delete=models.PROTECT,
        related_name="users",
        verbose_name="المنطقة",
        null=True,
        blank=True,
    )

    is_health_practitioner = models.BooleanField("ممارس صحي", default=False)

    # ✅ تحكم مشاركة الموقع (يتم تحديثه من التطبيق)
    location_sharing_enabled = models.BooleanField("مشاركة الموقع", default=True, db_index=True)

    # حقول نظامية
    is_active = models.BooleanField("مفعّل", default=True)
    is_staff = models.BooleanField("موظف لوحة التحكم", default=False)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["national_id", "full_name", "phone"]

    objects = UserManager()

    class Meta:
        verbose_name = "مستخدم"
        verbose_name_plural = "المستخدمون"
        ordering = ["full_name", "national_id"]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.national_id})"

    def clean(self) -> None:
        super().clean()

        # تنظيف البريد
        if self.email:
            self.email = self.email.strip().lower()

        # تحقق بسيط من رقم الجوال (أرقام + طول معقول)
        if self.phone:
            ph = self.phone.strip().replace(" ", "")
            self.phone = ph
            if not ph.replace("+", "").isdigit():
                raise ValidationError({"phone": "رقم الجوال يجب أن يحتوي على أرقام فقط (يسمح بـ + في البداية)."})
            if len(ph) < 9 or len(ph) > 16:
                raise ValidationError({"phone": "طول رقم الجوال غير صحيح."})

        # المنطقة إلزامية إلا إذا كانت مجموعة SYSADMIN
        if self.user_group and self.user_group.code == "SYSADMIN":
            # مسموح region = null
            return

        # غير SYSADMIN: لازم منطقة
        if not self.region:
            raise ValidationError({"region": "حقل المنطقة إلزامي (يسمح بتجاوزه فقط لمجموعة مدير النظام)."})
