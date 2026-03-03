from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, HttpResponseNotFound, HttpResponseForbidden, HttpResponseServerError
from django.urls import path, include
from django.conf.urls.static import static
from django.shortcuts import render
from django.views.generic import RedirectView
from django.views.generic import TemplateView

from rest_framework_simplejwt.views import TokenRefreshView
from accounts.jwt_views import NationalIdTokenObtainPairView
from accounts.password_reset_views import (
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
)

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Custom Error Handlers (Production-safe)
# -----------------------------------------------------------------------------
def custom_404(request, exception):
    # سجل 404 (مفيد لتتبع روابط مكسورة)
    logger.warning("404 Not Found: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "404.html", status=404)
    except Exception:
        return HttpResponseNotFound("404 Not Found")


def custom_403(request, exception):
    # سجل 403 (صلاحيات)
    logger.warning("403 Forbidden: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "403.html", status=403)
    except Exception:
        return HttpResponseForbidden("403 Forbidden")


def custom_500(request):
    """
    ✅ الأهم:
    - يسجّل الاستثناء الحقيقي في Logs (Render / gunicorn)
    - ويحاول يعرض 500.html
    - ولو 500.html نفسها فيها مشكلة، يرجع نص بسيط بدل انهيار إضافي
    """
    logger.exception("500 Internal Server Error: path=%s", getattr(request, "path", ""))
    try:
        return render(request, "500.html", status=500)
    except Exception:
        return HttpResponseServerError("500 Internal Server Error")


handler404 = custom_404
handler500 = custom_500
handler403 = custom_403


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

    # Admin (مسار مخصص)
    path("sansecr/", admin.site.urls),

    # Render health check
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
    # مسار اختبار WebSocket (يمكن حذفه لاحقًا)
    path("ws-test/", TemplateView.as_view(template_name="ws_test.html"), name="ws_test"),
]

# Media in development only
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)