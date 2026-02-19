from django.contrib import admin
from django.utils import timezone

from .models import CADReport, CaseType
from .forms import CADReportForm


@admin.register(CaseType)
class CaseTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active", "created_at")
    search_fields = ("name",)
    list_filter = ("is_active",)


@admin.register(CADReport)
class CADReportAdmin(admin.ModelAdmin):
    form = CADReportForm
    list_display = (
        "cad_number",
        "case_type",
        "severity",
        "injured_count",
        "is_conscious",
        "region",
        "created_by",
        "created_at",
        "dispatched_at",
        "dispatched_source",
        "accepted_at",
        "accepted_source",
        "arrived_at",
        "arrived_source",
        "is_closed",
        "closed_by",
        "total_response_time",
    )
    search_fields = ("cad_number", "details", "location_text")
    list_filter = ("severity", "case_type", "region")
    readonly_fields = (
        "created_at",
        "updated_at",
        "time_to_dispatch",
        "time_to_accept",
        "time_to_arrive",
        "total_response_time",
    )

    def save_model(self, request, obj, form, change):
        """حفظ البلاغ من لوحة الإدارة مع دعم إغلاق البلاغ يدوياً بدون أخطاء.

        ملاحظة مهمة:
        - لأن closed_at مُعرّف كـ readonly_fields في admin، فلن يكون ضمن حقول الـModelForm.
        - ولكن model.clean() يتطلب وجود closed_at عند تفعيل is_closed.
        - لذلك نضمن تعبئة closed_at تلقائياً عند تفعيل الإغلاق من لوحة الإدارة.
        """
        if getattr(obj, "is_closed", False) and not getattr(obj, "closed_at", None):
            obj.closed_at = timezone.now()

        # لو أغلق من لوحة الإدارة ولم يُحدد من أغلقه، نخزّن المستخدم الحالي
        if getattr(obj, "is_closed", False) and not getattr(obj, "closed_by_id", None):
            obj.closed_by = request.user

        # تثبيت المصدر الافتراضي عند الإغلاق من الويب
        if getattr(obj, "is_closed", False) and getattr(obj, "closed_source", None) in (None, ""):
            obj.closed_source = "web_manual"

        super().save_model(request, obj, form, change)
