from __future__ import annotations

import secrets
import string
from typing import Callable

DIGITS = string.digits


def _random_digits(n: int = 8) -> str:
    return "".join(secrets.choice(DIGITS) for _ in range(n))


def generate_ticket_code(prefix: str, exists_fn: Callable[[str], bool], digits: int = 8, max_tries: int = 50) -> str:
    """
    يولّد كود غير متسلسل باستخدام secrets ويضمن التفرد عبر exists_fn.
    مثال: INC12345678 / REQ12345678 / ECR12345678
    """
    prefix = prefix.strip().upper()
    for _ in range(max_tries):
        code = f"{prefix}{_random_digits(digits)}"
        if not exists_fn(code):
            return code
    raise RuntimeError("تعذر توليد كود فريد بعد عدة محاولات. راجع الفهرس/القيود أو زد max_tries.")