from __future__ import annotations

import logging

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import (
    HttpResponse,
    HttpResponseForbidden,
    HttpResponseNotFound,
    HttpResponseServerError,
)
from django.shortcuts import render
from django.urls import include, path
from django.views.generic import RedirectView, TemplateView

from rest_framework_simplejwt.views import TokenRefreshView

from accounts.jwt_views import NationalIdTokenObtainPairView
from accounts.password_reset_views import (
    PasswordResetConfirmView,
    PasswordResetRequestView,
    PasswordResetVerifyView,

)
from accounts.registration_api_views import (
    register,
    resend_verify_email,
    verify_email,
)

from ecr.catalog_api_views import (
    OrganizationsCatalogAPIView,
    RegionsCatalogAPIView,
)

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Custom Error Handlers (Production-safe)
# -----------------------------------------------------------------------------
def custom_404(request, exception):
    logger.warning("404 Not Found: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "404.html", status=404)
    except Exception:
        return HttpResponseNotFound("404 Not Found")


def custom_403(request, exception):
    logger.warning("403 Forbidden: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "403.html", status=403)
    except Exception:
        return HttpResponseForbidden("403 Forbidden")


def custom_500(request):
    logger.exception("500 Internal Server Error: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "500.html", status=500)
    except Exception:
        return HttpResponseServerError("500 Internal Server Error")


handler404 = custom_404
handler403 = custom_403
handler500 = custom_500


# -----------------------------------------------------------------------------
# Health Check (Render)
# -----------------------------------------------------------------------------
def healthz(_request):
    return HttpResponse("ok", content_type="text/plain")


# -----------------------------------------------------------------------------
# URL Patterns
# -----------------------------------------------------------------------------
urlpatterns = [
    # Root -> Login
    path("", RedirectView.as_view(url="/accounts/login/", permanent=False), name="root"),

    # Admin
    path("sansecr/", admin.site.urls),

    # Health
    path("healthz/", healthz),

    # -------------------------------------------------------------------------
    # Web Apps
    # -------------------------------------------------------------------------
    path("accounts/", include("accounts.urls")),

    # CAD Web فقط
    path("cad/", include(("cad_reports.urls", "cad_reports"), namespace="cad_reports")),

    # Responders Web
    path("responders/", include("responders.urls")),

    # Support Web
    path(
        "support/",
        include(("support_tickets.urls", "support_tickets"), namespace="support_tickets"),
    ),

    # -------------------------------------------------------------------------
    # APIs
    # -------------------------------------------------------------------------
    path("api/ecr/", include(("ecr_reports.urls", "ecr_reports"), namespace="ecr_reports")),

    # Responders API
    path("api/responders/", include(("responders.urls", "responders"), namespace="responders")),

    # CAD API فقط
    path("api/cad/", include("cad_reports.urls")),

    # Auth (JWT)
    path("api/auth/login/", NationalIdTokenObtainPairView.as_view(), name="jwt_login"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="jwt_refresh"),

    # Register + Verify Email
    path("api/auth/register/", register, name="api_register"),
    path("api/auth/verify-email/", verify_email, name="api_verify_email"),
    path("api/auth/verify-email/resend/", resend_verify_email, name="api_verify_email_resend"),

    # Accounts API
    path("api/accounts/", include("accounts.api_urls")),

    # Catalog APIs (Mobile App)
    path("api/catalog/regions/", RegionsCatalogAPIView.as_view(), name="api_catalog_regions"),
    path("api/catalog/organizations/", OrganizationsCatalogAPIView.as_view(), name="api_catalog_organizations"),

    # Password Reset APIs
    path("api/auth/password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("api/auth/password-reset/verify/", PasswordResetVerifyView.as_view(), name="password_reset_verify"),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),

    # WebSocket test
    path("ws-test/", TemplateView.as_view(template_name="ws_test.html"), name="ws_test"),
]

# Media in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)