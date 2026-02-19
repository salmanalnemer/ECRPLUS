from django.contrib import admin
from django.urls import path, include 

urlpatterns = [
    # Admin panel
    path("admin/", admin.site.urls),
    # API حسابات المستخدمين (تسجيل، تسجيل دخول، إلخ)
    path("accounts/", include("accounts.urls")),
    # API بلاغات تطبيق CAD (الويب)
    path("cad/", include("cad_reports.urls", namespace="cad_reports")),
    # API المستجيبين (تتبع المواقع، إلخ)
    path("responders/", include("responders.urls")),


    # API بلاغات تطبيق ECR (الجوال)
    path("api/ecr/", include("ecr_reports.urls", namespace="ecr_reports")),

    # API تتبع المستجيبين
    path("api/responders/", include("responders.urls", namespace="responders")),
]
