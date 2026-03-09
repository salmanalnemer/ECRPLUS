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


def _normalize_health_courses(value):
    if value is None:
        return []

    if isinstance(value, list):
        raw_items = value
    elif isinstance(value, str):
        raw_items = [v.strip() for v in value.split(",")]
    else:
        return []

    allowed = {"life_ambassador", "first_aid_8", "other"}
    result = []

    for item in raw_items:
        v = str(item).strip()
        if not v:
            continue
        if v in allowed and v not in result:
            result.append(v)

    return result


def _assign_default_usergroup(user) -> None:
    """
    تعيين المستخدم تلقائياً إلى مجموعة ECRMOBIL
    """
    try:
        from usergroups.models import UserGroup

        ug = UserGroup.objects.get(code="ECRMOBIL", is_active=True)
        user.user_group = ug
        user.save(update_fields=["user_group"])
    except Exception:
        logger.exception("Failed to assign default user_group (ECRMOBIL)")


def _model_has_field(model_class, field_name: str) -> bool:
    try:
        model_class._meta.get_field(field_name)
        return True
    except Exception:
        return False


def _ensure_responder_records(user, region_id=None, organization_id=None) -> None:
    """
    إنشاء سجلات المستجيب وموقعه الأولي بدون إسقاط التسجيل بالكامل
    إذا اختلفت بنية الموديل أو كان هناك قيد غير متوقع.
    """
    try:
        from responders.models import Responder, ResponderLocation
    except Exception:
        logger.exception("Unable to import responders models")
        return

    # إنشاء Responder إن أمكن
    try:
        responder_defaults = {}

        if _model_has_field(Responder, "region") and region_id:
            responder_defaults["region_id"] = region_id

        if _model_has_field(Responder, "organization") and organization_id:
            responder_defaults["organization_id"] = organization_id

        if _model_has_field(Responder, "is_active"):
            responder_defaults["is_active"] = True

        if _model_has_field(Responder, "user"):
            Responder.objects.get_or_create(
                user=user,
                defaults=responder_defaults,
            )
        else:
            logger.warning("Responder model has no 'user' field; skipping responder creation")
    except Exception:
        logger.exception("Failed to create/get Responder for user_id=%s", getattr(user, "id", None))

    # إنشاء موقع أولي للمستجيب إن أمكن
    try:
        location_defaults = {}

        if _model_has_field(ResponderLocation, "latitude"):
            location_defaults["latitude"] = 0.0

        if _model_has_field(ResponderLocation, "longitude"):
            location_defaults["longitude"] = 0.0

        if _model_has_field(ResponderLocation, "last_seen"):
            location_defaults["last_seen"] = timezone.now()

        if _model_has_field(ResponderLocation, "responder"):
            ResponderLocation.objects.get_or_create(
                responder=user,
                defaults=location_defaults,
            )
        else:
            logger.warning(
                "ResponderLocation model has no 'responder' field; skipping location creation"
            )
    except Exception:
        logger.exception(
            "Failed to create/get ResponderLocation for user_id=%s",
            getattr(user, "id", None),
        )


@csrf_exempt
@require_http_methods(["POST"])
def register(request):
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

    citizen_health_courses = _normalize_health_courses(
        data.get("citizen_health_courses")
    )
    citizen_other_health_courses = (
        data.get("citizen_other_health_courses") or ""
    ).strip()

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

    organization_obj = None
    is_citizen = False

    if organization_id:
        try:
            from organizations.models import Organization

            organization_obj = Organization.objects.filter(
                pk=organization_id,
                is_active=True,
            ).first()

            if organization_obj:
                is_citizen = (organization_obj.name or "").strip().lower() in {
                    "مواطن",
                    "citizen",
                }
        except Exception:
            logger.exception("Failed to load organization during register")
            organization_obj = None

    if organization_id and not organization_obj:
        errors["organization_id"] = ["invalid"]

    if is_citizen:
        if not citizen_health_courses:
            errors["citizen_health_courses"] = ["required"]

        if "other" in citizen_health_courses and not citizen_other_health_courses:
            errors["citizen_other_health_courses"] = ["required"]

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    if User.objects.filter(email=email).exists():
        return JsonResponse({"detail": "البريد الإلكتروني مستخدم مسبقًا"}, status=409)

    if hasattr(User, "national_id") and User.objects.filter(national_id=national_id).exists():
        return JsonResponse({"detail": "رقم الهوية مستخدم مسبقًا"}, status=409)

    try:
        with transaction.atomic():
            user_kwargs = {
                "email": email,
                "national_id": national_id,
                "full_name": full_name,
                "phone": phone,
                "password": password,
                "organization_id": organization_id,
                "region_id": region_id,
                "is_active": False,
            }

            # نضيف حقول المواطن فقط إذا كانت موجودة في الموديل
            if hasattr(User, "citizen_health_courses"):
                user_kwargs["citizen_health_courses"] = (
                    citizen_health_courses if is_citizen else []
                )

            if hasattr(User, "citizen_other_health_courses"):
                user_kwargs["citizen_other_health_courses"] = (
                    citizen_other_health_courses if is_citizen else ""
                )

            # إنشاء المستخدم
            user = User.objects.create_user(**user_kwargs)

            # إضافته لمجموعة ECRMOBIL
            _assign_default_usergroup(user)

            # إنشاء سجلات المستجيب بشكل آمن بدون كسر التسجيل
            _ensure_responder_records(
                user=user,
                region_id=region_id,
                organization_id=organization_id,
            )

            # سجل التحقق
            EmailVerification.objects.get_or_create(user=user)

            # إصدار OTP
            otp_obj = EmailOTP.issue_otp(
                user=user,
                purpose="verify_email",
                ttl_minutes=10,
                length=6,
            )

            otp = otp_obj.code

            try:
                _send_otp_email(email, otp)
                detail = "تم إنشاء الحساب. تم إرسال رمز التفعيل إلى البريد الإلكتروني."
            except Exception:
                logger.exception("Failed to send verification OTP email")
                detail = "تم إنشاء الحساب لكن تعذر إرسال رمز التفعيل حالياً."

            return JsonResponse({"detail": detail}, status=201)

    except IntegrityError as e:
        logger.exception("Register failed (IntegrityError)")
        if getattr(settings, "DEBUG", False):
            return JsonResponse(
                {
                    "detail": "IntegrityError",
                    "debug_error": str(e),
                },
                status=500,
            )

        return JsonResponse(
            {"detail": "بيانات غير صحيحة (تأكد من المنطقة والجهة وعدم تكرار البيانات)"},
            status=400,
        )

    except Exception as e:
        logger.exception("Register failed (Exception)")
        if getattr(settings, "DEBUG", False):
            return JsonResponse(
                {
                    "detail": "Register failed",
                    "debug_error": str(e),
                    "error_type": e.__class__.__name__,
                },
                status=500,
            )

        return JsonResponse({"detail": "حدث خطأ في إنشاء الحساب"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def verify_email(request):
    data = _json(request)
    if data is None:
        return JsonResponse({"detail": "Invalid JSON"}, status=400)

    national_id = (data.get("national_id") or "").strip()
    email = (data.get("email") or "").strip().lower()
    otp = (data.get("otp") or data.get("code") or "").strip()

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

    otp_obj = EmailOTP.issue_otp(
        user=user,
        purpose="verify_email",
        ttl_minutes=10,
        length=6,
    )

    otp = otp_obj.code

    try:
        _send_otp_email(user.email, otp)
        return JsonResponse({"detail": "تم إرسال رمز تفعيل جديد إلى البريد الإلكتروني"}, status=200)
    except Exception:
        logger.exception("Failed to resend verification OTP email")
        return JsonResponse({"detail": "تعذر إرسال الرمز حالياً، حاول لاحقاً"}, status=503)