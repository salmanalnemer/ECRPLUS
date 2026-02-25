from __future__ import annotations

from django.contrib import admin

from .models import (
    SupportTicket,              # تذكرة الدعم الفني
    TicketComment,              # التعليقات / التواصل على التذكرة
    TicketPause,                # تعليق التذكرة (إيقاف مؤقت)
    TicketMainCategory,         # التصنيف الرئيسي للتذكرة
    TicketSubCategory,          # التصنيف الفرعي
    TicketStatusCatalog,        # كتلوج حالات التذاكر
    TicketPauseReasonCatalog,   # كتلوج أسباب تعليق التذكرة
    TicketSolutionCatalog,      # كتلوج الحلول
    TicketStatusLog,            # سجل تغييرات حالة التذكرة
    TicketSequence,             # تسلسل أرقام التذاكر (REQ / INC)
)


@admin.register(TicketStatusCatalog)
class TicketStatusCatalogAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "is_active", "requires_pause_reason", "is_closed", "sort_order", "updated_at")
    list_filter = ("is_active", "requires_pause_reason", "is_closed")
    search_fields = ("code", "name")
    ordering = ("sort_order", "name")


@admin.register(TicketPauseReasonCatalog)
class TicketPauseReasonCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("sort_order", "name")


@admin.register(TicketSolutionCatalog)
class TicketSolutionCatalogAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("name",)
    ordering = ("sort_order", "name")


@admin.register(TicketMainCategory)
class TicketMainCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "name", "sla_minutes", "is_active", "created_at", "updated_at")
    list_filter = ("kind", "is_active")
    search_fields = ("name",)
    ordering = ("kind", "name")


@admin.register(TicketSubCategory)
class TicketSubCategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "main_category", "name", "sla_minutes_override", "is_active", "created_at", "updated_at")
    list_filter = ("main_category__kind", "is_active")
    search_fields = ("name", "main_category__name")
    ordering = ("main_category__kind", "main_category__name", "name")


@admin.register(TicketSequence)
class TicketSequenceAdmin(admin.ModelAdmin):
    list_display = ("prefix", "last_number", "updated_at")
    search_fields = ("prefix",)
    ordering = ("prefix",)


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "requester_name",
        "requester_national_id",
        "requester_phone",
        "requester_email",
        "region",
        "assignee",
        "source",
        "kind",
        "main_category",
        "sub_category",
        "sla_minutes",
        "effective_deadline",
        "overdue_flag",
        "overdue_minutes",
        "status",
        "pause_reason",
        "created_at",
        "first_response_at",
        "assigned_at",
        "last_status_changed_at",
        "closed_at",
    )
    list_filter = ("status", "source", "kind", "region", "main_category__kind", "created_at")
    search_fields = ("code", "requester_name", "requester_email", "requester_phone", "description")
    readonly_fields = (
        "code",
        "kind",
        "created_at",
        "first_response_at",
        "assigned_at",
        "last_status_changed_at",
        "closed_at",
        "deadline_at",
        "sla_minutes",
    )

    @admin.display(description="Deadline (Effective)")
    def effective_deadline(self, obj: SupportTicket):
        return obj.effective_deadline_at()

    @admin.display(description="Overdue", boolean=True)
    def overdue_flag(self, obj: SupportTicket) -> bool:
        return obj.is_overdue()

    @admin.display(description="Overdue (min)")
    def overdue_minutes(self, obj: SupportTicket) -> int:
        return int(obj.overdue_seconds() // 60)


@admin.register(TicketStatusLog)
class TicketStatusLogAdmin(admin.ModelAdmin):
    list_display = ("ticket", "from_status", "to_status", "changed_by", "changed_at")
    list_filter = ("to_status", "changed_at")
    search_fields = ("ticket__code", "changed_by__username")


@admin.register(TicketPause)
class TicketPauseAdmin(admin.ModelAdmin):
    list_display = ("ticket", "reason", "started_at", "ended_at")
    list_filter = ("reason",)
    search_fields = ("ticket__code",)


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "is_support_reply", "is_internal", "created_at")
    list_filter = ("is_support_reply", "is_internal")
    search_fields = ("ticket__code", "author__username", "body")
