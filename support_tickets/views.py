from __future__ import annotations

import logging
from functools import wraps
from typing import Any, Optional

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt

from .forms import (
    TicketCreateForm,
    CommentForm,
    SupportReplyForm,
    PauseForm,
    ResumeForm,
    CloseForm,
    StatusChangeForm,
)
from .models import (
    SUPPORT_GROUP_NAME,
    SupportTicket,
    TicketMainCategory,
    TicketSubCategory,
    TicketStatusCatalog,
    TicketPauseReasonCatalog,
    TicketSolutionCatalog,
)
from .services.workflow import TicketWorkflow, is_support

logger = logging.getLogger(__name__)
User = get_user_model()


# =========================
# Helpers
# =========================

PRIVILEGED_GROUP_CODES = {"SYSADMIN", "NEMSCC", SUPPORT_GROUP_NAME}


def _user_in_privileged_groups(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    try:
        return user.groups.filter(name__in=list(PRIVILEGED_GROUP_CODES)).exists()
    except Exception:
        return False


def _get_user_region(user):
    """يرجع region إن كان موجوداً في User model."""
    return getattr(user, "region", None)


def _open_status() -> TicketStatusCatalog:
    st = TicketStatusCatalog.objects.filter(code="OPEN", is_active=True).first()
    if not st:
        # fallback: أول حالة مفعّلة
        st = TicketStatusCatalog.objects.filter(is_active=True).order_by("sort_order", "name").first()
    if not st:
        raise ValidationError("لا يوجد كتلوج حالات مفعّل. أنشئ حالة OPEN في TicketStatusCatalog.")
    return st


def api_auth_required(view_func):
    """Authenticate API endpoints via Session OR JWT Bearer token.

    - If the user is logged in (session-auth), allow.
    - Else, try SimpleJWT Bearer token (Authorization: Bearer <access>).
    - If not authenticated, return 401 JSON (no redirects).
    """
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        # Try JWT (SimpleJWT)
        try:
            from rest_framework_simplejwt.authentication import JWTAuthentication
            jwt_auth = JWTAuthentication()
            auth_result = jwt_auth.authenticate(request)
            if auth_result:
                user, _token = auth_result
                request.user = user
                return view_func(request, *args, **kwargs)
        except Exception:
            pass

        return JsonResponse({"detail": "غير مصرح. أعد تسجيل الدخول."}, status=401)

    return _wrapped


def _json_error(exc: Exception, status: int = 400) -> JsonResponse:
    if isinstance(exc, PermissionDenied):
        return JsonResponse({"detail": str(exc)}, status=403)
    if isinstance(exc, ValidationError):
        # ValidationError.message_dict or message
        if hasattr(exc, "message_dict"):
            return JsonResponse({"detail": exc.message_dict}, status=status)
        return JsonResponse({"detail": str(exc)}, status=status)
    logger.exception("support_tickets error: %s", exc)
    return JsonResponse({"detail": "حدث خطأ غير متوقع."}, status=500)


def _support_only_or_privileged_required(user):
    """
    حارس صلاحيات لصفحات الدعم الفني ولوحات SLA:
    - يسمح للسوبر يوزر
    - يسمح لمن داخل مجموعة الدعم الفني
    - يسمح لمن داخل المجموعات العليا (SYSADMIN/NEMSCC/SUPPORT_GROUP_NAME)
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    if is_support(user):
        return True
    if _user_in_privileged_groups(user):
        return True
    return False


def _base_support_queryset(request: HttpRequest):
    """
    Queryset موحّد مع قيود المنطقة:
    - العميل العادي: يرى تذاكره فقط
    - الدعم: يرى كل شيء، لكن إن لم يكن بصلاحيات عليا فيُفلتر حسب region
    """
    qs = SupportTicket.objects.select_related("status", "main_category", "sub_category", "assignee", "region")

    if not is_support(request.user):
        qs = qs.filter(requester=request.user)
        return qs

    # موظف الدعم
    if not _user_in_privileged_groups(request.user):
        ur = _get_user_region(request.user)
        if getattr(ur, "pk", None):
            qs = qs.filter(region_id=ur.pk)

    return qs


def _get_status_obj_by_code(code: str) -> Optional[TicketStatusCatalog]:
    code = (code or "").strip().upper()
    if not code:
        return None
    return TicketStatusCatalog.objects.filter(code=code, is_active=True).first()


# =========================
# Web Views
# =========================

@login_required
def ticket_list(request: HttpRequest) -> HttpResponse:
    """
    ✅ Updated:
    - يدعم فلترة status من QueryString (?status=OPEN/RESOLVED/CLOSED...)
    - يفتح قالب مناسب إن كان status مشهور (open/resolved/closed)
    - وإلا يفتح dashboard.html (القديم) كـ fallback
    """
    qs = _base_support_queryset(request)

    status_code = (request.GET.get("status") or "").strip().upper()
    status_obj = _get_status_obj_by_code(status_code)
    if status_obj:
        qs = qs.filter(status_id=status_obj.id)

    tickets = qs.order_by("-created_at")[:200]

    # قوالب جديدة حسب الحالة (إن وجدت)
    template_map = {
        "OPEN": "support_tickets/tickets_open.html",
        "IN_PROGRESS": "support_tickets/tickets_open.html",
        "RESOLVED": "support_tickets/tickets_resolved.html",
        "CLOSED": "support_tickets/tickets_closed.html",
    }
    template_name = template_map.get(status_code) or "support_tickets/dashboard.html"

    return render(request, template_name, {"tickets": tickets, "active_status": status_code})


@login_required
@transaction.atomic
def ticket_create(request: HttpRequest) -> HttpResponse:
    """
    ✅ Updated:
    - يعرض قالب إنشاء التذكرة الجديد ticket_create.html
    - ويحافظ على نفس منطق الإنشاء الموجود عندك
    """
    if request.method == "POST":
        form = TicketCreateForm(request.POST, request.FILES)
        if form.is_valid():
            t: SupportTicket = form.save(commit=False)
            t.requester = request.user

            # region: للعميل تلقائياً من حسابه (إن توفر)
            if not is_support(request.user):
                ur = _get_user_region(request.user)
                if getattr(ur, "pk", None):
                    t.region = ur

            t.status = _open_status()
            t.save()
            messages.success(request, f"تم إنشاء التذكرة: {t.code}")
            return redirect("support_tickets:detail", pk=t.pk)
    else:
        form = TicketCreateForm()

    return render(request, "support_tickets/ticket_create.html", {"form": form})


@login_required
def ticket_detail(request: HttpRequest, pk: int) -> HttpResponse:
    """
    (كما هو) — لكن تركناه على dashboard.html لأنك قد تستخدم نفس صفحة العرض القديمة.
    لو عندك قالب تفصيلي جديد مستقبلاً نغيّره له.
    """
    ticket = get_object_or_404(
        SupportTicket.objects.select_related("status", "main_category", "sub_category", "assignee", "region"),
        pk=pk,
    )
    if not is_support(request.user) and ticket.requester_id != request.user.id:
        raise PermissionDenied("لا تملك صلاحية على هذه التذكرة.")

    comment_form = CommentForm()
    reply_form = SupportReplyForm()
    pause_form = PauseForm()
    resume_form = ResumeForm()
    close_form = CloseForm()
    status_form = StatusChangeForm()

    return render(
        request,
        "support_tickets/dashboard.html",
        {
            "ticket": ticket,
            "comment_form": comment_form,
            "reply_form": reply_form,
            "pause_form": pause_form,
            "resume_form": resume_form,
            "close_form": close_form,
            "status_form": status_form,
        },
    )


# =========================================================
# ✅ NEW: Pages to open templates/support_tickets/*
# =========================================================

@login_required
def support_sla_dashboard(request: HttpRequest) -> HttpResponse:
    """
    ✅ هذه هي الـ View التي تحل مشكلة:
    Reverse for 'support_sla_dashboard' not found
    وتفتح قالب لوحة SLA من templates/support_tickets/dashboard_sla.html
    """
    if not _support_only_or_privileged_required(request.user):
        raise PermissionDenied("هذه الصفحة خاصة بالدعم الفني والصلاحيات العليا فقط.")

    # أنت قلت: "صفحة عالمية داشبورد الدعم الفني"
    # حالياً نفتح القالب مباشرة. (لاحقاً نربط KPIs/Charts لو رغبت)
    return render(request, "support_tickets/dashboard_sla.html", {})


@login_required
def support_ticket_create_page(request: HttpRequest) -> HttpResponse:
    """
    فتح صفحة إنشاء التذكرة (القالب الجديد).
    إن رغبت تقييدها للدعم فقط، فعل شرط الصلاحيات.
    """
    # إن تبغى تكون متاحة للجميع (عميل/دعم) اتركها بدون شرط
    return render(request, "support_tickets/ticket_create.html", {"form": TicketCreateForm()})


@login_required
def support_tickets_assigned_to_me(request: HttpRequest) -> HttpResponse:
    """
    فتح قالب التذاكر المسندة لي — خاص بالدعم الفني
    """
    if not _support_only_or_privileged_required(request.user):
        raise PermissionDenied("هذه الصفحة خاصة بالدعم الفني والصلاحيات العليا فقط.")

    qs = _base_support_queryset(request).filter(assignee=request.user).order_by("-created_at")[:200]
    return render(request, "support_tickets/tickets_assigned_to_me.html", {"tickets": qs})


@login_required
def support_tickets_open_page(request: HttpRequest) -> HttpResponse:
    """
    فتح قالب التذاكر المفتوحة — خاص بالدعم الفني
    """
    if not _support_only_or_privileged_required(request.user):
        raise PermissionDenied("هذه الصفحة خاصة بالدعم الفني والصلاحيات العليا فقط.")

    # OPEN + IN_PROGRESS
    st_open = _get_status_obj_by_code("OPEN")
    st_ip = _get_status_obj_by_code("IN_PROGRESS")
    ids = [s.pk for s in [st_open, st_ip] if s]

    qs = _base_support_queryset(request)
    if ids:
        qs = qs.filter(status_id__in=ids)

    qs = qs.order_by("-created_at")[:200]
    return render(request, "support_tickets/tickets_open.html", {"tickets": qs})


@login_required
def support_tickets_resolved_page(request: HttpRequest) -> HttpResponse:
    """
    فتح قالب التذاكر المحلولة — خاص بالدعم الفني
    """
    if not _support_only_or_privileged_required(request.user):
        raise PermissionDenied("هذه الصفحة خاصة بالدعم الفني والصلاحيات العليا فقط.")

    st = _get_status_obj_by_code("RESOLVED")
    qs = _base_support_queryset(request)
    if st:
        qs = qs.filter(status_id=st.id)
    qs = qs.order_by("-created_at")[:200]
    return render(request, "support_tickets/tickets_resolved.html", {"tickets": qs})


@login_required
def support_tickets_closed_page(request: HttpRequest) -> HttpResponse:
    """
    فتح قالب التذاكر المغلقة — خاص بالدعم الفني
    """
    if not _support_only_or_privileged_required(request.user):
        raise PermissionDenied("هذه الصفحة خاصة بالدعم الفني والصلاحيات العليا فقط.")

    st = _get_status_obj_by_code("CLOSED")
    qs = _base_support_queryset(request)
    if st:
        qs = qs.filter(status_id=st.id)
    qs = qs.order_by("-created_at")[:200]
    return render(request, "support_tickets/tickets_closed.html", {"tickets": qs})


# =========================
# Catalog APIs
# =========================

@require_GET
@csrf_exempt
@api_auth_required
def api_main_categories(request: HttpRequest) -> JsonResponse:
    qs = TicketMainCategory.objects.filter(is_active=True).order_by("kind", "name")
    data = [{"id": c.id, "kind": c.kind, "name": c.name, "sla_minutes": c.sla_minutes} for c in qs]
    return JsonResponse(data, safe=False)


@require_GET
@csrf_exempt
@api_auth_required
def api_sub_categories(request: HttpRequest) -> JsonResponse:
    main_id = request.GET.get("main_id")
    qs = TicketSubCategory.objects.filter(is_active=True)
    if main_id:
        qs = qs.filter(main_category_id=main_id)
    qs = qs.select_related("main_category").order_by("name")
    data = [
        {
            "id": s.id,
            "main_category_id": s.main_category_id,
            "name": s.name,
            "sla_minutes": s.effective_sla_minutes(),
        }
        for s in qs
    ]
    return JsonResponse(data, safe=False)


@require_GET
@csrf_exempt
@api_auth_required
def api_status_catalog(request: HttpRequest) -> JsonResponse:
    qs = TicketStatusCatalog.objects.filter(is_active=True).order_by("sort_order", "name")
    data = [{"id": s.id, "code": s.code, "name": s.name, "requires_pause_reason": s.requires_pause_reason, "is_closed": s.is_closed} for s in qs]
    return JsonResponse(data, safe=False)


@require_GET
@csrf_exempt
@api_auth_required
def api_pause_reasons(request: HttpRequest) -> JsonResponse:
    qs = TicketPauseReasonCatalog.objects.filter(is_active=True).order_by("sort_order", "name")
    data = [{"id": r.id, "name": r.name} for r in qs]
    return JsonResponse(data, safe=False)


@require_GET
@csrf_exempt
@api_auth_required
def api_solution_catalog(request: HttpRequest) -> JsonResponse:
    qs = TicketSolutionCatalog.objects.filter(is_active=True).order_by("sort_order", "name")
    data = [{"id": s.id, "name": s.name} for s in qs]
    return JsonResponse(data, safe=False)


@require_GET
@csrf_exempt
@api_auth_required
def api_assignees(request: HttpRequest) -> JsonResponse:
    """يرجع موظفي الدعم الفني حسب منطقة المستخدم (أو كل المناطق للصلاحيات العليا)."""
    if not is_support(request.user):
        return JsonResponse([], safe=False)

    qs = User.objects.filter(is_active=True, groups__name=SUPPORT_GROUP_NAME).distinct()

    if not _user_in_privileged_groups(request.user):
        ur = _get_user_region(request.user)
        if getattr(ur, "pk", None):
            # إن كان User model يحتوي region_id
            try:
                User._meta.get_field("region")
                qs = qs.filter(region_id=ur.pk)
            except Exception:
                pass

    data = [{"id": u.id, "name": (u.get_full_name() or u.username)} for u in qs.order_by("username")]
    return JsonResponse(data, safe=False)


# =========================
# Ticket APIs
# =========================

@require_GET
@csrf_exempt
@api_auth_required
def api_tickets_list(request: HttpRequest) -> JsonResponse:
    qs = SupportTicket.objects.select_related("status", "main_category", "sub_category", "assignee", "region")
    if not is_support(request.user):
        qs = qs.filter(requester=request.user)
    else:
        if not _user_in_privileged_groups(request.user):
            ur = _get_user_region(request.user)
            if getattr(ur, "pk", None):
                qs = qs.filter(region_id=ur.pk)

    tickets = qs.order_by("-created_at")[:200]
    data = []
    now = timezone.now()
    for t in tickets:
        data.append(
            {
                "id": t.id,
                "code": t.code,
                "kind": t.kind,
                "source": t.source,
                "requester_name": t.requester_name,
                "requester_national_id": t.requester_national_id,
                "requester_phone": t.requester_phone,
                "requester_email": t.requester_email,
                "region": getattr(t.region, "name", None),
                "assignee": (t.assignee.get_full_name() if t.assignee_id else None),
                "status": {"id": t.status_id, "code": t.status.code if t.status_id else None, "name": t.status.name if t.status_id else None},
                "pause_reason": str(t.pause_reason) if t.pause_reason_id else None,
                "main_category": t.main_category.name,
                "sub_category": t.sub_category.name,
                "sla_minutes": t.sla_minutes,
                "deadline_at": t.effective_deadline_at(at=now).isoformat() if t.effective_deadline_at(at=now) else None,
                "is_overdue": t.is_overdue(at=now),
                "overdue_seconds": t.overdue_seconds(at=now),
                "created_at": t.created_at.isoformat(),
                "first_response_at": t.first_response_at.isoformat() if t.first_response_at else None,
                "assigned_at": t.assigned_at.isoformat() if t.assigned_at else None,
                "last_status_changed_at": t.last_status_changed_at.isoformat() if t.last_status_changed_at else None,
                "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            }
        )
    return JsonResponse(data, safe=False)


@require_POST
@csrf_exempt
@api_auth_required
def api_tickets_create(request: HttpRequest) -> JsonResponse:
    try:
        form = TicketCreateForm(request.POST, request.FILES)
        if not form.is_valid():
            return JsonResponse({"detail": form.errors}, status=400)

        t: SupportTicket = form.save(commit=False)
        t.requester = request.user

        if not is_support(request.user):
            ur = _get_user_region(request.user)
            if getattr(ur, "pk", None):
                t.region = ur

        t.status = _open_status()
        t.save()
        return JsonResponse({"id": t.id, "code": t.code}, status=201)
    except Exception as e:
        return _json_error(e)


@require_GET
@csrf_exempt
@api_auth_required
def api_ticket_detail(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(
            SupportTicket.objects.select_related("status", "main_category", "sub_category", "assignee", "region"),
            pk=pk,
        )
        if not is_support(request.user) and t.requester_id != request.user.id:
            raise PermissionDenied("لا تملك صلاحية على هذه التذكرة.")

        comments = [
            {
                "id": c.id,
                "author": c.author.get_full_name() or c.author.username,
                "body": c.body,
                "is_support_reply": c.is_support_reply,
                "is_internal": c.is_internal,
                "created_at": c.created_at.isoformat(),
            }
            for c in t.comments.select_related("author").all()
            if (not c.is_internal) or is_support(request.user)
        ]

        data = {
            "id": t.id,
            "code": t.code,
            "kind": t.kind,
            "source": t.source,
            "requester_name": t.requester_name,
            "requester_national_id": t.requester_national_id,
            "requester_phone": t.requester_phone,
            "requester_email": t.requester_email,
            "region": getattr(t.region, "name", None),
            "assignee": (t.assignee.get_full_name() if t.assignee_id else None),
            "status": {"id": t.status_id, "code": t.status.code if t.status_id else None, "name": t.status.name if t.status_id else None},
            "pause_reason": str(t.pause_reason) if t.pause_reason_id else None,
            "main_category": {"id": t.main_category_id, "name": t.main_category.name},
            "sub_category": {"id": t.sub_category_id, "name": t.sub_category.name},
            "description": t.description,
            "image": t.image.url if t.image else None,
            "sla_minutes": t.sla_minutes,
            "deadline_at": t.effective_deadline_at().isoformat() if t.effective_deadline_at() else None,
            "is_overdue": t.is_overdue(),
            "overdue_seconds": t.overdue_seconds(),
            "created_at": t.created_at.isoformat(),
            "first_response_at": t.first_response_at.isoformat() if t.first_response_at else None,
            "assigned_at": t.assigned_at.isoformat() if t.assigned_at else None,
            "last_status_changed_at": t.last_status_changed_at.isoformat() if t.last_status_changed_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "solution": {"catalog": str(t.solution_catalog) if t.solution_catalog_id else None, "notes": t.solution_notes or ""},
            "comments": comments,
        }
        return JsonResponse(data)
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_comment(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        body = (request.POST.get("body") or "").strip()
        res = TicketWorkflow.add_comment(user=request.user, ticket=t, body=body, is_internal=False)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_reply(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        body = (request.POST.get("body") or "").strip()
        is_internal = str(request.POST.get("is_internal") or "").lower() in {"1", "true", "yes"}
        res = TicketWorkflow.add_comment(user=request.user, ticket=t, body=body, is_internal=is_internal)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_pause(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        reason_id = int(request.POST.get("reason_id") or 0)
        res = TicketWorkflow.pause_ticket(user=request.user, ticket=t, reason_id=reason_id)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_resume(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        res = TicketWorkflow.resume_ticket(user=request.user, ticket=t)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_change_status(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        status_id = int(request.POST.get("status_id") or 0)
        pause_reason_id = request.POST.get("pause_reason_id")
        pr = int(pause_reason_id) if pause_reason_id else None
        res = TicketWorkflow.change_status(user=request.user, ticket=t, status_id=status_id, pause_reason_id=pr)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_close(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        solution_catalog_id = int(request.POST.get("solution_catalog_id") or 0)
        solution_notes = (request.POST.get("solution_notes") or "").strip()
        res = TicketWorkflow.close_ticket(
            user=request.user,
            ticket=t,
            solution_catalog_id=solution_catalog_id,
            solution_notes=solution_notes,
        )
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)


@require_POST
@csrf_exempt
@api_auth_required
def api_ticket_assign(request: HttpRequest, pk: int) -> JsonResponse:
    try:
        t = get_object_or_404(SupportTicket, pk=pk)
        assignee_id = int(request.POST.get("assignee_id") or 0)
        assignee = get_object_or_404(User, pk=assignee_id)
        res = TicketWorkflow.assign_ticket(user=request.user, ticket=t, assignee=assignee)
        return JsonResponse({"ok": res.ok, "message": res.message})
    except Exception as e:
        return _json_error(e)