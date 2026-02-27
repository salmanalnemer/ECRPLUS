from django.urls import path

from .api_views import (
    MeView,
    ChangePasswordView,
    LocationSharingView,
    LogoutAPIView,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="api_me"),
    path("change-password/", ChangePasswordView.as_view(), name="api_change_password"),
    path("location-sharing/", LocationSharingView.as_view(), name="api_location_sharing"),
    path("logout/", LogoutAPIView.as_view(), name="api_logout"),
]