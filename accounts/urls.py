from django.urls import path
from . import views
from .views import ecr_dashcad
from django.contrib.auth.views import LogoutView
from .api_views import MeView, ChangePasswordView, LocationSharingView, LogoutAPIView


urlpatterns = [
    # Auth
    path("login/", views.login_view, name="accounts_login"),
    path("verify-otp/", views.verify_otp_view, name="accounts_verify_otp"),
    path("forgot-password/", views.forgot_password_view, name="accounts_forgot_password"),
    path("reset-password/", views.reset_password_view, name="accounts_reset_password"),
    path("logout/", LogoutView.as_view(next_page="/accounts/login/"), name="logout"),

    # Register
    path("register/", views.register_view, name="accounts_register"),
    path("dashboard/main/", ecr_dashcad, name="ecr_dashcad"),

    # ===== APIs =====
    path("api/me/", MeView.as_view(), name="api_me"),
    path("api/change-password/", ChangePasswordView.as_view(), name="api_change_password"),
    path("api/location-sharing/", LocationSharingView.as_view(), name="api_location_sharing"),
    path("api/logout/", LogoutAPIView.as_view(), name="api_logout"),
]