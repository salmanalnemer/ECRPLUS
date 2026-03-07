import json
import logging
import random

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models_auth import EmailOTP, EmailVerification

logger = logging.getLogger(__name__)
User = get_user_model()


def _generate_otp() -> str:
    return f"{random.randint(100000, 999999)}"


def _send_otp_email(email: str, otp: str) -> None:
    subject = "رمز تفعيل الحساب"
    message = f"رمز التفعيل الخاص بك هو: {otp}"
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None)
    send_mail(subject, message, from_email, [email], fail_silently=False)


def _json(request):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return None


def _coerce_int(v):
    try:
        return int(v)
    except Exception:
        return v


def _assign_default_usergroup(user) -> None:
    """
    ✅ المطلوب:
    - أي مستخدم يسجل من Flutter يتم تعيينه تلقائياً إلى مجموعة ECRMOBIL (كتلوج usergroups)

    ملاحظة:
    - هذا يعبّي الحقل المهم عندك (User.user_group).
    - لا نضيف المستخدم إلى auth.Group إطلاقاً لتجنب التكرار/اللخبطة.
    """
    try:
        from usergroups.models import UserGroup

        ug = UserGroup.objects.get(code="ECRMOBIL", is_active=True)
        user.user_group = ug
        user.save(update_fields=["user_group"])
    except Exception:
        logger.exception("Failed to assign default user_group (ECRMOBIL)")


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
    """
    Body:
      - full_name
      - national_id
      - phone
      - email
      - password
      - region_id
      - organization_id

    سلوك التسجيل:
      - إنشاء المستخدم بحالة غير مفعّل is_active=False
      - تعيينه تلقائياً إلى مجموعة ECRMOBIL داخل كتلوج usergroups
      - إصدار OTP وإرساله للبريد
    """
    data = _json(request)
    if data is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    full_name = (data.get("full_name") or "").strip()
    national_id = (data.get("national_id") or "").strip()
    phone = (data.get("phone") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    region_id = _coerce_int(data.get("region_id"))
    organization_id = _coerce_int(data.get("organization_id"))

    errors = {}
    if not full_name:
        errors["full_name"] = ["required"]
    if not national_id:
        errors["national_id"] = ["required"]
    if not phone:
        errors["phone"] = ["required"]
    if not email:
        errors["email"] = ["required"]
    if not password:
        errors["password"] = ["required"]
    if not region_id:
        errors["region_id"] = ["required"]
    if not organization_id:
        errors["organization_id"] = ["required"]

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"detail": "البريد الإلكتروني مستخدم مسبقًا"}, status=409)
    if hasattr(User, "national_id") and User.objects.filter(national_id=national_id).exists():
        return JsonResponse({"detail": "رقم الهوية مستخدم مسبقًا"}, status=409)

    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                national_id=national_id,
                full_name=full_name,
                phone=phone,
                password=password,
                organization_id=organization_id,
                region_id=region_id,
                is_active=False,
            )

            # ✅ تعيين تلقائي لمجموعة ECRMOBIL (الحقل المهم)
            _assign_default_usergroup(user)

            EmailVerification.objects.get_or_create(user=user)

            otp_obj = EmailOTP.issue_otp(user=user, purpose="verify_email", ttl_minutes=10, length=6)
            otp = otp_obj.code

            try:
                _send_otp_email(email, otp)
                detail = "تم إنشاء الحساب. تم إرسال رمز التفعيل إلى البريد الإلكتروني."
            except Exception:
                logger.exception("Failed to send verification OTP email")
                detail = "تم إنشاء الحساب لكن تعذر إرسال رمز التفعيل حالياً. استخدم إعادة الإرسال لاحقاً."

            return JsonResponse({"detail": detail}, status=201)

    except IntegrityError as e:
        logger.exception("Register failed (IntegrityError)")
        if getattr(settings, "DEBUG", False):
            return JsonResponse({"detail": f"IntegrityError: {str(e)}"}, status=500)
        return JsonResponse({"detail": "بيانات غير صحيحة (تأكد من المنطقة/الجهة وعدم تكرار رقم الهوية/الإيميل)"}, status=400)

    except Exception as e:
        logger.exception("Register failed (Exception)")
        if getattr(settings, "DEBUG", False):
            return JsonResponse({"detail": str(e)}, status=500)
        return JsonResponse({"detail": "حدث خطأ في إنشاء الحساب"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def verify_email(request):
    """
    Body:
    - national_id OR email
    - otp
    """
    data = _json(request)
    if data is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    national_id = (data.get("national_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or "").strip()

    if not otp or (not national_id and not email):
        return JsonResponse({"detail": "national_id/email and otp are required"}, status=400)

    try:
        user = User.objects.get(national_id=national_id) if national_id else User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({"detail": "المستخدم غير موجود"}, status=404)

    ev, _ = EmailVerification.objects.get_or_create(user=user)

    if ev.verified_at is not None:
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        return JsonResponse({"detail": "البريد الإلكتروني مفعل بالفعل"}, status=200)

    ok = EmailOTP.verify_otp(user=user, code=otp, purpose="verify_email")
    if not ok:
        return JsonResponse({"detail": "رمز التفعيل غير صحيح أو منتهي"}, status=400)

    with transaction.atomic():
        if not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])

        EmailVerification.objects.update_or_create(
            user=user,
            defaults={"verified_at": timezone.now()},
        )

    return JsonResponse({"detail": "تم تفعيل الحساب بنجاح"}, status=200)


@csrf_exempt
@require_http_methods(["POST"])
def resend_verify_email(request):
    """
    Body:
    - national_id OR email
    """
    data = _json(request)
    if data is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    national_id = (data.get("national_id") or "").strip()
    email = (data.get("email") or "").strip().lower()

    if not national_id and not email:
        return JsonResponse({"detail": "national_id or email is required"}, status=400)

    try:
        user = User.objects.get(national_id=national_id) if national_id else User.objects.get(email=email)
    except User.DoesNotExist:
        return JsonResponse({"detail": "المستخدم غير موجود"}, status=404)

    if user.is_active:
        return JsonResponse({"detail": "الحساب مفعل بالفعل"}, status=200)

    otp_obj = EmailOTP.issue_otp(user=user, purpose="verify_email", ttl_minutes=10, length=6)
    otp = otp_obj.code

    try:
        _send_otp_email(user.email, otp)
        return JsonResponse({"detail": "تم إرسال رمز تفعيل جديد إلى البريد الإلكتروني"}, status=200)
    except Exception:
        logger.exception("Failed to resend verification OTP email")
        return JsonResponse({"detail": "تعذر إرسال الرمز حالياً، حاول لاحقاً"}, status=503)
