from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ecr_reports", "0002_rename_ecr_report_region__cfa0d3_idx_ecr_reports_region__aa7f57_idx_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="MobileReportHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("create", "إنشاء"), ("update", "تعديل"), ("other", "عملية")], db_index=True, max_length=30, verbose_name="الإجراء")),
                ("note", models.TextField(blank=True, default="", verbose_name="التفاصيل")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="وقت العملية")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ecr_report_history_actions", to=settings.AUTH_USER_MODEL, verbose_name="المنفّذ")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="ecr_reports.mobilereport", verbose_name="البلاغ")),
            ],
            options={
                "verbose_name": "سجل بلاغ تطبيق",
                "verbose_name_plural": "سجل بلاغات التطبيق",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="mobilereporthistory",
            index=models.Index(fields=["report", "created_at"], name="ecr_report__report__8f7c0a_idx"),
        ),
        migrations.AddIndex(
            model_name="mobilereporthistory",
            index=models.Index(fields=["action", "created_at"], name="ecr_report__action__b0b7b5_idx"),
        ),
    ]
