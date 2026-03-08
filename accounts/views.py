import logging

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_http_methods

from .forms import LoginForm, OTPForm, ForgotPasswordRequestForm, ResetPasswordForm
from .services_otp import send_login_otp, send_password_reset_otp, get_otp, clear_otp

logger = logging.getLogger(__name__)
User = get_user_model()


def _client_ip(request):
    xff = request.META.get("HTTP_X_FORWARDED_FOR")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _rate_limit_key(action: str, ip: str) -> str:
    return f"rl:{action}:{ip}"


def _check_rate_limit(request, action: str, limit=10, window=300) -> bool:
    ip = _client_ip(request) or "unknown"
    key = _rate_limit_key(action, ip)
    count = cache.get(key, 0)
    if count >= limit:
        return False
    cache.set(key, count + 1, window)
    return True


def _is_safe_next(request, next_url: str) -> bool:
    return bool(
        next_url
        and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
    )


def _default_success_redirect():
    return reverse("ecr_dashcad")


@require_http_methods(["GET", "POST"])
def login_view(request):

    if request.user.is_authenticated:
        next_url = request.GET.get("next")
        if _is_safe_next(request, next_url):
            return redirect(next_url)
        return redirect("ecr_dashcad")

    if request.method == "POST" and not _check_rate_limit(request, "login", limit=20, window=300):
        messages.error(request, "محاولات كثيرة. حاول لاحقًا.")
        return render(request, "accounts/login.html", {"form": LoginForm()})

    form = LoginForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        identifier = form.cleaned_data["identifier"].strip()
        password = form.cleaned_data["password"]

        user = authenticate(request, username=identifier, password=password)

        if not user:
            messages.error(request, "بيانات الدخول غير صحيحة.")
            return render(request, "accounts/login.html", {"form": form})

        if not user.is_active:
            messages.error(request, "هذا الحساب غير مفعل.")
            return render(request, "accounts/login.html", {"form": form})

        if not getattr(user, "email", None):
            messages.error(request, "لا يوجد بريد إلكتروني مسجل لهذا الحساب.")
            return render(request, "accounts/login.html", {"form": form})

        request.session["otp_pending_user_id"] = user.id
        request.session["otp_purpose"] = "login"
        request.session["otp_auth_backend"] = getattr(user, "backend", None)

        next_url = request.POST.get("next") or request.GET.get("next")
        if _is_safe_next(request, next_url):
            request.session["otp_next_url"] = next_url

        request.session.modified = True

        sent = send_login_otp(user, ip=_client_ip(request))
        if sent:
            messages.success(request, "تم إرسال رمز التحقق إلى بريدك الإلكتروني.")
        else:
            messages.warning(
                request,
                "تعذر إرسال البريد الآن. تحقق من إعدادات SMTP/DNS أو جرّب بريد Gmail."
            )

        return redirect("accounts_verify_otp")

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def verify_otp_view(request):

    pending_user_id = request.session.get("otp_pending_user_id")
    purpose = request.session.get("otp_purpose")

    if not pending_user_id or purpose not in ("login", "reset"):
        messages.error(request, "جلسة التحقق غير صالحة.")
        return redirect("accounts_login")

    form = OTPForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        otp = form.cleaned_data["otp"].strip()
        expected = get_otp(purpose, pending_user_id)

        if not expected or otp != expected:
            messages.error(request, "رمز التحقق غير صحيح.")
            return render(request, "accounts/verify_otp.html", {"form": form})

        clear_otp(purpose, pending_user_id)

        if purpose == "login":

            user = User.objects.filter(id=pending_user_id).first()

            backend = request.session.get("otp_auth_backend")
            if not backend:
                backend = settings.AUTHENTICATION_BACKENDS[0]

            login(request, user, backend=backend)

            request.session.pop("otp_pending_user_id", None)
            request.session.pop("otp_purpose", None)
            request.session.pop("otp_auth_backend", None)

            next_url = request.session.pop("otp_next_url", None)
            if _is_safe_next(request, next_url):
                return redirect(next_url)

            return redirect("ecr_dashcad")

        request.session["reset_verified_user_id"] = pending_user_id
        return redirect("accounts_reset_password")

    return render(request, "accounts/verify_otp.html", {"form": form})


@require_http_methods(["GET", "POST"])
def forgot_password_view(request):

    form = ForgotPasswordRequestForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        identifier = form.cleaned_data["identifier"].strip()

        user = (
            User.objects.filter(email__iexact=identifier).first()
            or User.objects.filter(national_id=identifier).first()
        )

        if not user:
            messages.error(request, "لا يوجد حساب بهذه البيانات.")
            return render(request, "accounts/forgot_password.html", {"form": form})

        request.session["otp_pending_user_id"] = user.id
        request.session["otp_purpose"] = "reset"

        send_password_reset_otp(user, ip=_client_ip(request))

        return redirect("accounts_verify_otp")

    return render(request, "accounts/forgot_password.html", {"form": form})


@require_http_methods(["GET", "POST"])
def reset_password_view(request):

    user_id = request.session.get("reset_verified_user_id")

    if not user_id:
        return redirect("accounts_forgot_password")

    user = User.objects.filter(id=user_id).first()

    form = ResetPasswordForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        user.set_password(form.cleaned_data["new_password1"])
        user.save(update_fields=["password"])

        request.session.pop("reset_verified_user_id", None)

        messages.success(request, "تم تغيير كلمة المرور.")
        return redirect("accounts_login")

    return render(request, "accounts/reset_password.html", {"form": form})


# -------------------------------------------------------------------
# Compatibility alias
# -------------------------------------------------------------------
from organizations.models import Organization
from usergroups.models import UserGroup
from regions.models import Region
from responders.models import Responder


def register_view(request):

    if request.method == "POST":

        full_name = request.POST.get("full_name")
        national_id = request.POST.get("national_id")
        email = request.POST.get("email")
        phone = request.POST.get("phone")

        organization_id = request.POST.get("organization")
        group_id = request.POST.get("group")
        region_id = request.POST.get("region")

        password = request.POST.get("password")

        user = User.objects.create_user(
            email=email,
            full_name=full_name,
            national_id=national_id,
            phone=phone,
            organization_id=organization_id,
            user_group_id=group_id,
            region_id=region_id,
            password=password
        )

        # إضافة المستخدم تلقائياً إلى مجموعة التطبيق
        try:
            group = UserGroup.objects.get(code="ECRMOBIL")
            user.user_group = group
            user.save(update_fields=["user_group"])
        except Exception:
            pass

        # إنشاء Responder تلقائياً
        try:
            Responder.objects.create(
                user=user,
                region_id=region_id,
                is_active=True
            )
        except Exception:
            pass

        messages.success(request, "تم إنشاء الحساب")
        return redirect("accounts_login")

    organizations = Organization.objects.all()
    groups = UserGroup.objects.filter(is_active=True)
    regions = Region.objects.filter(is_active=True)

    return render(
        request,
        "accounts/register.html",
        {
            "organizations": organizations,
            "groups": groups,
            "regions": regions,
        }
    )


@login_required
def ecr_dashcad(request):
    return render(request, "dashboard/main_dashboard.html")