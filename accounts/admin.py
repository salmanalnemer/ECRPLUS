# accounts/admin.py
from django.contrib import admin
from django.utils import timezone

from .models import User, EmailOTP, EmailVerification


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "full_name",
        "national_id",
        "email",
        "phone",
        "organization",
        "region",
        "user_group",
        "is_active",
        "is_staff",
    )
    search_fields = ("full_name", "national_id", "email", "phone")
    list_filter = ("is_active", "is_staff", "organization", "region", "user_group")
    ordering = ("-id",)

    # ✅ نخفي حقول Django الافتراضية اللي تسبب لك التكرار (المجموعات/الصلاحيات)
    exclude = ("groups", "user_permissions")


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "purpose", "code", "expires_at", "used_at", "created_at", "expired", "used")
    list_filter = ("purpose", "expires_at", "used_at", "created_at")
    search_fields = ("user__email", "user__national_id", "code")
    ordering = ("-created_at",)

    @admin.display(boolean=True, description="Expired?")
    def expired(self, obj: EmailOTP) -> bool:
        return timezone.now() >= obj.expires_at

    @admin.display(boolean=True, description="Used?")
    def used(self, obj: EmailOTP) -> bool:
        return obj.used_at is not None


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "verified_at", "last_sent_at", "is_verified")
    list_filter = ("verified_at", "last_sent_at")
    search_fields = ("user__email", "user__national_id")
    ordering = ("-id",)

    @admin.display(boolean=True, description="Verified?")
    def is_verified(self, obj: EmailVerification) -> bool:
        return obj.verified_at is not None
