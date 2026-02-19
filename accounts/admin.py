from __future__ import annotations

from django import forms
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth import get_user_model
from .models_auth import EmailOTP, EmailVerification

User = get_user_model()


class UserCreationForm(forms.ModelForm):
    password1 = forms.CharField(label="كلمة المرور", widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="تأكيد كلمة المرور", widget=forms.PasswordInput, required=False)

    class Meta:
        model = User
        fields = (
            "national_id",
            "full_name",
            "email",
            "phone",
            "organization",
            "user_group",
            "region",
            "is_health_practitioner",
            "is_active",
            "is_staff",
        )

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if (p1 or p2) and (p1 != p2):
            raise forms.ValidationError("كلمتا المرور غير متطابقتين.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        p1 = self.cleaned_data.get("password1")
        if p1:
            user.set_password(p1)
        else:
            user.set_unusable_password()
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "national_id",
            "full_name",
            "email",
            "phone",
            "organization",
            "user_group",
            "region",
            "is_health_practitioner",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "user_permissions",
        )


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    add_form = UserCreationForm
    form = UserChangeForm

    model = User

    list_display = ("full_name", "national_id", "email", "phone", "organization", "region", "user_group", "is_active")
    list_filter = ("is_active", "is_staff", "is_superuser", "user_group", "region", "organization")
    search_fields = ("full_name", "national_id", "email", "phone")
    ordering = ("full_name",)

    # تخصيص عرض الحقول
    fieldsets = (
        ("بيانات المستخدم", {"fields": ("national_id", "full_name", "email", "phone")}),
        ("الربط", {"fields": ("organization", "region", "user_group", "is_health_practitioner")}),
        ("صلاحيات النظام", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("معلومات النظام", {"fields": ("last_login",)}),
    )

    add_fieldsets = (
        ("بيانات المستخدم", {"fields": ("national_id", "full_name", "email", "phone")}),
        ("الربط", {"fields": ("organization", "region", "user_group", "is_health_practitioner")}),
        ("كلمة المرور", {"fields": ("password1", "password2")}),
        ("الحالة", {"fields": ("is_active", "is_staff")}),
    )

    readonly_fields = ("last_login",)

    def _is_sysadmin(self, request) -> bool:
        try:
            # إذا ربطت المستخدم بـ user_group
            return bool(getattr(request.user, "user_group", None) and request.user.user_group.code == "SYSADMIN")
        except Exception:
            return False

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        # إخفاء حقل user_group لغير SYSADMIN
        if not self._is_sysadmin(request):
            if "user_group" in form.base_fields:
                form.base_fields.pop("user_group")

        return form

    def save_model(self, request, obj, form, change):
        # منع غير SYSADMIN من تغيير user_group حتى لو أرسله يدويًا
        if change and (not self._is_sysadmin(request)):
            if "user_group" in form.changed_data:
                # تجاهل التغيير
                obj.user_group = User.objects.get(pk=obj.pk).user_group

        obj.full_clean()
        super().save_model(request, obj, form, change)

@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "is_verified", "verified_at", "created_at")
    list_filter = ("is_verified",)
    search_fields = ("user__full_name", "user__national_id", "user__email")
    ordering = ("-created_at",)


@admin.register(EmailOTP)
class EmailOTPAdmin(admin.ModelAdmin):
    list_display = ("user", "purpose", "is_used", "attempts", "max_attempts", "expires_at", "created_at")
    list_filter = ("purpose", "is_used")
    search_fields = ("user__full_name", "user__national_id", "user__email")
    ordering = ("-created_at",)
