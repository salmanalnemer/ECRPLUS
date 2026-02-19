from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog
from ecr_reports.utils.geo import point_in_geojson_polygon


class MedicalConditionCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalConditionCatalog
        fields = ["id", "name"]


class ServiceCatalogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCatalog
        fields = ["id", "name"]


class MobileReportCreateSerializer(serializers.ModelSerializer):
    services_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        write_only=True,
        help_text="قائمة IDs للخدمات المقدمة",
    )

    class Meta:
        model = MobileReport
        fields = [
            "id",
            "patient_name",
            "national_id",
            "patient_phone",
            "age",
            "nationality",
            "gender",
            "medical_condition",
            "services_ids",
            "called_ambulance",
            "ambulance_called_by",
            "latitude",
            "longitude",
            "send_to_997",
        ]

    def validate_patient_name(self, value: str) -> str:
        v = (value or "").strip()
        if not v:
            raise serializers.ValidationError("اسم المريض إجباري.")
        return v

    def validate(self, attrs: dict) -> dict:
        called = attrs.get("called_ambulance", False)
        called_by = (attrs.get("ambulance_called_by") or "").strip()
        if called and not called_by:
            raise serializers.ValidationError({"ambulance_called_by": "حدد (أنا/شخص آخر) عند اختيار طلب إسعاف."})
        if not called and called_by:
            raise serializers.ValidationError({"ambulance_called_by": "لا يمكن تحديد هذا الحقل بدون اختيار طلب إسعاف."})

        # تحقق الإحداثيات
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")
        if lat is None or lng is None:
            raise serializers.ValidationError("الموقع (خط العرض/الطول) إجباري.")

        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except Exception:  # noqa: BLE001
            raise serializers.ValidationError("الإحداثيات غير صحيحة.")

        if not (-90 <= lat_f <= 90 and -180 <= lng_f <= 180):
            raise serializers.ValidationError("الإحداثيات خارج النطاق العالمي.")

        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> MobileReport:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise serializers.ValidationError("يجب تسجيل الدخول.")

        services_ids = validated_data.pop("services_ids", [])

        # المنطقة تُحدد من المستخدم نفسه (منع التلاعب)
        user_region = getattr(user, "region", None)
        if user_region is None:
            raise serializers.ValidationError("لا يمكن إنشاء البلاغ بدون ربط المستخدم بمنطقة.")

        # تحقق حدود المنطقة إذا كانت مضافة في Region (boundary_geojson)
        boundary = getattr(user_region, "boundary_geojson", None)
        if boundary:
            ok = point_in_geojson_polygon(validated_data["latitude"], validated_data["longitude"], boundary)
            if not ok:
                raise serializers.ValidationError("يرجى اختيار الموقع داخل منطقتك فقط.")

        report = MobileReport.objects.create(
            created_by=user,
            region=user_region,
            **validated_data,
        )

        if services_ids:
            qs = ServiceCatalog.objects.filter(id__in=services_ids, is_active=True)
            report.services.set(qs)

        return report


class MobileReportSerializer(serializers.ModelSerializer):
    medical_condition_name = serializers.CharField(source="medical_condition.name", read_only=True)
    services = ServiceCatalogSerializer(many=True, read_only=True)
    region_name = serializers.CharField(source="region.name_ar", read_only=True)

    class Meta:
        model = MobileReport
        fields = [
            "id",
            "patient_name",
            "national_id",
            "patient_phone",
            "age",
            "nationality",
            "gender",
            "medical_condition",
            "medical_condition_name",
            "services",
            "called_ambulance",
            "ambulance_called_by",
            "latitude",
            "longitude",
            "region",
            "region_name",
            "send_to_997",
            "created_at",
        ]
