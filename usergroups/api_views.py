from __future__ import annotations

from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .models import UserGroup


@require_GET
def responder_groups_by_organization(request, organization_id: int):
    qs = UserGroup.objects.filter(is_active=True).order_by("name")

    data = [{"id": g.id, "code": g.code, "name": g.name} for g in qs]
    return JsonResponse(data, safe=False)