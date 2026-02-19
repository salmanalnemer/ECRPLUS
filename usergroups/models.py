from django.db import models
from django.contrib.auth.models import Group

class UserGroup(models.Model):
    """
    مجموعات نظام ECR
    مرتبطة مع Django Group لإدارة الصلاحيات.
    """

    class DataScope(models.TextChoices):
        ALL_REGIONS = "ALL", "جميع المناطق"
        OWN_REGION = "REGION", "منطقة المستخدم فقط"

    name_ar = models.CharField("اسم المجموعة", max_length=255, unique=True)
    code = models.CharField("كود المجموعة", max_length=20, unique=True)

    # هل المجموعة خاصة بالمستجيبين (موبايل)
    is_mobile_group = models.BooleanField("مجموعة موبايل", default=False)

    # ✅ نطاق البيانات لهذه المجموعة
    data_scope = models.CharField(
        "نطاق البيانات",
        max_length=10,
        choices=DataScope.choices,
        default=DataScope.OWN_REGION,
        help_text="يحدد هل ترى هذه المجموعة جميع المناطق أم منطقة المستخدم فقط.",
    )

    # ربط مع Django Auth Group
    django_group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="ecr_group",
        verbose_name="مجموعة Django",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField("مفعّلة", default=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "مجموعة"
        verbose_name_plural = "المجموعات"
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar

    """
    مجموعات نظام ECR
    مرتبطة مع Django Group لإدارة الصلاحيات.
    """

    name_ar = models.CharField("اسم المجموعة", max_length=255, unique=True)
    code = models.CharField("كود المجموعة", max_length=20, unique=True)

    # هل المجموعة خاصة بالمستجيبين (موبايل)
    is_mobile_group = models.BooleanField("مجموعة موبايل", default=False)

    # ربط مع Django Auth Group
    django_group = models.OneToOneField(
        Group,
        on_delete=models.CASCADE,
        related_name="ecr_group",
        verbose_name="مجموعة Django",
        null=True,
        blank=True,
    )

    is_active = models.BooleanField("مفعّلة", default=True)

    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        verbose_name = "مجموعة"
        verbose_name_plural = "المجموعات"
        ordering = ["name_ar"]

    def __str__(self):
        return self.name_ar
