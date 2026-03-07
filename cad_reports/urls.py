from __future__ import annotations

from django.urls import path

from . import views
from .views_ai import ai_hotspots_page, cad_api_ai_hotspots, cad_api_case_types
from .views_mobile_api import (
    cad_accept,
    cad_arrive,
    cad_assigned_reports,
    cad_chat,
    cad_close,
    cad_my_reports,
    cad_reject,
    register_device_token,
)

app_name = "cad_reports"

urlpatterns = [
    # ==========================
    # Pages
    # ==========================
    path("", views.list_reports, name="list"),
    path("new/", views.reports_cad_page, name="page"),
    path("reports-cad-ecr/", views.reports_cad_ecr, name="reports_cad_ecr"),
    path("reports/", views.cad_reports_reports_page, name="cad_reports_reports"),

    # ==========================
    # Print view
    # ==========================
    path("print/<int:report_id>/", views.cad_report_print, name="print_report"),

    # ==========================
    # Dashboards
    # ==========================
    path("dashboard/main/", views.main_dashboard_page, name="main_dashboard_page"),
    path("dashboard/cad/", views.reports_cad_dashboard, name="reports_cad_dashboard"),
    path("dashboard/ecr/", views.reports_ecr_dashboard, name="reports_ecr_dashboard"),

    # ==========================
    # AI Hotspots Map Page
    # ==========================
    path("ai/hotspots/", ai_hotspots_page, name="cad_ai_hotspots_page"),

    # ==========================
    # JSON for dashboard pages
    # ==========================
    path("assigned-reports-json/", views.assigned_reports_json, name="assigned_reports_json"),

    # ==========================
    # CRUD
    # ==========================
    path("create/", views.create_report, name="create"),
    path("<int:report_id>/", views.report_detail, name="detail"),

    # ==========================
    # Workflow
    # ==========================
    path("<int:report_id>/dispatch/", views.dispatch_report, name="dispatch"),
    path("<int:report_id>/accept/", views.accept_report, name="accept"),
    path("<int:report_id>/arrive/", views.arrive_report, name="arrive"),
    path("<int:report_id>/close/", views.close_report, name="close"),

    # ==========================
    # API - dashboard / stats
    # ==========================
    path("api/dashboard/summary/", views.api_dashboard_summary, name="api_dashboard_summary"),
    path("api/responders/online/", views.responders_online_json, name="responders_online_json"),
    path("api/activity/<int:report_id>/", views.cad_activity_history, name="cad_activity_history"),

    # ==========================
    # API - AI
    # ==========================
    path("api/ai/hotspots/", cad_api_ai_hotspots, name="cad_api_ai_hotspots"),
    path("api/case-types/", cad_api_case_types, name="cad_api_case_types"),

    # ==========================
    # API by report_id
    # ==========================
    path("api/<int:report_id>/accept/", views.api_accept_report, name="api_accept"),
    path("api/<int:report_id>/arrive/", views.api_mark_arrived, name="api_arrive"),
    path("api/<int:report_id>/close/", views.api_close_report, name="api_close"),

    # ==========================
    # API by cad_number
    # ==========================
    path("api/assigned/<str:cad_number>/accept/", views.api_assigned_accept, name="api_assigned_accept"),
    path("api/assigned/<str:cad_number>/arrive/", views.api_assigned_arrive, name="api_assigned_arrive"),
    path("api/assigned/<str:cad_number>/close/", views.api_assigned_close, name="api_assigned_close"),
    path("api/assigned/<str:cad_number>/update/", views.api_assigned_update, name="api_assigned_update"),

    # ==========================
    # Mobile / app APIs
    # ==========================
    path("api/assigned/<str:cad_number>/mobile-accept/", cad_accept, name="cad_accept"),
    path("api/assigned/<str:cad_number>/mobile-arrive/", cad_arrive, name="cad_arrive"),
    path("api/assigned/<str:cad_number>/mobile-close/", cad_close, name="cad_close"),
    path("api/assigned/<str:cad_number>/reject/", cad_reject, name="cad_reject"),
    path("api/assigned/<str:cad_number>/chat/", cad_chat, name="cad_chat"),

    # ==========================
    # Lists
    # ==========================
    path("api/assigned-reports/", cad_assigned_reports, name="cad_assigned_reports"),
    path("api/my-reports/", cad_my_reports, name="cad_my_reports"),

    # ==========================
    # Device token
    # ==========================
    path("api/device-token/", register_device_token, name="cad_device_token"),
]