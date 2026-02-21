from __future__ import annotations

from django.urls import path
from . import views

app_name = "support_tickets"

urlpatterns = [
    path("", views.ticket_list, name="list"),
    path("new/", views.ticket_create, name="create"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/dashboard/summary/", views.api_dashboard_summary, name="api_dashboard_summary"),
    path("api/main-categories/", views.api_main_categories, name="api_main_categories"),
    path("api/sub-categories/", views.api_sub_categories, name="api_sub_categories"),

    path("api/tickets/", views.api_tickets_list, name="api_tickets_list"),
    path("api/tickets/create/", views.api_tickets_create, name="api_tickets_create"),
    path("api/tickets/<int:pk>/", views.api_ticket_detail, name="api_ticket_detail"),
    path("api/tickets/<int:pk>/comment/", views.api_ticket_comment, name="api_ticket_comment"),
    path("api/tickets/<int:pk>/reply/", views.api_ticket_reply, name="api_ticket_reply"),
    path("api/tickets/<int:pk>/pause/", views.api_ticket_pause, name="api_ticket_pause"),
    path("api/tickets/<int:pk>/resume/", views.api_ticket_resume, name="api_ticket_resume"),
    path("api/tickets/<int:pk>/close/", views.api_ticket_close, name="api_ticket_close"),
    path("api/tickets/<int:pk>/assign/", views.api_ticket_assign, name="api_ticket_assign"),
    path("<int:pk>/", views.ticket_detail, name="detail"),

    path("tickets/", views.ticket_list, name="ticket_list"),
    path("tickets/create/", views.ticket_create, name="ticket_create"),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
]