from __future__ import annotations

from django.contrib import admin

from .models import (
    SupportTicket,
    TicketComment,
    TicketPause,
    TicketMainCategory,
    TicketSubCategory,
)


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


@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "requester",
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
        "created_at",
        "first_response_at",
        "closed_at",
    )
    list_filter = ("status", "source", "kind", "main_category__kind", "created_at")
    search_fields = ("code", "requester__username", "requester__email", "description")
    readonly_fields = (
        "code",
        "kind",
        "created_at",
        "first_response_at",
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


@admin.register(TicketComment)
class TicketCommentAdmin(admin.ModelAdmin):
    list_display = ("ticket", "author", "is_support_reply", "created_at")
    list_filter = ("is_support_reply", "created_at")
    search_fields = ("ticket__code", "author__username", "body")


@admin.register(TicketPause)
class TicketPauseAdmin(admin.ModelAdmin):
    list_display = ("ticket", "reason", "started_at", "ended_at")
    list_filter = ("reason",)
