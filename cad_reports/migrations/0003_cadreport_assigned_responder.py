from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("cad_reports", "0002_alter_cadreport_cad_number"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="cadreport",
            name="assigned_responder",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cad_assigned_reports",
                to=settings.AUTH_USER_MODEL,
                verbose_name="المستجيب المُعيّن",
            ),
        ),
    ]
