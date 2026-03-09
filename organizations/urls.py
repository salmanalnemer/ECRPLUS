from django.urls import path
from .api_views import organizations_by_region

urlpatterns = [
    path("api/by-region/<int:region_id>/", organizations_by_region, name="organizations_by_region"),
]