from __future__ import annotations

from django.contrib import admin

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog


@admin.register(MedicalConditionCatalog)
class MedicalConditionCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ServiceCatalog)
class ServiceCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(MobileReport)
class MobileReportAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "patient_name",
        "patient_phone",
        "region",
        "temperature",
        "pulse_rate",
        "blood_pressure",
        "respiratory_rate",
        "blood_sugar",
        "called_ambulance",
        "send_to_997",
        "created_at",
    )
    list_filter = ("region", "called_ambulance", "send_to_997", "nationality", "gender")
    search_fields = ("patient_name", "patient_phone", "national_id")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)
    filter_horizontal = ("services",)