from __future__ import annotations

import secrets
from django.core.exceptions import ValidationError
from django.db import models, transaction


def _generate_5digit_code() -> str:
    """
    يولّد كود من 5 أرقام عشوائية (00000 - 99999)
    باستخدام secrets (أكثر أمانًا من random).
    """
    return f"{secrets.randbelow(100000):05d}"


class Organization(models.Model):
    """
    الجهات (كتالوج)
    - name: اسم الجهة (يدوي)
    - code: كود 5 أرقام (يتولد تلقائيًا عند الحفظ إذا لم يُدخل)
    """

    name = models.CharField("اسم الجهة", max_length=255, unique=True)
    code = models.CharField(
        "كود الجهة (5 أرقام)",
        max_length=5,
        unique=True,
        blank=True,
        editable=False,  # لا يظهر للتعديل داخل Admin Form افتراضيًا
        db_index=True,
    )
    is_active = models.BooleanField("مفعّلة", default=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "جهة"
        verbose_name_plural = "الجهات"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        super().clean()

        # إذا تم إدخال code لأي سبب، تأكد أنه 5 أرقام فقط
        if self.code:
            if (len(self.code) != 5) or (not self.code.isdigit()):
                raise ValidationError({"code": "كود الجهة يجب أن يكون 5 أرقام فقط."})

    def save(self, *args, **kwargs):
        """
        توليد كود تلقائي 5 أرقام عند أول حفظ إذا كان فارغًا.
        مع محاولة إعادة التوليد عند حدوث تعارض (نادر).
        """
        if not self.code:
            # نحاول عدة مرات لتفادي تعارض UNIQUE
            for _ in range(20):
                candidate = _generate_5digit_code()
                if not Organization.objects.filter(code=candidate).exists():
                    self.code = candidate
                    break

            if not self.code:
                # احتمال نادر جدًا (مثلاً قاعدة كبيرة جدًا/تصادمات)
                raise RuntimeError("تعذر توليد كود فريد للجهة بعد عدة محاولات.")

        return super().save(*args, **kwargs)
