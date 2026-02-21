from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction, models
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import TicketCreateForm, CommentForm, SupportReplyForm, PauseForm, ResumeForm, CloseForm
from .models import SupportTicket, TicketKind, TicketMainCategory, TicketSubCategory
from .services.workflow import TicketWorkflow, is_support
from datetime import timedelta
from django.utils import timezone
from .models import TicketStatus
from django.db.models.functions import TruncDay
from django.db.models import Count, Q
logger = logging.getLogger(__name__)


def _ticket_queryset_for_user(user):
    qs = SupportTicket.objects.select_related(
        "requester",
        "assignee",
        "main_category",
        "sub_category",
    ).prefetch_related("comments", "pauses")

    # الأدمن أو المجموعات العامة → يشوف كل شيء
    if user.is_superuser or user.groups.filter(name__in=["SYSADMIN", "NEMSCC"]).exists():
        return qs

    # الدعم الفني يشوف كل شيء
    if is_support(user):
        return qs

    # المستخدم العادي
    return qs.filter(requester=user)


@login_required
def ticket_list(request: HttpRequest) -> HttpResponse:
    tickets = _ticket_queryset_for_user(request.user)
    return render(
        request,
        "support_tickets/ticket_list.html",
        {"tickets": tickets, "is_support": is_support(request.user)},
    )


@login_required
@transaction.atomic
def ticket_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = TicketCreateForm(request.POST, request.FILES)
        if form.is_valid():
            ticket: SupportTicket = form.save(commit=False)
            ticket.requester = request.user

            # ✅ لا full_clean هنا
            # SupportTicket.save() داخل models.py يقوم بـ:
            # - bootstrap kind/sla
            # - ensure_code()
            # - full_clean()
            ticket.save()

            messages.success(request, f"تم إنشاء التذكرة: {ticket.code}")
            return redirect("support_tickets:detail", pk=ticket.pk)
    else:
        form = TicketCreateForm()

    return render(
        request,
        "support_tickets/ticket_create.html",
        {"form": form, "is_support": is_support(request.user)},
    )


@login_required
@transaction.atomic
def ticket_detail(request: HttpRequest, pk: int) -> HttpResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)

    _is_support = is_support(request.user)
    comment_form = CommentForm()
    support_reply_form = SupportReplyForm()
    pause_form = PauseForm()
    resume_form = ResumeForm()
    close_form = CloseForm()

    if request.method == "POST":
        action = (request.POST.get("action", "") or "").strip()

        try:
            if action == "comment":
                form = CommentForm(request.POST)
                if form.is_valid():
                    TicketWorkflow.add_requester_comment(
                        user=request.user,
                        ticket=ticket,
                        body=form.cleaned_data["body"],
                    )
                    messages.success(request, "تم إضافة التعليق.")
                    return redirect("support_tickets:detail", pk=ticket.pk)

            if action == "support_reply":
                if not _is_support:
                    return HttpResponseForbidden("غير مصرح")
                form = SupportReplyForm(request.POST)
                if form.is_valid():
                    TicketWorkflow.add_support_reply(
                        user=request.user,
                        ticket=ticket,
                        body=form.cleaned_data["body"],
                    )
                    messages.success(request, "تم تسجيل رد الدعم وبدء الاستجابة (إن لم تكن مسجلة).")
                    return redirect("support_tickets:detail", pk=ticket.pk)

            if action == "pause":
                if not _is_support:
                    return HttpResponseForbidden("غير مصرح")
                form = PauseForm(request.POST)
                if form.is_valid():
                    TicketWorkflow.pause_ticket(
                        user=request.user,
                        ticket=ticket,
                        reason=form.cleaned_data["reason"],
                    )
                    messages.info(request, "تم تعليق التذكرة مؤقتًا وإيقاف احتساب الوقت.")
                    return redirect("support_tickets:detail", pk=ticket.pk)

            if action == "resume":
                if not _is_support:
                    return HttpResponseForbidden("غير مصرح")
                form = ResumeForm(request.POST)
                if form.is_valid():
                    TicketWorkflow.resume_ticket(user=request.user, ticket=ticket)
                    messages.success(request, "تم استئناف التذكرة واستكمال احتساب الوقت.")
                    return redirect("support_tickets:detail", pk=ticket.pk)

            if action == "close":
                if not _is_support:
                    return HttpResponseForbidden("غير مصرح")
                form = CloseForm(request.POST)
                if form.is_valid():
                    TicketWorkflow.close_ticket(user=request.user, ticket=ticket)
                    messages.success(request, "تم إغلاق التذكرة.")
                    return redirect("support_tickets:detail", pk=ticket.pk)

        except PermissionDenied as e:
            messages.error(request, str(e))
        except ValidationError as e:
            msg = getattr(e, "message", None) or str(e)
            messages.error(request, msg)
        except Exception:
            logger.exception("ticket_detail action failed: action=%s ticket=%s", action, ticket.pk)
            messages.error(request, "حدث خطأ غير متوقع أثناء تنفيذ العملية.")

    context = {
        "ticket": ticket,
        "is_support": _is_support,
        "comment_form": comment_form,
        "support_reply_form": support_reply_form,
        "pause_form": pause_form,
        "resume_form": resume_form,
        "close_form": close_form,
        "response_time_sec": ticket.response_time_seconds(),
        "resolution_time_sec": ticket.resolution_time_seconds(),
    }
    return render(request, "support_tickets/ticket_detail.html", context)


# ==========================
# API (for dynamic dropdowns)
# ==========================

@login_required
@require_GET
def api_main_categories(request: HttpRequest) -> JsonResponse:
    kind = (request.GET.get("kind") or "").strip()
    if kind not in {TicketKind.REQ, TicketKind.INC}:
        return JsonResponse({"ok": False, "items": [], "error": "Invalid kind"}, status=400)

    items = list(
        TicketMainCategory.objects.filter(kind=kind, is_active=True)
        .order_by("name")
        .values("id", "name")
    )
    return JsonResponse({"ok": True, "items": items})


@login_required
@require_GET
def api_sub_categories(request: HttpRequest) -> JsonResponse:
    main_id = (request.GET.get("main_id") or "").strip()
    try:
        main_id_int = int(main_id)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "items": [], "error": "Invalid main_id"}, status=400)

    items = list(
        TicketSubCategory.objects.filter(main_category_id=main_id_int, is_active=True)
        .order_by("name")
        .values("id", "name")
    )
    return JsonResponse({"ok": True, "items": items})


# ==========================
# Dashboard (KPIs)
# ==========================

@login_required
@require_GET
def dashboard(request: HttpRequest) -> HttpResponse:
    # هذه لوحة خاصة بالدعم الفني
    if not is_support(request.user):
        return HttpResponseForbidden("غير مصرح")

    # نعيد استخدام نفس منطق الـ API لضمان تطابق الأرقام (SLA/pauses/averages/assignees)
    data = _build_dashboard_summary(request)

    days = int(data.get("days") or 30)
    since = data.get("since")

    totals = dict(data.get("totals") or {})
    averages = data.get("averages") or {"avg_response_sec": 0, "avg_resolution_sec": 0, "avg_overdue_sec": 0}
    assignees = data.get("assignees") or []
    top_main_categories = data.get("top_main_categories") or []
    top_sub_categories = data.get("top_sub_categories") or []

    total = int(totals.get("total") or 0)
    overdue = int(totals.get("overdue") or 0)
    on_time = max(total - overdue, 0)
    sla_pct = round((on_time / total) * 100, 2) if total else 0

    totals["on_time"] = on_time

    # شارت يومي: labels + counts (خفيف على DB)
    qs = SupportTicket.objects.filter(created_at__gte=since)
    daily = (
        qs.annotate(d=TruncDay("created_at"))
          .values("d")
          .annotate(cnt=Count("id"))
          .order_by("d")
    )
    daily_labels = [row["d"].strftime("%Y-%m-%d") for row in daily if row.get("d")]
    daily_counts = [int(row.get("cnt") or 0) for row in daily]

    context = {
        "days": days,
        "since": since,
        "totals": totals,
        "averages": averages,
        "assignees": assignees,
        "top_main_categories": top_main_categories,
        "top_sub_categories": top_sub_categories,
        "charts": {
            "sla_pct": float(sla_pct or 0),
            "daily_labels": daily_labels or [],
            "daily_counts": daily_counts or [],
        },
    }
    return render(request, "support_tickets/dashboard.html", context)
@login_required
@require_GET
def api_dashboard_summary(request: HttpRequest) -> JsonResponse:
    if not is_support(request.user):
        return JsonResponse({"ok": False, "error": "Forbidden"}, status=403)

    data = _build_dashboard_summary(request)
    return JsonResponse({"ok": True, "data": data})


def _parse_days_param(request: HttpRequest, default_days: int = 30) -> int:
    raw = (request.GET.get("days") or "").strip()
    if not raw:
        return default_days
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return default_days
    return max(1, min(365, days))


def _build_dashboard_summary(request: HttpRequest) -> dict:
    User = get_user_model()

    days = _parse_days_param(request, default_days=30)
    since = timezone.now() - timedelta(days=days)

    qs = (
        SupportTicket.objects.select_related("assignee", "main_category", "sub_category")
        .prefetch_related("pauses")
        .filter(created_at__gte=since)
        .order_by("-created_at")
    )

    tickets = list(qs)

    total = len(tickets)
    by_status = {s: 0 for s, _ in TicketStatus.choices}
    by_kind = {k: 0 for k, _ in TicketKind.choices}

    overdue_count = 0
    response_times = []
    resolution_times = []
    overdue_seconds_list = []

    assignee_map: dict[int, dict] = {}

    for t in tickets:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_kind[getattr(t, "kind", "")] = by_kind.get(getattr(t, "kind", ""), 0) + 1

        rt = t.response_time_seconds()
        if rt:
            response_times.append(rt)

        res_t = t.resolution_time_seconds()
        if res_t:
            resolution_times.append(res_t)

        try:
            is_od = t.is_overdue()
        except Exception:
            is_od = False
        if is_od:
            overdue_count += 1
            try:
                od_sec = int(t.overdue_seconds())
            except Exception:
                od_sec = 0
            if od_sec > 0:
                overdue_seconds_list.append(od_sec)

        aid = getattr(t, "assignee_id", None)
        if aid:
            row = assignee_map.setdefault(
                aid,
                {
                    "assignee_id": aid,
                    "assignee_name": getattr(getattr(t, "assignee", None), "get_full_name", lambda: "")() or getattr(getattr(t, "assignee", None), "username", ""),
                    "total": 0,
                    "overdue": 0,
                    "avg_overdue_sec": 0,
                },
            )
            row["total"] += 1
            if is_od:
                row["overdue"] += 1

    assignee_overdue_sec: dict[int, list[int]] = {}
    for t in tickets:
        aid = getattr(t, "assignee_id", None)
        if not aid:
            continue
        try:
            if t.is_overdue():
                sec = int(t.overdue_seconds())
                if sec > 0:
                    assignee_overdue_sec.setdefault(aid, []).append(sec)
        except Exception:
            continue

    for aid, secs in assignee_overdue_sec.items():
        if aid in assignee_map and secs:
            assignee_map[aid]["avg_overdue_sec"] = int(sum(secs) / len(secs))

    top_main = list(
        SupportTicket.objects.filter(created_at__gte=since)
        .values("main_category__kind", "main_category__name")
        .annotate(cnt=models.Count("id"))
        .order_by("-cnt")[:10]
    )

    top_sub = list(
        SupportTicket.objects.filter(created_at__gte=since)
        .values("sub_category__name", "main_category__kind", "main_category__name")
        .annotate(cnt=models.Count("id"))
        .order_by("-cnt")[:10]
    )

    def _avg(lst):
        return int(sum(lst) / len(lst)) if lst else 0

    summary = {
        "days": days,
        "since": since,
        "totals": {
            "total": total,
            "overdue": overdue_count,
            "open": by_status.get(TicketStatus.OPEN, 0),
            "in_progress": by_status.get(TicketStatus.IN_PROGRESS, 0),
            "paused": by_status.get(TicketStatus.PAUSED, 0),
            "closed": by_status.get(TicketStatus.CLOSED, 0),
            "req": by_kind.get(TicketKind.REQ, 0),
            "inc": by_kind.get(TicketKind.INC, 0),
        },
        "averages": {
            "avg_response_sec": _avg(response_times),
            "avg_resolution_sec": _avg(resolution_times),
            "avg_overdue_sec": _avg(overdue_seconds_list),
        },
        "assignees": sorted(assignee_map.values(), key=lambda x: (-x["overdue"], -x["total"]))[:20],
        "top_main_categories": top_main,
        "top_sub_categories": top_sub,
    }

    return summary


# =========================
# API (Step 7)
# =========================

def _ticket_to_dict(t: SupportTicket) -> dict:
    def _call(obj, name, default=None):
        fn = getattr(obj, name, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                return default
        return default

    deadline_base = getattr(t, "deadline_at", None)
    deadline_effective = _call(t, "effective_deadline_at", default=deadline_base) or deadline_base
    is_overdue = _call(t, "is_overdue", default=False)

    return {
        "id": t.id,
        "code": t.code,
        "kind": t.kind,
        "status": t.status,
        "source": t.source,
        "requester_id": t.requester_id,
        "assignee_id": getattr(t, "assignee_id", None),
        "main_category": {"id": t.main_category_id, "name": getattr(t.main_category, "name", None), "kind": getattr(t.main_category, "kind", None)}
        if getattr(t, "main_category_id", None) else None,
        "sub_category": {"id": t.sub_category_id, "name": getattr(t.sub_category, "name", None)}
        if getattr(t, "sub_category_id", None) else None,
        "sla_minutes": getattr(t, "sla_minutes", None),
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "first_response_at": getattr(t, "first_response_at", None).isoformat() if getattr(t, "first_response_at", None) else None,
        "closed_at": getattr(t, "closed_at", None).isoformat() if getattr(t, "closed_at", None) else None,
        "deadline_at": deadline_base.isoformat() if deadline_base else None,
        "effective_deadline_at": deadline_effective.isoformat() if deadline_effective else None,
        "overdue": bool(is_overdue),
        "overdue_seconds": _call(t, "overdue_seconds", default=0),
        "remaining_seconds": _call(t, "remaining_seconds", default=None),
        "description": getattr(t, "description", ""),
    }


def _api_error(message: str, *, status: int = 400, code: str = "bad_request"):
    return JsonResponse({"ok": False, "code": code, "message": message}, status=status)


def _api_ok(payload: dict, *, status: int = 200):
    resp = {"ok": True}
    resp.update(payload)
    return JsonResponse(resp, status=status)


@login_required
@require_GET
def api_tickets_list(request: HttpRequest) -> JsonResponse:
    qs = _ticket_queryset_for_user(request.user).select_related("main_category", "sub_category", "requester")

    kind = request.GET.get("kind")
    if kind in (TicketKind.REQ, TicketKind.INC):
        qs = qs.filter(kind=kind)

    status = request.GET.get("status")
    if status in dict(SupportTicket._meta.get_field("status").choices):
        qs = qs.filter(status=status)

    main_id = request.GET.get("main_category_id")
    if main_id and main_id.isdigit():
        qs = qs.filter(main_category_id=int(main_id))

    sub_id = request.GET.get("sub_category_id")
    if sub_id and sub_id.isdigit():
        qs = qs.filter(sub_category_id=int(sub_id))

    assignee_id = request.GET.get("assignee_id")
    if assignee_id:
        if not is_support(request.user):
            return _api_error("لا تملك صلاحية فلترة الموظف.", status=403, code="forbidden")
        if assignee_id.isdigit():
            qs = qs.filter(assignee_id=int(assignee_id))

    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(models.Q(code__icontains=q) | models.Q(description__icontains=q))

    overdue = request.GET.get("overdue")
    if overdue in ("0", "1"):
        want = overdue == "1"
        items = list(qs.order_by("-created_at")[:500])

        def _is_over(t):
            fn = getattr(t, "is_overdue", None)
            return bool(fn()) if callable(fn) else False

        items = [t for t in items if _is_over(t) == want]
        return _api_ok({"results": [_ticket_to_dict(t) for t in items], "count": len(items)})

    limit = request.GET.get("limit") or "50"
    try:
        limit_i = max(1, min(200, int(limit)))
    except Exception:
        limit_i = 50

    tickets = list(qs.order_by("-created_at")[:limit_i])
    return _api_ok({"results": [_ticket_to_dict(t) for t in tickets], "count": qs.count()})


@login_required
@require_POST
def api_tickets_create(request: HttpRequest) -> JsonResponse:
    if request.content_type and "application/json" in request.content_type:
        try:
            import json as _json
            data = _json.loads(request.body.decode("utf-8") or "{}")
        except Exception:
            return _api_error("JSON غير صالح.", status=400, code="invalid_json")
    else:
        data = request.POST

    form = TicketCreateForm(data, request.FILES)
    if not form.is_valid():
        return JsonResponse({"ok": False, "code": "validation_error", "errors": form.errors}, status=400)

    ticket: SupportTicket = form.save(commit=False)
    ticket.requester = request.user
    try:
        ticket.save()
    except Exception as ex:
        logger.exception("api create ticket failed")
        return _api_error(f"تعذر إنشاء التذكرة: {ex}", status=500, code="server_error")

    ticket = SupportTicket.objects.select_related("main_category", "sub_category").get(pk=ticket.pk)
    return _api_ok({"ticket": _ticket_to_dict(ticket)}, status=201)


@login_required
@require_GET
def api_ticket_detail(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(
        _ticket_queryset_for_user(request.user).select_related("main_category", "sub_category", "requester"),
        pk=pk,
    )
    comments = [
        {
            "id": c.id,
            "author_id": c.author_id,
            "body": c.body,
            "created_at": c.created_at.isoformat(),
            "is_support_reply": c.is_support_reply,
        }
        for c in ticket.comments.select_related("author").all()
    ]
    pauses = [
        {
            "id": p.id,
            "reason": p.reason,
            "started_at": p.started_at.isoformat() if p.started_at else None,
            "ended_at": p.ended_at.isoformat() if p.ended_at else None,
        }
        for p in ticket.pauses.all()
    ]
    return _api_ok({"ticket": _ticket_to_dict(ticket), "comments": comments, "pauses": pauses})


def _json_field(request: HttpRequest, key: str) -> str:
    if request.content_type and "application/json" in request.content_type:
        try:
            import json as _json
            return str((_json.loads(request.body.decode("utf-8") or "{}").get(key) or "")).strip()
        except Exception:
            raise ValueError("invalid_json")
    return str((request.POST.get(key) or "")).strip()


@login_required
@require_POST
def api_ticket_comment(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        body = _json_field(request, "body")
    except ValueError:
        return _api_error("JSON غير صالح.", status=400, code="invalid_json")

    try:
        TicketWorkflow.add_requester_comment(user=request.user, ticket=ticket, body=body)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api comment failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم إضافة التعليق."})


@login_required
@require_POST
def api_ticket_reply(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        body = _json_field(request, "body")
    except ValueError:
        return _api_error("JSON غير صالح.", status=400, code="invalid_json")

    try:
        TicketWorkflow.add_support_reply(user=request.user, ticket=ticket, body=body)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api reply failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم إضافة رد الدعم."})


@login_required
@require_POST
def api_ticket_pause(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        reason = _json_field(request, "reason")
    except ValueError:
        return _api_error("JSON غير صالح.", status=400, code="invalid_json")

    try:
        TicketWorkflow.pause_ticket(user=request.user, ticket=ticket, reason=reason)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api pause failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم تعليق التذكرة."})


@login_required
@require_POST
def api_ticket_resume(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        TicketWorkflow.resume_ticket(user=request.user, ticket=ticket)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api resume failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم استئناف التذكرة."})


@login_required
@require_POST
def api_ticket_close(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        closing_note = _json_field(request, "closing_note")
    except ValueError:
        return _api_error("JSON غير صالح.", status=400, code="invalid_json")

    try:
        res = TicketWorkflow.close_ticket(user=request.user, ticket=ticket, closing_note=closing_note)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api close failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم إغلاق التذكرة.", "extra": res.extra or {}})


@login_required
@require_POST
def api_ticket_assign(request: HttpRequest, pk: int) -> JsonResponse:
    ticket = get_object_or_404(_ticket_queryset_for_user(request.user), pk=pk)
    try:
        assignee_id = _json_field(request, "assignee_id")
    except ValueError:
        return _api_error("JSON غير صالح.", status=400, code="invalid_json")

    if not assignee_id.isdigit():
        return _api_error("assignee_id مطلوب.", status=400, code="validation_error")

    User = get_user_model()
    assignee = get_object_or_404(User, pk=int(assignee_id))

    try:
        TicketWorkflow.assign_ticket(user=request.user, ticket=ticket, assignee_user=assignee)
    except PermissionDenied as e:
        return _api_error(str(e), status=403, code="forbidden")
    except ValidationError as e:
        return _api_error(str(e), status=400, code="validation_error")
    except Exception:
        logger.exception("api assign failed")
        return _api_error("خطأ غير متوقع.", status=500, code="server_error")

    return _api_ok({"message": "تم تعيين التذكرة."})