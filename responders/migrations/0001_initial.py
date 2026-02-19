# Generated manually for initial setup

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ResponderLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("latitude", models.DecimalField(decimal_places=6, max_digits=9, verbose_name="خط العرض")),
                ("longitude", models.DecimalField(decimal_places=6, max_digits=9, verbose_name="خط الطول")),
                ("accuracy_m", models.FloatField(blank=True, null=True, verbose_name="الدقة (متر)")),
                ("speed_m_s", models.FloatField(blank=True, null=True, verbose_name="السرعة (م/ث)")),
                ("heading_deg", models.FloatField(blank=True, null=True, verbose_name="الاتجاه (درجة)")),
                ("device_id", models.CharField(blank=True, max_length=128, null=True, verbose_name="معرّف الجهاز")),
                ("platform", models.CharField(blank=True, max_length=32, null=True, verbose_name="النظام")),
                ("app_version", models.CharField(blank=True, max_length=32, null=True, verbose_name="إصدار التطبيق")),
                ("last_seen", models.DateTimeField(db_index=True, default=django.utils.timezone.now, verbose_name="آخر ظهور")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")),
                (
                    "responder",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="responder_location",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المستجيب",
                    ),
                ),
            ],
            options={
                "verbose_name": "موقع مستجيب",
                "verbose_name_plural": "مواقع المستجيبين",
                "ordering": ["-last_seen"],
            },
        ),
    ]
