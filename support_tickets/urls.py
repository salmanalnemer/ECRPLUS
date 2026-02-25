from __future__ import annotations

from django.urls import path
from . import views

app_name = "support_tickets"

urlpatterns = [
    # =========================
    # ✅ Pages (NEW Templates)
    # =========================
    path("dashboard/sla/", views.support_sla_dashboard, name="support_sla_dashboard"),

    # صفحات القوالب داخل templates/support_tickets/
    path("pages/new/", views.support_ticket_create_page, name="support_ticket_create_page"),
    path("pages/assigned/", views.support_tickets_assigned_to_me, name="support_tickets_assigned_to_me"),
    path("pages/open/", views.support_tickets_open_page, name="support_tickets_open_page"),
    path("pages/resolved/", views.support_tickets_resolved_page, name="support_tickets_resolved_page"),
    path("pages/closed/", views.support_tickets_closed_page, name="support_tickets_closed_page"),

    # ✅ Ticket Detail Page (FIX: was missing)
    # هذا يطابق اللي في القالب: {% url 'support_tickets:ticket_detail' t.id %}
    path("pages/<int:pk>/", views.ticket_detail, name="ticket_detail"),

    # ✅ Alias (عشان redirect("support_tickets:detail", pk=...) في views.py ما ينكسر)
    path("detail/<int:pk>/", views.ticket_detail, name="detail"),

    # =========================
    # ✅ (Optional) Root redirect page
    # =========================
    # خلي /support/ يفتح لوحة SLA مباشرة
    path("", views.support_sla_dashboard, name="home"),

    # =========================
    # Catalog APIs (KEEP)
    # =========================
    path("api/main-categories/", views.api_main_categories, name="api_main_categories"),
    path("api/sub-categories/", views.api_sub_categories, name="api_sub_categories"),
    path("api/statuses/", views.api_status_catalog, name="api_status_catalog"),
    path("api/pause-reasons/", views.api_pause_reasons, name="api_pause_reasons"),
    path("api/solutions/", views.api_solution_catalog, name="api_solution_catalog"),
    path("api/assignees/", views.api_assignees, name="api_assignees"),

    # =========================
    # Ticket APIs (KEEP)
    # =========================
    path("api/tickets/", views.api_tickets_list, name="api_tickets_list"),
    path("api/tickets/create/", views.api_tickets_create, name="api_tickets_create"),
    path("api/tickets/<int:pk>/", views.api_ticket_detail, name="api_ticket_detail"),
    path("api/tickets/<int:pk>/comment/", views.api_ticket_comment, name="api_ticket_comment"),
    path("api/tickets/<int:pk>/reply/", views.api_ticket_reply, name="api_ticket_reply"),
    path("api/tickets/<int:pk>/pause/", views.api_ticket_pause, name="api_ticket_pause"),
    path("api/tickets/<int:pk>/resume/", views.api_ticket_resume, name="api_ticket_resume"),
    path("api/tickets/<int:pk>/change-status/", views.api_ticket_change_status, name="api_ticket_change_status"),
    path("api/tickets/<int:pk>/close/", views.api_ticket_close, name="api_ticket_close"),
    path("api/tickets/<int:pk>/assign/", views.api_ticket_assign, name="api_ticket_assign"),
]