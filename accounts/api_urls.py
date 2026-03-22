from django.urls import path

from .api_views import (
    MeView,
    ChangePasswordView,
    LocationSharingView,
    NotificationSettingsView,
    LogoutAPIView,
)

urlpatterns = [
    path("me/", MeView.as_view(), name="api_me"),
    path("change-password/", ChangePasswordView.as_view(), name="api_change_password"),
    path("location-sharing/", LocationSharingView.as_view(), name="api_location_sharing"),
    path("notification-settings/", NotificationSettingsView.as_view(), name="notification-settings"),
    path("logout/", LogoutAPIView.as_view(), name="api_logout"),
]
