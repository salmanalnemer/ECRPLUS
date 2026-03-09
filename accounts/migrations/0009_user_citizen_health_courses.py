from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0008_alter_emailotp_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="citizen_health_courses",
            field=models.JSONField(
                blank=True,
                default=list,
                verbose_name="الدورات الصحية للمواطن",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="citizen_other_health_courses",
            field=models.TextField(
                blank=True,
                default="",
                help_text="يمكن كتابة أكثر من دورة، كل دورة في سطر أو مفصولة بفواصل.",
                verbose_name="دورات صحية أخرى",
            ),
        ),
    ]