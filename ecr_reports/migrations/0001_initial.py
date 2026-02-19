# Generated manually for initial structure of ecr_reports app.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.core.validators
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("regions", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MedicalConditionCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True, verbose_name="اسم الحالة")),
                ("is_active", models.BooleanField(default=True, verbose_name="مفعّل")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")),
            ],
            options={
                "verbose_name": "كتالوج الحالة المرضية",
                "verbose_name_plural": "كتالوج الحالات المرضية",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="ServiceCatalog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, unique=True, verbose_name="اسم الخدمة")),
                ("is_active", models.BooleanField(default=True, verbose_name="مفعّل")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")),
            ],
            options={
                "verbose_name": "كتالوج الخدمات المقدمة",
                "verbose_name_plural": "كتالوج الخدمات المقدمة",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="MobileReport",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("patient_name", models.CharField(max_length=200, verbose_name="اسم المريض")),
                ("national_id", models.CharField(blank=True, default="", max_length=20, verbose_name="رقم الهوية")),
                (
                    "patient_phone",
                    models.CharField(
                        max_length=20,
                        validators=[
                            django.core.validators.RegexValidator(
                                message="رقم الجوال غير صالح. أدخل أرقام فقط ويمكن إضافة + في البداية.",
                                regex="^\\+?\\d{7,15}$",
                            )
                        ],
                        verbose_name="رقم الجوال",
                    ),
                ),
                ("age", models.PositiveSmallIntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0)], verbose_name="العمر")),
                ("nationality", models.CharField(choices=[("saudi", "سعودي"), ("resident", "مقيم")], default="saudi", max_length=20, verbose_name="الجنسية")),
                ("gender", models.CharField(choices=[("male", "ذكر"), ("female", "أنثى")], default="male", max_length=10, verbose_name="الجنس")),
                ("called_ambulance", models.BooleanField(default=False, verbose_name="هل تم طلب إسعاف؟")),
                (
                    "ambulance_called_by",
                    models.CharField(
                        blank=True,
                        choices=[("self", "أنا"), ("other", "شخص آخر")],
                        default="",
                        help_text="يظهر فقط إذا كان (هل تم طلب إسعاف؟) = نعم",
                        max_length=10,
                        verbose_name="من طلب الإسعاف",
                    ),
                ),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9, verbose_name="خط العرض")),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9, verbose_name="خط الطول")),
                (
                    "created_at",
                    models.DateTimeField(default=django.utils.timezone.now, verbose_name="تاريخ البلاغ"),
                ),
                (
                    "send_to_997",
                    models.BooleanField(
                        default=False,
                        help_text="يوثق رغبة المستخدم (يتم إرجاع نص جاهز للمشاركة/الإبلاغ عبر التطبيق).",
                        verbose_name="إرسال توثيق الحالة إلى 997",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mobile_reports",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المُبلّغ",
                    ),
                ),
                (
                    "medical_condition",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reports",
                        to="ecr_reports.medicalconditioncatalog",
                        verbose_name="تفاصيل الحالة المرضية",
                    ),
                ),
                (
                    "region",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="mobile_reports",
                        to="regions.region",
                        verbose_name="المنطقة",
                    ),
                ),
            ],
            options={
                "verbose_name": "بلاغ تطبيق",
                "verbose_name_plural": "بلاغات التطبيق",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddField(
            model_name="mobilereport",
            name="services",
            field=models.ManyToManyField(blank=True, related_name="reports", to="ecr_reports.servicecatalog", verbose_name="الخدمات المقدمة للمريض"),
        ),
        migrations.AddIndex(
            model_name="mobilereport",
            index=models.Index(fields=["region", "created_at"], name="ecr_report_region__cfa0d3_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilereport",
            index=models.Index(fields=["created_by", "created_at"], name="ecr_report_created_25f31b_idx"),
        ),
    ]
