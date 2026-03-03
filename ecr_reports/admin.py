from __future__ import annotations

from django.contrib import admin

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog


@admin.register(MedicalConditionCatalog)
class MedicalConditionCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(ServiceCatalog)
class ServiceCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(MobileReport)
class MobileReportAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "created_by", "medical_condition", "gender", "latitude", "longitude")
    list_filter = ("gender", "medical_condition")
    search_fields = ("id", "notes")
    filter_horizontal = ("services",)