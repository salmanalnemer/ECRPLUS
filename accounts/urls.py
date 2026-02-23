from django.urls import path
from . import views
from .views import ecr_dashcad
from django.contrib.auth.views import LogoutView
from .api_views import MeView, ChangePasswordView, LocationSharingView

urlpatterns = [
    # Auth
    path("login/", views.login_view, name="accounts_login"),
    path("verify-otp/", views.verify_otp_view, name="accounts_verify_otp"),
    path("forgot-password/", views.forgot_password_view, name="accounts_forgot_password"),
    path("reset-password/", views.reset_password_view, name="accounts_reset_password"),
    path("logout/", LogoutView.as_view(next_page="/accounts/login/"), name="logout"),
    # Register
    path("register/", views.register_view, name="accounts_register"),
    path("portal/ecr_dashcad/", ecr_dashcad, name="ecr_dashcad"),
]