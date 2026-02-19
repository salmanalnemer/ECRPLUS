from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cad_reports", "0003_cadreport_assigned_responder"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cadreport",
            name="is_closed",
            field=models.BooleanField(db_index=True, default=False, verbose_name="مغلق؟"),
        ),
        migrations.AddField(
            model_name="cadreport",
            name="closed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت الإغلاق"),
        ),
        migrations.AddField(
            model_name="cadreport",
            name="closed_source",
            field=models.CharField(
                choices=[
                    ("web_manual", "يدوي (لوحة الوِب)"),
                    ("mobile_manual", "يدوي (جوال المستجيب)"),
                    ("auto", "آلي"),
                ],
                default="web_manual",
                max_length=20,
                verbose_name="مصدر الإغلاق",
            ),
        ),
        migrations.AddField(
            model_name="cadreport",
            name="closed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cad_closed_reports",
                to=settings.AUTH_USER_MODEL,
                verbose_name="أُغلق بواسطة",
            ),
        ),
    ]
