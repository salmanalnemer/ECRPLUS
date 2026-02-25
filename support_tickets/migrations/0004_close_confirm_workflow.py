from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support_tickets", "0003_alter_supportticket_kind_alter_supportticket_source_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportticket",
            name="status",
            field=models.CharField(
                verbose_name="الحالة",
                max_length=40,
                choices=[
                    ("OPEN", "مفتوحة"),
                    ("IN_PROGRESS", "قيد المعالجة"),
                    ("PAUSED", "معلّقة (مؤقت)"),
                    ("CLOSE_REQUESTED", "طلب إغلاق من صاحب الطلب"),
                    ("AWAITING_REQUESTER_CONFIRM", "بانتظار تأكيد صاحب الطلب"),
                    ("CLOSED", "مغلقة"),
                ],
                default="OPEN",
            ),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="close_requested_at",
            field=models.DateTimeField(verbose_name="تاريخ طلب الإغلاق (صاحب الطلب)", blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="close_requested_reason",
            field=models.TextField(verbose_name="سبب طلب الإغلاق (صاحب الطلب)", blank=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="support_closed_at",
            field=models.DateTimeField(verbose_name="تاريخ إغلاق الدعم (حل/إنهاء)", blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="support_solution",
            field=models.TextField(verbose_name="حل/ملاحظات الدعم الفني", blank=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="requester_decision_at",
            field=models.DateTimeField(verbose_name="وقت قرار صاحب الطلب", blank=True, null=True),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="requester_reject_reason",
            field=models.TextField(verbose_name="سبب رفض الحل (صاحب الطلب)", blank=True),
        ),
    ]
