from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ecr_reports.views import (
    MedicalConditionCatalogViewSet,
    MobileReportViewSet,
    ServiceCatalogViewSet,
    reports_ecr_dashboard,  # ✅ Web dashboard view
)

app_name = "ecr_reports"

router = DefaultRouter()
router.register(r"catalog/conditions", MedicalConditionCatalogViewSet, basename="conditions")
router.register(r"catalog/services", ServiceCatalogViewSet, basename="services")
router.register(r"mobile-reports", MobileReportViewSet, basename="mobile-reports")

urlpatterns = [
    # ==========================
    # Web Dashboard
    # ==========================
    path("dashboard/ecr/", reports_ecr_dashboard, name="reports_ecr_dashboard"),

    # ==========================
    # API
    # ==========================
    path("", include(router.urls)),
]
