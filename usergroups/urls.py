from django.urls import path
from .api_views import responder_groups_by_organization

urlpatterns = [
    path("api/responders/<int:organization_id>/", responder_groups_by_organization, name="usergroups_responders_by_org"),
]