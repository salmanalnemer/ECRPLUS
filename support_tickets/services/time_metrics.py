from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def safe_seconds(delta: Optional[timedelta]) -> int:
    if not delta:
        return 0
    return max(0, int(delta.total_seconds()))


def between(a: Optional[datetime], b: Optional[datetime]) -> int:
    if not a or not b:
        return 0
    if b < a:
        return 0
    return int((b - a).total_seconds())