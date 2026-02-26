from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse
from django.urls import path, include
from django.conf.urls.static import static
from django.conf.urls import handler404, handler500, handler403
from django.shortcuts import render

from rest_framework_simplejwt.views import TokenRefreshView
from accounts.jwt_views import NationalIdTokenObtainPairView

from accounts.password_reset_views import (
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
)
from django.views.generic import RedirectView

# -----------------------------------------------------------------------------
# Custom Error Handlers
# -----------------------------------------------------------------------------
def custom_404(request, exception):
    return render(request, "404.html", status=404)


def custom_500(request):
    return render(request, "500.html", status=500)


def custom_403(request, exception):
    return render(request, "403.html", status=403)


handler404 = custom_404
handler500 = custom_500
handler403 = custom_403

def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")
# -----------------------------------------------------------------------------
# URL Patterns
# -----------------------------------------------------------------------------
urlpatterns = [
    path("", RedirectView.as_view(url="/accounts/login/", permanent=False), name="root"),
    path("sansecr/", admin.site.urls),
    path("healthz/", healthz),
    # Web Apps
    path("accounts/", include("accounts.urls")),
    path("cad/", include(("cad_reports.urls", "cad_reports"), namespace="cad_reports")),
    path("responders/", include("responders.urls")),
    path("support/", include(("support_tickets.urls", "support_tickets"), namespace="support_tickets")),

    # APIs
    path("api/ecr/", include(("ecr_reports.urls", "ecr_reports"), namespace="ecr_reports")),
    path("api/responders/", include(("responders.urls", "responders"), namespace="responders")),
    path("api/auth/login/", NationalIdTokenObtainPairView.as_view(), name="jwt_login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="jwt_refresh"),
    path("api/accounts/", include("accounts.api_urls")),

    # Password Reset APIs
    path("api/auth/password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("api/auth/password-reset/verify/", PasswordResetVerifyView.as_view(), name="password_reset_verify"),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
]

# Media in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)