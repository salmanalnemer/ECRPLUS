from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import render

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog
from ecr_reports.permissions import IsEcrMobileReporter
from ecr_reports.serializers import (
    MedicalConditionCatalogSerializer,
    MobileReportCreateSerializer,
    MobileReportSerializer,
    ServiceCatalogSerializer,
)


class MedicalConditionCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = MedicalConditionCatalog.objects.filter(is_active=True)
    serializer_class = MedicalConditionCatalogSerializer
    permission_classes = [IsEcrMobileReporter]


class ServiceCatalogViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    queryset = ServiceCatalog.objects.filter(is_active=True)
    serializer_class = ServiceCatalogSerializer
    permission_classes = [IsEcrMobileReporter]


class MobileReportViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,   # ✅✅ إضافة التعديل الحقيقي (PATCH/PUT)
    viewsets.GenericViewSet,
):
    permission_classes = [IsEcrMobileReporter]

    def get_queryset(self):
        user = self.request.user

        qs = (
            MobileReport.objects
            .select_related("region", "medical_condition")
            .prefetch_related("services")
        )

        # ✅ منطق التطبيق كما هو: المستخدم العادي يشوف بلاغاته فقط
        # ✅ إضافة عملية للويب: لو المستخدم staff يقدر يشوف الكل (للتعديل اليدوي)
        if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
            return qs

        return qs.filter(created_by=user)

    def get_serializer_class(self):
        if self.action in {"create"}:
            return MobileReportCreateSerializer
        return MobileReportSerializer

    @action(detail=True, methods=["get"], url_path="documentation")
    def documentation(self, request, pk=None):
        """يعيد نصاً جاهزاً لمشاركة توثيق الحالة/إبلاغ 997 عبر التطبيق."""
        report: MobileReport = self.get_object()

        services = ", ".join([s.name for s in report.services.all()]) or "-"
        condition = report.medical_condition.name if report.medical_condition else "-"
        ambulance = "نعم" if report.called_ambulance else "لا"
        ambulance_by = report.get_ambulance_called_by_display() if report.ambulance_called_by else "-"

        text = (
            "بلاغ تطبيق ECR\n"
            f"اسم المريض: {report.patient_name}\n"
            f"رقم الهوية: {report.national_id or '-'}\n"
            f"الجوال: {report.patient_phone}\n"
            f"العمر: {report.age if report.age is not None else '-'}\n"
            f"الجنسية: {report.get_nationality_display()}\n"
            f"الجنس: {report.get_gender_display()}\n"
            f"درجة الحرارة: {report.temperature if report.temperature is not None else '-'}\n"
            f"معدل النبض: {report.pulse_rate if report.pulse_rate is not None else '-'}\n"
            f"ضغط الدم: {report.blood_pressure or '-'}\n"
            f"معدل التنفس: {report.respiratory_rate if report.respiratory_rate is not None else '-'}\n"
            f"نسبة السكر في الدم: {report.blood_sugar if report.blood_sugar is not None else '-'}\n"
            f"ملاحظات: {report.notes or '-'}\n"
            f"تفاصيل الحالة: {condition}\n"
            f"الخدمات المقدمة: {services}\n"
            f"هل تم طلب إسعاف؟: {ambulance}\n"
            f"من طلب الإسعاف: {ambulance_by}\n"
            f"الموقع: {report.latitude}, {report.longitude}\n"
            f"المنطقة: {report.region.name_ar}\n"
            f"وقت البلاغ: {report.created_at:%Y-%m-%d %H:%M}\n"
        )

        return Response({"report_id": report.pk, "send_to_997": report.send_to_997, "text": text})

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        report = serializer.save()
        out = MobileReportSerializer(report, context={"request": request}).data
        headers = self.get_success_headers(out)
        return Response(out, status=status.HTTP_201_CREATED, headers=headers)


# ==========================
# ✅ Web Dashboard (NEW)
# ==========================

def _get_user_map_center(user):
    """
    مركز الخريطة يعتمد على منطقة المستخدم في Django فقط:
    - region.center_lat
    - region.center_lng
    - region.default_zoom
    fallback: المملكة
    """
    center_lat = None
    center_lng = None
    zoom = 9

    region = getattr(user, "region", None)
    if region:
        try:
            if getattr(region, "center_lat", None) is not None:
                center_lat = float(region.center_lat)
        except Exception:
            center_lat = None

        try:
            if getattr(region, "center_lng", None) is not None:
                center_lng = float(region.center_lng)
        except Exception:
            center_lng = None

        try:
            if getattr(region, "default_zoom", None) is not None:
                zoom = int(region.default_zoom)
        except Exception:
            zoom = 9

    if center_lat is None or center_lng is None:
        # السعودية بالكامل
        center_lat = 23.8859
        center_lng = 45.0792
        zoom = 5

    return center_lat, center_lng, zoom


def _ui_status_for_report(r: MobileReport) -> tuple[str, str]:
    """
    تحويل بلاغ MobileReport إلى حالة UI (لأن الموديل ما فيه status):
    - أحمر (urgent): إذا send_to_997=True
    - أصفر (active): إذا called_ambulance=True
    - أخضر (ok): إذا ما فيه إسعاف ولا 997 (اعتبره مستقر)
    - رمادي: fallback
    """
    try:
        if bool(getattr(r, "send_to_997", False)):
            return "red", "عاجل (إرسال 997)"
        if bool(getattr(r, "called_ambulance", False)):
            return "yellow", "تم طلب إسعاف"
        return "green", "بلاغ مسجّل"
    except Exception:
        return "gray", "غير محدد"


@login_required
def reports_ecr_dashboard(request):
    """
    صفحة Web احترافية لبلاغات ECR:
    - جدول كامل بكل حقول MobileReport
    - زر (عين) يفتح مودال: خريطة + تفاصيل البلاغ + نص توثيق جاهز
    - مركز الخريطة من منطقة المستخدم (Django فقط)
    """
    user = request.user

    qs = (
        MobileReport.objects
        .select_related("region", "medical_condition", "created_by")
        .prefetch_related("services")
        .order_by("-created_at")
    )

    # ✅ staff/superuser يشوف الكل (لوحة ويب)، غير ذلك يشوف منطقة المستخدم فقط
    if not (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        region_id = getattr(user, "region_id", None)
        if region_id:
            qs = qs.filter(region_id=region_id)
        else:
            qs = qs.none()

    # لا تسحب أعداد ضخمة بالويب
    reports = list(qs[:1000])

    # ✅ احصائيات احترافية (منطق واقعي حسب موديلك)
    total = len(reports)
    to_997 = sum(1 for r in reports if bool(getattr(r, "send_to_997", False)))
    ambulance = sum(1 for r in reports if bool(getattr(r, "called_ambulance", False)))
    stable = max(total - to_997 - ambulance, 0)

    stats = {
        "total": total,
        "urgent": to_997,          # أحمر
        "open": ambulance,         # أصفر
        "closed": stable,          # أخضر (اعتبرناها “مستقرة/مسجلة”)
        "last_updated": reports[0].created_at.strftime("%Y-%m-%d %H:%M") if reports else None,
    }

    # ✅ attach UI status لكل report للاستخدام في القالب
    for r in reports:
        cls, label = _ui_status_for_report(r)
        setattr(r, "ui_status_class", cls)
        setattr(r, "ui_status_label", label)

    # كتالوج الحالات للفلترة داخل القالب (اختياري)
    conditions_json = list(
        MedicalConditionCatalog.objects.filter(is_active=True).values("id", "name").order_by("name")
    )

    center_lat, center_lng, zoom = _get_user_map_center(user)

    return render(
        request,
        "dashboard/reports_ecr.html",
        {
            "google_maps_api_key": getattr(settings, "GOOGLE_MAPS_API_KEY", ""),
            "map_center_lat": center_lat,
            "map_center_lng": center_lng,
            "map_zoom": zoom,
            "reports": reports,
            "stats": stats,
            "conditions_json": conditions_json,
        },
    )