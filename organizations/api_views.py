from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import Organization


@require_GET
def organizations_by_region(request, region_id: int):
    qs = Organization.objects.filter(
        is_active=True,
        region_id=region_id,
    ).order_by("name")

    data = [{"id": o.id, "code": o.code, "name": o.name} for o in qs]
    return JsonResponse(data, safe=False)