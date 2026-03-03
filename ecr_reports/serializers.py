from __future__ import annotations

from django.db import transaction
from rest_framework import serializers

from ecr_reports.models import MedicalConditionCatalog, MobileReport, ServiceCatalog


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
            "medical_condition",
            "gender",
            "latitude",
            "longitude",
            "notes",
            "services_ids",
        ]

    def validate(self, attrs: dict) -> dict:
        lat = attrs.get("latitude")
        lng = attrs.get("longitude")
        if lat is None or lng is None:
            raise serializers.ValidationError("الموقع (خط العرض/الطول) إجباري.")
        return attrs

    @transaction.atomic
    def create(self, validated_data: dict) -> MobileReport:
        request = self.context.get("request")
        user = getattr(request, "user", None)

        if not user or not user.is_authenticated:
            raise serializers.ValidationError("لا يمكن إنشاء بلاغ بدون مستخدم مصادق عليه.")

        services_ids = validated_data.pop("services_ids", [])

        report = MobileReport.objects.create(created_by=user, **validated_data)

        if services_ids:
            qs = ServiceCatalog.objects.filter(id__in=services_ids, is_active=True)
            report.services.set(qs)

        return report


class MobileReportSerializer(serializers.ModelSerializer):
    created_by_id = serializers.IntegerField(source="created_by.id", read_only=True)
    created_by_name = serializers.CharField(source="created_by.get_username", read_only=True)
    medical_condition_name = serializers.CharField(source="medical_condition.name", read_only=True)
    services = ServiceCatalogSerializer(many=True, read_only=True)

    class Meta:
        model = MobileReport
        fields = [
            "id",
            "created_at",
            "created_by_id",
            "created_by_name",
            "medical_condition",
            "medical_condition_name",
            "gender",
            "latitude",
            "longitude",
            "notes",
            "services",
        ]