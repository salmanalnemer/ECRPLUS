from django.urls import path
from . import views
from .views import ecr_dashcad
from django.contrib.auth.views import LogoutView
from .api_views import MeView, ChangePasswordView, LocationSharingView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.contrib.auth import logout
from responders.models import ResponderLocation


# API logout
class LogoutAPI(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):

        user = request.user

        # ايقاف مشاركة الموقع
        try:
            if hasattr(user, "location_sharing_enabled"):
                user.location_sharing_enabled = False
                user.save(update_fields=["location_sharing_enabled"])
        except Exception:
            pass

        # حذف اخر موقع للمستجيب ليصبح Offline مباشرة
        try:
            ResponderLocation.objects.filter(responder=user).delete()
        except Exception:
            pass

        # انهاء الجلسة
        logout(request)

        return Response({"ok": True})


urlpatterns = [
    path("login/", views.login_view, name="accounts_login"),
    path("verify-otp/", views.verify_otp_view, name="accounts_verify_otp"),
    path("forgot-password/", views.forgot_password_view, name="accounts_forgot_password"),
    path("reset-password/", views.reset_password_view, name="accounts_reset_password"),

    # Mobile/API logout
    path("api/logout/", LogoutAPI.as_view(), name="api_logout"),
    # Web logout
    path("logout/", LogoutView.as_view(next_page="/accounts/login/"), name="logout"),

    path("register/", views.register_view, name="accounts_register"),
    path("dashboard/main/", ecr_dashcad, name="ecr_dashcad"),

    # APIs
    path("api/me/", MeView.as_view(), name="api_me"),
    path("api/change-password/", ChangePasswordView.as_view(), name="api_change_password"),
    path("api/location-sharing/", LocationSharingView.as_view(), name="api_location_sharing"),

]