from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog
from ecr_reports.permissions import IsEcrMobileReporter
from ecr_reports.serializers import (
    MedicalConditionCatalogSerializer,
    MobileReportCreateSerializer,
    MobileReportSerializer,
    ServiceCatalogSerializer,
)


# ==========================
# API (Mobile)
# ==========================
class MedicalConditionCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MedicalConditionCatalog.objects.filter(is_active=True).order_by("name")
    serializer_class = MedicalConditionCatalogSerializer
    permission_classes = [IsEcrMobileReporter]


class ServiceCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ServiceCatalog.objects.filter(is_active=True).order_by("name")
    serializer_class = ServiceCatalogSerializer
    permission_classes = [IsEcrMobileReporter]


class MobileReportViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    permission_classes = [IsEcrMobileReporter]

    def get_queryset(self):
        return (
            MobileReport.objects.select_related("medical_condition", "created_by")
            .prefetch_related("services")
            .order_by("-created_at", "-id")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return MobileReportCreateSerializer
        return MobileReportSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        out = MobileReportSerializer(report, context={"request": request}).data
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)


# ==========================
# Portal / Dashboard (Web)
# ==========================
@login_required
def reports_ecr_dashboard(request):
    """Dashboard page for ECR Mobile reports.

    IMPORTANT:
    - Template path is project-level and MUST remain:
      templates/dashboard/reports_ecr.html
    - Your custom User model may NOT have `username`, so templates must not rely on it.
    """

    qs = (
        MobileReport.objects.select_related("created_by", "medical_condition")
        .prefetch_related("services")
        .order_by("-created_at", "-id")
    )

    # ---- Filters (GET) ----
    search = (request.GET.get("search") or "").strip()
    from_date = (request.GET.get("from") or "").strip()
    to_date = (request.GET.get("to") or "").strip()
    gender = (request.GET.get("gender") or "").strip()
    condition = (request.GET.get("condition") or "").strip()

    if search:
        if search.isdigit():
            s_int = int(search)
            qs = qs.filter(
                Q(id=s_int)
                | Q(created_by_id=s_int)
                | Q(medical_condition_id=s_int)
            )
        else:
            qs = qs.filter(
                Q(medical_condition__name__icontains=search)
                | Q(notes__icontains=search)
            )

    if from_date:
        qs = qs.filter(created_at__date__gte=from_date)
    if to_date:
        qs = qs.filter(created_at__date__lte=to_date)

    if gender in {MobileReport.Gender.MALE, MobileReport.Gender.FEMALE}:
        qs = qs.filter(gender=gender)

    if condition:
        if condition.isdigit():
            qs = qs.filter(medical_condition_id=int(condition))
        else:
            qs = qs.filter(medical_condition__name__icontains=condition)

    # ---- Pagination (fixed 10) ----
    page_size = 10
    paginator = Paginator(qs, page_size)
    page_number = request.GET.get("page") or 1
    reports_page = paginator.get_page(page_number)

    # ---- Display helpers (avoid template touching unknown User fields) ----
    for r in reports_page:
        u = getattr(r, "created_by", None)
        if not u:
            r.created_by_display = "—"
            r.created_by_handle = ""
            continue

        # Display name
        display = ""
        try:
            if hasattr(u, "get_full_name"):
                display = (u.get_full_name() or "").strip()
        except Exception:
            display = ""

        if not display:
            display = (getattr(u, "full_name", "") or "").strip()

        if not display:
            # fallback to __str__
            display = str(u)

        # Handle (optional)
        handle = ""
        for attr in ("email", "phone", "mobile", "national_id", "id_number"):
            v = getattr(u, attr, None)
            if v:
                handle = str(v).strip()
                break

        r.created_by_display = display
        r.created_by_handle = handle

    # ---- Stats ----
    now = timezone.localtime(timezone.now())
    today = now.date()
    stats = {
        "total": MobileReport.objects.count(),
        "today": MobileReport.objects.filter(created_at__date=today).count(),
        "male": MobileReport.objects.filter(gender=MobileReport.Gender.MALE).count(),
        "female": MobileReport.objects.filter(gender=MobileReport.Gender.FEMALE).count(),
        "last_updated": qs.first().created_at if qs.exists() else None,
    }

    conditions = MedicalConditionCatalog.objects.filter(is_active=True).order_by("name")

    return render(
        request,
        "dashboard/reports_ecr.html",
        {
            "reports": reports_page,
            "stats": stats,
            "conditions": conditions,
        },
    )


# Backward-compatible alias (if some urls imported old name)
reports_ecr_portal_page = reports_ecr_dashboard
