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
    """
    simple rate limit per IP using cache
    """
    ip = _client_ip(request) or "unknown"
    key = _rate_limit_key(action, ip)
    count = cache.get(key, 0)
    if count >= limit:
        return False
    cache.set(key, count + 1, window)
    return True


def _is_safe_next(request, next_url: str) -> bool:
    """
    منع Open Redirect: يسمح فقط بالروابط داخل نفس الهوست.
    """
    return bool(
        next_url
        and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
    )


def _default_success_redirect():
    """
    التحويل الافتراضي بعد تسجيل الدخول (من الويب) -> داشبورد البورتال
    """
    return reverse("ecr_dashcad")


@require_http_methods(["GET", "POST"])
def login_view(request):
    # ✅ إذا كان المستخدم مسجل دخول مسبقًا: لا توديه على admin تلقائياً
    # - لو فيه next آمن (مثلاً /admin/) نروح له
    # - غير ذلك نروح لداشبورد البورتال
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

        # وضع حالة pending في session (لا نسجل دخول فعلي قبل OTP)
        request.session["otp_pending_user_id"] = user.id
        request.session["otp_purpose"] = "login"
        # حفظ الـ backend الذي تم عبره authenticate لتفادي خطأ تعدد الـ backends عند login بعد OTP
        request.session["otp_auth_backend"] = getattr(user, "backend", None)

        # ✅ حفظ next بشكل آمن لمنع Open Redirect
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
                "تعذر إرسال البريد الآن. تحقق من إعدادات SMTP/DNS أو جرّب بريد Gmail. "
                "(في وضع DEBUG قد يظهر الرمز في الكونسول)."
            )
        return redirect("accounts_verify_otp")

    return render(request, "accounts/login.html", {"form": form})


@require_http_methods(["GET", "POST"])
def verify_otp_view(request):
    pending_user_id = request.session.get("otp_pending_user_id")
    purpose = request.session.get("otp_purpose")

    if not pending_user_id or purpose not in ("login", "reset"):
        messages.error(request, "جلسة التحقق غير صالحة. أعد المحاولة.")
        return redirect("accounts_login")

    if request.method == "POST" and not _check_rate_limit(request, "verify_otp", limit=25, window=300):
        messages.error(request, "محاولات كثيرة. حاول لاحقًا.")
        return render(request, "accounts/verify_otp.html", {"form": OTPForm(), "purpose": purpose})

    form = OTPForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        otp = form.cleaned_data["otp"].strip()

        expected = get_otp(purpose, pending_user_id)
        if not expected or otp != expected:
            messages.error(request, "رمز التحقق غير صحيح أو منتهي الصلاحية.")
            return render(request, "accounts/verify_otp.html", {"form": form, "purpose": purpose})

        # OTP صحيح
        clear_otp(purpose, pending_user_id)

        if purpose == "login":
            user = User.objects.filter(id=pending_user_id).first()
            if not user:
                messages.error(request, "الحساب غير موجود.")
                return redirect("accounts_login")

            # مع تعدد AUTHENTICATION_BACKENDS يجب تمرير backend صراحةً لأننا جلبنا المستخدم من DB وليس عبر authenticate
            backend = request.session.get("otp_auth_backend")
            if not backend:
                # افتراضيًا استخدم Backend المصادقة الأساسي (أول عنصر) أو ModelBackend كخيار آمن
                backend = (
                    settings.AUTHENTICATION_BACKENDS[0]
                    if getattr(settings, "AUTHENTICATION_BACKENDS", None)
                    else "django.contrib.auth.backends.ModelBackend"
                )

            login(request, user, backend=backend)

            # تنظيف session flags
            request.session.pop("otp_pending_user_id", None)
            request.session.pop("otp_purpose", None)
            request.session.pop("otp_auth_backend", None)

            messages.success(request, "تم تسجيل الدخول بنجاح.")

            # ✅ إذا جاء الدخول من /admin/ فسيكون next=/admin/ وسنرجع له
            next_url = request.session.pop("otp_next_url", None)
            if _is_safe_next(request, next_url):
                return redirect(next_url)

            # ✅ غير ذلك (الدخول من الويب) -> داشبورد البورتال
            return redirect("ecr_dashcad")

        # reset
        request.session["reset_verified_user_id"] = pending_user_id
        request.session.pop("otp_pending_user_id", None)
        request.session.pop("otp_purpose", None)
        request.session.pop("otp_auth_backend", None)
        return redirect("accounts_reset_password")

    return render(request, "accounts/verify_otp.html", {"form": form, "purpose": purpose})


@require_http_methods(["GET", "POST"])
def forgot_password_view(request):
    if request.method == "POST" and not _check_rate_limit(request, "forgot_password", limit=15, window=300):
        messages.error(request, "محاولات كثيرة. حاول لاحقًا.")
        return render(request, "accounts/forgot_password.html", {"form": ForgotPasswordRequestForm()})

    form = ForgotPasswordRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        identifier = form.cleaned_data["identifier"].strip()

        # نفس منطق authenticate لكن بدون كلمة مرور: نبحث بالهوية أو الإيميل
        user = User.objects.filter(email__iexact=identifier).first() or User.objects.filter(national_id=identifier).first()
        if not user:
            messages.error(request, "لا يوجد حساب بهذه البيانات.")
            return render(request, "accounts/forgot_password.html", {"form": form})

        if not getattr(user, "email", None):
            messages.error(request, "لا يوجد بريد إلكتروني مسجل لهذا الحساب.")
            return render(request, "accounts/forgot_password.html", {"form": form})

        request.session["otp_pending_user_id"] = user.id
        request.session["otp_purpose"] = "reset"
        request.session.modified = True

        sent = send_password_reset_otp(user, ip=_client_ip(request))
        if sent:
            messages.success(request, "تم إرسال رمز إعادة التعيين إلى بريدك الإلكتروني.")
        else:
            messages.warning(
                request,
                "تعذر إرسال البريد الآن. تحقق من إعدادات SMTP/DNS أو جرّب بريد Gmail. "
                "(في وضع DEBUG قد يظهر الرمز في الكونسول)."
            )
        return redirect("accounts_verify_otp")

    return render(request, "accounts/forgot_password.html", {"form": form})


@require_http_methods(["GET", "POST"])
def reset_password_view(request):
    user_id = request.session.get("reset_verified_user_id")
    if not user_id:
        messages.error(request, "يجب التحقق أولاً.")
        return redirect("accounts_forgot_password")

    user = User.objects.filter(id=user_id).first()
    if not user:
        messages.error(request, "الحساب غير موجود.")
        return redirect("accounts_forgot_password")

    form = ResetPasswordForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user.set_password(form.cleaned_data["new_password1"])
        user.save(update_fields=["password"])

        request.session.pop("reset_verified_user_id", None)
        messages.success(request, "تم تغيير كلمة المرور بنجاح. يمكنك تسجيل الدخول الآن.")
        return redirect("accounts_login")

    return render(request, "accounts/reset_password.html", {"form": form})


# -------------------------------------------------------------------
# Compatibility alias (إذا عندك رابط قديم)
# -------------------------------------------------------------------
# إذا كان مشروعك يستخدم register_view بدل register
def register_view(request):
    # لو عندك register فعلي سابقًا، اربطه هنا أو احذف هذا وارجع لدالتك
    return HttpResponseForbidden("صفحة التسجيل لم تُفعّل بعد.")


register = register_view


@login_required
def ecr_dashcad(request):
    return render(request, "portal/ecr_dashcad.html")
