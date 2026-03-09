from django.urls import path
from .api_views import regions_list

urlpatterns = [
    path("api/list/", regions_list, name="regions_api_list"),
]