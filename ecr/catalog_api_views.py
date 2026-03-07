from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from regions.models import Region
from organizations.models import Organization


class RegionsCatalogAPIView(APIView):
    """GET /api/catalog/regions/

    Returns:
      [{"id": 1, "name_ar": "...", "code": "..."}, ...]
    """

    permission_classes = [AllowAny]

    def get(self, request):
        qs = Region.objects.filter(is_active=True).order_by("name_ar")
        data = [{"id": r.id, "name_ar": r.name_ar, "code": r.code} for r in qs]
        return Response(data)


class OrganizationsCatalogAPIView(APIView):
    """GET /api/catalog/organizations/

    Optional query:
      - region_id (currently not used because Organization model has no region FK)

    Returns:
      [{"id": 1, "name_ar": "جهة ...", "code": "12345"}, ...]

    NOTE:
      If you later add region relation, filter by it here.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        qs = Organization.objects.filter(is_active=True).order_by("name")
        data = [{"id": o.id, "name_ar": o.name, "code": o.code} for o in qs]
        return Response(data)
