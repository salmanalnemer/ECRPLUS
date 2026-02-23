from django.conf import settings
from django.contrib import admin
from django.urls import path, include 
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import  TokenRefreshView
from accounts.jwt_views import NationalIdTokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.jwt_views import NationalIdTokenObtainPairView

urlpatterns = [
    # Admin panel
    path("admin/", admin.site.urls),
    # API حسابات المستخدمين (تسجيل، تسجيل دخول، إلخ)
    path("accounts/", include("accounts.urls")),
    # API بلاغات تطبيق CAD (الويب)
    path("cad/", include("cad_reports.urls", namespace="cad_reports")),
    # API المستجيبين (تتبع المواقع، إلخ)
    path("responders/", include("responders.urls")),
    # API تذاكر الدعم الفني
    path("support/", include("support_tickets.urls")),
    # API بلاغات تطبيق ECR (الجوال)
    path("support_tickets/", include("support_tickets.urls")),


    # API بلاغات تطبيق ECR (الجوال)
    path("api/ecr/", include("ecr_reports.urls", namespace="ecr_reports")),

    # API تتبع المستجيبين
    path("api/responders/", include("responders.urls", namespace="responders")),
    #تكامل التحقق من الهوية باستخدام JWT
    path("api/auth/login/", NationalIdTokenObtainPairView.as_view(), name="jwt_login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="jwt-refresh"),
    # API حسابات المستخدمين (تسجيل، تسجيل دخول، إلخ) عبرالتطبيق
    path("api/accounts/", include("accounts.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

    from accounts.password_reset_views import (
    PasswordResetRequestView,
    PasswordResetVerifyView,
    PasswordResetConfirmView,
)

urlpatterns += [
    path("api/auth/password-reset/request/", PasswordResetRequestView.as_view(), name="password_reset_request"),
    path("api/auth/password-reset/verify/", PasswordResetVerifyView.as_view(), name="password_reset_verify"),
    path("api/auth/password-reset/confirm/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
]