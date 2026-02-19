from django.db import migrations


GROUPS = [
    ("المركز الوطني الإسعافي للقيادة والسيطرة", "NEMSCC", False),
    ("مدراء إدارة التحكم العملياتي بالفروع", "BOCM", False),
    ("مرحلين غرف العمليات بالفروع", "ORRB", False),
    ("إدارة التطوع بالفروع", "BVM", False),
    ("الدعم الفني", "ITS", False),
    ("مدير النظام", "SYSADMIN", False),
    ("المستجيبين", "ECRMOBIL", True),
]


def seed_groups(apps, schema_editor):
    UserGroup = apps.get_model("usergroups", "UserGroup")
    Group = apps.get_model("auth", "Group")

    for name, code, is_mobile in GROUPS:
        django_group, _ = Group.objects.get_or_create(name=name)

        UserGroup.objects.update_or_create(
            code=code,
            defaults={
                "name_ar": name,
                "is_mobile_group": is_mobile,
                "django_group": django_group,
                "is_active": True,
            },
        )


def unseed_groups(apps, schema_editor):
    UserGroup = apps.get_model("usergroups", "UserGroup")
    Group = apps.get_model("auth", "Group")

    codes = [g[1] for g in GROUPS]
    UserGroup.objects.filter(code__in=codes).delete()

    names = [g[0] for g in GROUPS]
    Group.objects.filter(name__in=names).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("usergroups", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_groups, unseed_groups),
    ]
