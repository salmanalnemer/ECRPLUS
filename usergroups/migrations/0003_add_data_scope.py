from django.db import migrations, models


def set_default_scopes(apps, schema_editor):
    UserGroup = apps.get_model("usergroups", "UserGroup")

    # ALL = يرى جميع المناطق
    UserGroup.objects.filter(code__in=["NEMSCC", "SYSADMIN"]).update(data_scope="ALL")

    # REGION = يرى منطقته فقط (احتياط)
    UserGroup.objects.exclude(code__in=["NEMSCC", "SYSADMIN"]).update(data_scope="REGION")


class Migration(migrations.Migration):

    dependencies = [
        ("usergroups", "0002_seed_groups"),
    ]

    operations = [
        migrations.AddField(
            model_name="usergroup",
            name="data_scope",
            field=models.CharField(
                verbose_name="نطاق البيانات",
                max_length=10,
                choices=[("ALL", "جميع المناطق"), ("REGION", "منطقة المستخدم فقط")],
                default="REGION",
                help_text="يحدد هل ترى هذه المجموعة جميع المناطق أم منطقة المستخدم فقط.",
            ),
        ),
        migrations.RunPython(set_default_scopes, migrations.RunPython.noop),
    ]
