from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Region


@require_GET
def regions_list(request):
    """إرجاع كتالوج المناطق لاستخدام تطبيق Flutter."""
    qs = Region.objects.filter(is_active=True).order_by("name_ar")
    data = [{"id": r.id, "code": r.code, "name": r.name_ar} for r in qs]
    return JsonResponse(data, safe=False)
