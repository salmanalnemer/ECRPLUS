from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from .models import (
    SupportTicket,
    TicketComment,
    TicketMainCategory,
    TicketSubCategory,
    TicketPauseReasonCatalog,
    TicketSolutionCatalog,
    TicketStatusCatalog,
)


class TicketCreateForm(forms.ModelForm):
    """إنشاء تذكرة (المستخدم).

    - اسم مقدم التذكرة + الهوية/الجوال/الايميل تعبأ تلقائياً من حساب المستخدم (Snapshot).
    - الرقم (code) يتولّد تلقائياً.
    - الحالة تُضبط على OPEN تلقائياً في view (حسب كتلوج الحالة).
    """

    class Meta:
        model = SupportTicket
        fields = ["source", "main_category", "sub_category", "description", "image"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["source"].label = "تم الرفع عن طريق"
        self.fields["main_category"].label = "التصنيف الرئيسي"
        self.fields["sub_category"].label = "التصنيف الفرعي"
        self.fields["description"].label = "وصف المشكلة/الطلب"
        self.fields["image"].label = "إرفاق صورة (اختياري)"

        self.fields["main_category"].queryset = TicketMainCategory.objects.filter(is_active=True).order_by("kind", "name")
        self.fields["sub_category"].queryset = TicketSubCategory.objects.none()

        main_id = (
            self.data.get("main_category")
            or self.initial.get("main_category")
            or getattr(self.instance, "main_category_id", None)
        )
        if main_id:
            try:
                main_id_int = int(main_id)
                self.fields["sub_category"].queryset = TicketSubCategory.objects.filter(
                    is_active=True,
                    main_category_id=main_id_int,
                ).order_by("name")
            except (TypeError, ValueError):
                pass

        self.fields["image"].required = False

    def clean(self):
        cleaned = super().clean()
        main = cleaned.get("main_category")
        sub = cleaned.get("sub_category")

        if not main:
            raise ValidationError({"main_category": "اختر التصنيف الرئيسي."})
        if not sub:
            raise ValidationError({"sub_category": "اختر التصنيف الفرعي."})
        if sub and main and sub.main_category_id != main.id:
            raise ValidationError({"sub_category": "التصنيف الفرعي لا يتبع التصنيف الرئيسي المختار."})
        return cleaned


class CommentForm(forms.ModelForm):
    class Meta:
        model = TicketComment
        fields = ["body"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4, "placeholder": "اكتب ردك..."})}

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise ValidationError("نص الرد مطلوب.")
        return body


class SupportReplyForm(forms.Form):
    body = forms.CharField(label="رد الدعم الفني", widget=forms.Textarea(attrs={"rows": 4}))
    is_internal = forms.BooleanField(label="تعليق داخلي (لا يظهر للمستخدم)", required=False)

    def clean_body(self):
        body = (self.cleaned_data.get("body") or "").strip()
        if not body:
            raise ValidationError("نص الرد مطلوب.")
        return body


class PauseForm(forms.Form):
    reason = forms.ModelChoiceField(
        label="سبب التعليق",
        queryset=TicketPauseReasonCatalog.objects.filter(is_active=True).order_by("sort_order", "name"),
        empty_label="اختر سبب التعليق",
    )


class ResumeForm(forms.Form):
    confirm = forms.BooleanField(label="تأكيد الاستئناف", required=True)


class StatusChangeForm(forms.Form):
    status = forms.ModelChoiceField(
        label="الحالة",
        queryset=TicketStatusCatalog.objects.filter(is_active=True).order_by("sort_order", "name"),
        empty_label="اختر الحالة",
    )
    pause_reason = forms.ModelChoiceField(
        label="سبب التعليق (إن لزم)",
        queryset=TicketPauseReasonCatalog.objects.filter(is_active=True).order_by("sort_order", "name"),
        required=False,
        empty_label="—",
    )

    def clean(self):
        cleaned = super().clean()
        st = cleaned.get("status")
        pr = cleaned.get("pause_reason")
        if st and st.requires_pause_reason and not pr:
            raise ValidationError({"pause_reason": "هذه الحالة تتطلب سبب تعليق."})
        if st and (not st.requires_pause_reason) and pr:
            cleaned["pause_reason"] = None
        return cleaned


class CloseForm(forms.Form):
    solution_catalog = forms.ModelChoiceField(
        label="نوع الحل (كتلوج)",
        queryset=TicketSolutionCatalog.objects.filter(is_active=True).order_by("sort_order", "name"),
        empty_label="اختر نوع الحل",
    )
    solution_notes = forms.CharField(label="ملاحظات الحل", widget=forms.Textarea(attrs={"rows": 4}))

    def clean_solution_notes(self):
        notes = (self.cleaned_data.get("solution_notes") or "").strip()
        if not notes:
            raise ValidationError("ملاحظات الحل إلزامية.")
        return notes
