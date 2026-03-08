from django.urls import path
from . import views

app_name = "cad_reports_api"

urlpatterns = [
    path("assigned-reports/", views.assigned_reports_api, name="assigned_reports_api"),
]