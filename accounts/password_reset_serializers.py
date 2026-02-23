from rest_framework import serializers


class PasswordResetRequestSerializer(serializers.Serializer):
    national_id = serializers.CharField(required=True, allow_blank=False)


class PasswordResetVerifySerializer(serializers.Serializer):
    national_id = serializers.CharField(required=True, allow_blank=False)
    otp = serializers.CharField(required=True, allow_blank=False)


class PasswordResetConfirmSerializer(serializers.Serializer):
    national_id = serializers.CharField(required=True, allow_blank=False)
    otp = serializers.CharField(required=True, allow_blank=False)
    new_password = serializers.CharField(required=True, min_length=8, allow_blank=False)