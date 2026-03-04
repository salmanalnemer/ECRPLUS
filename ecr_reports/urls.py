from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from ecr_reports import views
from ecr_reports.views import (
    MedicalConditionCatalogViewSet,
    MobileReportViewSet,
    ServiceCatalogViewSet,
    reports_ecr_dashboard,
)

app_name = "ecr_reports"

router = DefaultRouter()
router.register(r"catalog/conditions", MedicalConditionCatalogViewSet, basename="conditions")
router.register(r"catalog/services", ServiceCatalogViewSet, basename="services")
router.register(r"mobile-reports", MobileReportViewSet, basename="mobile-reports")

urlpatterns = [
    # Dashboard / Portal (Web)
    path("dashboard/ecr-reports/", reports_ecr_dashboard, name="reports_ecr_dashboard"),
    path("dashboard/ecr/", reports_ecr_dashboard, name="reports_ecr_dashboard_alias"),
    #================================
    # طباعة البلاغ (Web) 
    path("print/<int:pk>/", views.ecr_report_print, name="report_print"),
    # old path kept (if you used it before)
    path("portal/reports/", reports_ecr_dashboard, name="portal_reports"),

    # API (Mobile)
    path("", include(router.urls)),
]
