from __future__ import annotations

from django.urls import path

from . import views
from .views_ai import ai_hotspots_page, cad_api_ai_hotspots, cad_api_case_types

"""cad_reports URLs.

ملاحظة مهمة:
- مسارات dashboard التي تعتمد على cad_number يجب أن تعمل عبر جلسة الويب (Session) + CSRF
  لأن لوحة التحكم تستخدم تسجيل دخول Django العادي، وليس JWT.
- مسارات الموبايل تبقى في views_mobile_api وتستخدم JWT.

هذا الملف كان يربط مسارات dashboard (api/assigned/...) إلى نقاط JWT بالخطأ،
مما تسبب برسائل مثل: "لم يتم تزويد بيانات الدخول" أو HTTP 403.
"""

from .views_mobile_api import (
    cad_accept,
    cad_arrive,
    cad_close,
    cad_reject,
    cad_assigned_reports,
    register_device_token,
)

app_name = "cad_reports"

urlpatterns = [
    # ==========================
    # Pages
    # ==========================
    path("new/", views.reports_cad_page, name="page"),
    path("reports-cad-ecr/", views.reports_cad_ecr, name="reports_cad_ecr"),
    path("reports/", views.cad_reports_reports_page, name="cad_reports_reports"),

    # ==========================
    # Dashboards
    # ==========================
    path("dashboard/main/", views.main_dashboard_page, name="main_dashboard_page"),
    path("dashboard/cad/", views.reports_cad_dashboard, name="reports_cad_dashboard"),
    path("dashboard/ecr/", views.reports_ecr_dashboard, name="reports_ecr_dashboard"),

    # ==========================
    # Main dashboard API (KPIs + charts)
    # ==========================
    path("api/dashboard/summary/", views.api_dashboard_summary, name="api_dashboard_summary"),

    # ==========================
    # AI Hotspots Map Page
    # ==========================
    path("ai/hotspots/", ai_hotspots_page, name="cad_ai_hotspots_page"),

    # ==========================
    # AI APIs
    # ==========================
    path("api/ai/hotspots/", cad_api_ai_hotspots, name="cad_api_ai_hotspots"),
    path("api/case-types/", cad_api_case_types, name="cad_api_case_types"),

    # ==========================
    # JSON for dashboard
    # ==========================
    path("assigned-reports-json/", views.assigned_reports_json, name="assigned_reports_json"),

    # ==========================
    # Responders online JSON
    # ==========================
    path("api/responders/online/", views.responders_online_json, name="responders_online_json"),

    # ==========================
    # CRUD
    # ==========================
    path("", views.list_reports, name="list"),
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
    # API mobile/app
    # ==========================
    path("api/<int:report_id>/accept/", views.api_accept_report, name="api_accept"),
    path("api/<int:report_id>/arrive/", views.api_mark_arrived, name="api_arrive"),
    path("api/<int:report_id>/close/", views.api_close_report, name="api_close"),

    # ==========================
    # Dashboard API (CAD number)
    # ==========================
    # ✅ هذه هي endpoints الخاصة بلوحة الويب (Session-based)
    path("api/assigned/<str:cad_number>/accept/", views.api_assigned_accept, name="api_assigned_accept"),
    path("api/assigned/<str:cad_number>/arrive/", views.api_assigned_arrive, name="api_assigned_arrive"),
    path("api/assigned/<str:cad_number>/close/", views.api_assigned_close, name="api_assigned_close"),
    # reject لا يوجد له نسخة web حالياً؛ لو أضفت زر رفض في الويب لاحقاً أضف view هنا.
    path("api/assigned/<str:cad_number>/reject/", cad_reject, name="api_assigned_reject"),
    path("api/assigned/<str:cad_number>/update/", views.api_assigned_update, name="api_assigned_update"),

    # ==========================
    # Device token (FCM)
    # ==========================
    path("api/device-token/", register_device_token, name="api_device_token"),

    # ==========================
    # API mobile/app (CAD number)
    # ==========================
    path("cad/api/assigned/<str:cad_number>/accept/", cad_accept, name="cad_accept"),
    path("cad/api/assigned/<str:cad_number>/arrive/", cad_arrive, name="cad_arrive"),
    path("cad/api/assigned/<str:cad_number>/close/", cad_close, name="cad_close"),
    path("cad/api/assigned-reports/", cad_assigned_reports, name="cad_assigned_reports"),
    path("cad/api/device-token/", register_device_token, name="cad_device_token"),
    path("cad/api/assigned/<str:cad_number>/reject/", cad_reject, name="cad_reject"),
]