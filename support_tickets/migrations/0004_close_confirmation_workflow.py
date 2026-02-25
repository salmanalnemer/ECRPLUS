from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("support_tickets", "0003_alter_supportticket_kind_alter_supportticket_source_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="supportticket",
            name="close_requested_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ طلب الإغلاق من العميل"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="close_requested_reason",
            field=models.TextField(blank=True, verbose_name="سبب طلب الإغلاق من العميل"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="support_closed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ إغلاق الدعم (حل مقترح)"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="support_solution",
            field=models.TextField(blank=True, verbose_name="حل/ملاحظة الإغلاق من الدعم"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="requester_decision_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ قرار العميل"),
        ),
        migrations.AddField(
            model_name="supportticket",
            name="requester_reject_reason",
            field=models.TextField(blank=True, verbose_name="سبب رفض الحل (إن وجد)"),
        ),
    ]
