from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    SupportTicket,
    TicketComment,
    PauseReason,
    TicketMainCategory,
    TicketSubCategory,
)


class TicketCreateForm(forms.ModelForm):
    class Meta:
        model = SupportTicket
        fields = ["source", "main_category", "sub_category", "description", "image"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Labels بالعربي حسب المطلوب
        self.fields["source"].label = "مصدر الطلب"
        self.fields["main_category"].label = "تصنيف البلاغ الرئيسي"
        self.fields["sub_category"].label = "تصنيف البلاغ الفرعي"
        self.fields["description"].label = "وصف المشكلة"
        self.fields["image"].label = "إرفاق صورة من المشكلة (اختياري)"

        # QuerySets (active فقط)
        self.fields["main_category"].queryset = (
            TicketMainCategory.objects.filter(is_active=True).order_by("kind", "name")
        )

        # افتراضيًا الفرعي فاضي لين يختار الرئيسي
        self.fields["sub_category"].queryset = TicketSubCategory.objects.none()

        main_id = self.data.get("main_category") or self.initial.get("main_category") or getattr(self.instance, "main_category_id", None)
        if main_id:
            try:
                main_id_int = int(main_id)
                self.fields["sub_category"].queryset = (
                    TicketSubCategory.objects.filter(is_active=True, main_category_id=main_id_int)
                    .order_by("name")
                )
            except (TypeError, ValueError):
                pass

        # الصورة اختيارية
        self.fields["image"].required = False

    def clean(self):
        cleaned = super().clean()

        main = cleaned.get("main_category")
        sub = cleaned.get("sub_category")

        if not main:
            raise ValidationError({"main_category": "اختر تصنيفًا رئيسيًا."})

        if not sub:
            raise ValidationError({"sub_category": "اختر تصنيفًا فرعيًا."})

        if sub.main_category_id != main.id:
            raise ValidationError({"sub_category": "التصنيف الفرعي لا يتبع التصنيف الرئيسي المختار."})

        return cleaned


class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]


class SupportReplyForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]

    def save(self, commit=True):
        obj: TicketComment = super().save(commit=False)
        obj.is_support_reply = True
        if commit:
            obj.save()
        return obj


class PauseForm(forms.Form):
    reason = forms.ChoiceField(choices=PauseReason.choices)


class ResumeForm(forms.Form):
    resume = forms.BooleanField(required=True)


class CloseForm(forms.Form):
    close = forms.BooleanField(required=True)