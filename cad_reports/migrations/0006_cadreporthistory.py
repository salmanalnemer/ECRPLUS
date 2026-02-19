from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("cad_reports", "0005_alter_cadreport_options"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="CADReportHistory",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action", models.CharField(choices=[("create", "إنشاء"), ("update", "تعديل"), ("dispatch", "ترحيل"), ("accept", "قبول"), ("arrive", "وصول"), ("start_action", "مباشرة"), ("close", "إغلاق")], db_index=True, max_length=30, verbose_name="الإجراء")),
                ("note", models.TextField(blank=True, default="", verbose_name="التفاصيل")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="وقت العملية")),
                ("actor", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="cad_report_history_actions", to=settings.AUTH_USER_MODEL, verbose_name="المنفّذ")),
                ("report", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="history", to="cad_reports.cadreport", verbose_name="البلاغ")),
            ],
            options={
                "verbose_name": "سجل بلاغ CAD",
                "verbose_name_plural": "سجل بلاغات CAD",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="cadreporthistory",
            index=models.Index(fields=["report", "created_at"], name="cad_report__report__0f1b37_idx"),
        ),
        migrations.AddIndex(
            model_name="cadreporthistory",
            index=models.Index(fields=["action", "created_at"], name="cad_report__action__7b2c42_idx"),
        ),
    ]
