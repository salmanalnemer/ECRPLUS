from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Organization


@require_GET
def organizations_list(request):
    """إرجاع كتالوج الجهات لاستخدام تطبيق Flutter.

    يدعم query param اختياري: region_id (حالياً للتوافق فقط).
    """
    _ = request.GET.get("region_id")  # للتوافق مع تطبيق Flutter
    qs = Organization.objects.filter(is_active=True).order_by("name")
    data = [{"id": o.id, "code": o.code, "name": o.name} for o in qs]
    return JsonResponse(data, safe=False)
