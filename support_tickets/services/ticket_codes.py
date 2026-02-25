from __future__ import annotations

from django.apps import apps
from django.db import transaction


def next_sequential_ticket_code(prefix: str, *, width: int = 6) -> str:
    """
    يولّد كود متسلسل وآمن للتزامن:
    - REQ000001
    - INC000001

    يتم حفظ آخر رقم لكل Prefix في جدول TicketSequence مع select_for_update لضمان عدم التكرار.

    ملاحظة: نستخدم apps.get_model لتجنب circular import أثناء إقلاع Django.
    """
    prefix = (prefix or "").strip().upper()
    if not prefix:
        raise ValueError("prefix is required")

    TicketSequence = apps.get_model("support_tickets", "TicketSequence")

    with transaction.atomic():
        seq, _created = TicketSequence.objects.select_for_update().get_or_create(
            prefix=prefix,
            defaults={"last_number": 0},
        )
        seq.last_number = int(seq.last_number or 0) + 1
        seq.save(update_fields=["last_number", "updated_at"])

        return f"{prefix}{seq.last_number:0{int(width)}d}"
