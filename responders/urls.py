from __future__ import annotations

from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import (
    OnlineRespondersAPI,
    UpdateMyLocationAPI,
    show_all_responders,  # ✅ صفحة عرض جميع المستجيبين (HTML)
)

app_name = "responders"

urlpatterns = [
    # ==========================
    # JWT
    # ==========================
    path("auth/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),

    # ==========================
    # Pages (HTML)
    # ==========================
    path("show-all/", show_all_responders, name="show_all_responders"),

    # ==========================
    # Responder tracking APIs
    # ==========================
    path("me/location/", UpdateMyLocationAPI.as_view(), name="update_my_location"),
    path("online/", OnlineRespondersAPI.as_view(), name="online_responders"),
]
