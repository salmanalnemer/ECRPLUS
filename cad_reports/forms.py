from django import forms
from django.utils import timezone

from .models import CADReport


class CADReportForm(forms.ModelForm):
    # نضيف الحقل صراحةً لضمان وجوده داخل الفورم (حتى لو كان readonly في الـAdmin)
    closed_at = forms.DateTimeField(
        required=False,
        widget=forms.HiddenInput(),
        label="وقت الإغلاق",
    )

    class Meta:
        model = CADReport
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()

        # لو تم تفعيل الإغلاق من لوحة الإدارة ولم يتم تمرير وقت الإغلاق
        # نضعه تلقائيًا لتجنب ValidationError داخل model.clean()
        is_closed = cleaned.get("is_closed")
        closed_at = cleaned.get("closed_at")

        if is_closed:
            # إذا لم يتم إدخال وقت الإغلاق يدوياً نضعه الآن
            if not closed_at:
                cleaned["closed_at"] = timezone.now()

        return cleaned
