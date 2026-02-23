from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cad_reports", "0010_alter_cadreport_latitude_alter_cadreport_longitude"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="UserDeviceToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=512, unique=True, verbose_name="FCM Token")),
                ("platform", models.CharField(blank=True, default="", max_length=30, verbose_name="المنصة")),
                ("is_active", models.BooleanField(default=True, verbose_name="مفعّل")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="device_tokens", to=settings.AUTH_USER_MODEL, verbose_name="المستخدم")),
            ],
            options={
                "verbose_name": "Token جهاز (FCM)",
                "verbose_name_plural": "Tokens الأجهزة (FCM)",
                "ordering": ["-updated_at"],
            },
        ),
    ]
