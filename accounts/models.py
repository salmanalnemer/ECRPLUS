from __future__ import annotations
import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models
from django.utils import timezone

from .user_manager import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """
    مستخدم نظام ECR:
    - يعتمد البريد الإلكتروني كـ USERNAME_FIELD
    - مرتبط بكتلوج المجموعات (UserGroup) لتحديد صلاحية الوصول (ويب/تطبيق/كلاهما)
    - مرتبط بكتلوج الجهات (Organization)
    - مرتبط بكتلوج المناطق (Region) (إجباري إلا لمدير النظام)
    """

    HEALTH_COURSE_LIFE_AMBASSADOR = "life_ambassador"
    HEALTH_COURSE_FIRST_AID_EIGHT = "first_aid_8"
    HEALTH_COURSE_OTHER = "other"

    HEALTH_COURSE_CHOICES = (
        (HEALTH_COURSE_LIFE_AMBASSADOR, "سفير الحياة"),
        (HEALTH_COURSE_FIRST_AID_EIGHT, "الثمان الأولى للإسعافات الأولية"),
        (HEALTH_COURSE_OTHER, "أخرى"),
    )

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

    # دورات المواطن الصحية
    citizen_health_courses = models.JSONField(
        "دوراتي الصحية",
        default=list,
        blank=True,
        help_text="اختيار متعدد للدورات الصحية الخاصة بالمواطن.",
    )

    citizen_other_health_courses = models.TextField(
        "دورات أخرى",
        blank=True,
        default="",
        help_text="اكتب دورة أو أكثر عند اختيار (أخرى)، ويمكن الفصل بين الدورات بفاصلة أو سطر جديد.",
    )

    # ✅ تحكم مشاركة الموقع (يتم تحديثه من التطبيق)
    location_sharing_enabled = models.BooleanField("مشاركة الموقع", default=True, db_index=True)

    # حقول نظامية
    # ملاحظة: لسيناريو التفعيل عبر OTP، اجعل المستخدم الجديد is_active=False عند التسجيل.
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

    @classmethod
    def allowed_health_courses(cls) -> set[str]:
        return {
            cls.HEALTH_COURSE_LIFE_AMBASSADOR,
            cls.HEALTH_COURSE_FIRST_AID_EIGHT,
            cls.HEALTH_COURSE_OTHER,
        }

    def _organization_is_citizen(self) -> bool:
        org_name = ""
        if self.organization_id and getattr(self, "organization", None):
            org_name = (self.organization.name or "").strip().lower()

        return org_name in {"مواطن", "citizen"}

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

        # تنظيف والتحقق من الدورات الصحية
        if self.citizen_health_courses is None:
            self.citizen_health_courses = []

        if not isinstance(self.citizen_health_courses, list):
            raise ValidationError({"citizen_health_courses": "صيغة دوراتي الصحية غير صحيحة."})

        allowed_courses = self.allowed_health_courses()
        normalized_courses: list[str] = []

        for item in self.citizen_health_courses:
            value = str(item).strip()
            if not value:
                continue
            if value not in allowed_courses:
                raise ValidationError({"citizen_health_courses": f"قيمة غير مسموحة: {value}"})
            if value not in normalized_courses:
                normalized_courses.append(value)

        self.citizen_health_courses = normalized_courses
        self.citizen_other_health_courses = (self.citizen_other_health_courses or "").strip()

        is_citizen = self._organization_is_citizen()

        if is_citizen:
            if not self.citizen_health_courses:
                raise ValidationError({"citizen_health_courses": "حقل دوراتي الصحية مطلوب عند اختيار الجهة مواطن."})

            if (
                self.HEALTH_COURSE_OTHER in self.citizen_health_courses
                and not self.citizen_other_health_courses
            ):
                raise ValidationError({"citizen_other_health_courses": "اكتب اسم دورة واحدة على الأقل عند اختيار أخرى."})
        else:
            # إذا لم تكن الجهة مواطن، نفرغ الحقول حتى لا تُخزن بالخطأ
            self.citizen_health_courses = []
            self.citizen_other_health_courses = ""

        # المنطقة إلزامية إلا إذا كانت مجموعة SYSADMIN
        if self.user_group and getattr(self.user_group, "code", None) == "SYSADMIN":
            # مسموح region = null
            return

        # غير SYSADMIN: لازم منطقة
        if not self.region:
            raise ValidationError({"region": "حقل المنطقة إلزامي (يسمح بتجاوزه فقط لمجموعة مدير النظام)."})


class EmailVerification(models.Model):
    """
    سجل اختياري لحالة التحقق من البريد (مفيد للتدقيق/التقارير).
    تفعيل الحساب النهائي يتم عبر User.is_active.
    """

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_verification")
    verified_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "تحقق البريد"
        verbose_name_plural = "تحقق البريد"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None


class EmailOTP(models.Model):
    """
    OTP للبريد:
    - إصدار كود (6 أرقام) للتفعيل أو لإعادة تعيين كلمة المرور
    - تحقق آمن: غير مستخدم + غير منتهي الصلاحية
    """

    PURPOSE_VERIFY_EMAIL = "verify_email"
    PURPOSE_RESET_PASSWORD = "reset_password"

    PURPOSE_CHOICES = (
        (PURPOSE_VERIFY_EMAIL, "Verify Email"),
        (PURPOSE_RESET_PASSWORD, "Reset Password"),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="email_otps")
    purpose = models.CharField(max_length=32, choices=PURPOSE_CHOICES)
    code = models.CharField(max_length=10, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        verbose_name = "رمز تحقق البريد"
        verbose_name_plural = "رموز تحقق البريد"
        indexes = [
            models.Index(fields=["user", "purpose", "code"]),
        ]

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def is_used(self) -> bool:
        return self.used_at is not None

    @staticmethod
    def generate_code(length: int = 6) -> str:
        digits = "0123456789"
        return "".join(secrets.choice(digits) for _ in range(length))

    @classmethod
    def issue_otp(cls, *, user, purpose: str, ttl_minutes: int = 10, length: int = 6) -> "EmailOTP":
        now = timezone.now()
        return cls.objects.create(
            user=user,
            purpose=purpose,
            code=cls.generate_code(length=length),
            expires_at=now + timedelta(minutes=ttl_minutes),
        )

    @classmethod
    def verify_otp(cls, *, user, code: str, purpose: str) -> bool:
        """
        يرجع True عند نجاح التحقق ويقوم بتمييز الرمز كمستخدم.
        """
        code = (code or "").strip()
        if not code:
            return False

        otp = (
            cls.objects
            .filter(user=user, purpose=purpose, code=code, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            return False
        if otp.is_expired():
            return False

        otp.used_at = timezone.now()
        otp.save(update_fields=["used_at"])
        return True