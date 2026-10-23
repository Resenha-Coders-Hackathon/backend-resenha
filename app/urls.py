from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAdminUser

from core.authenticate import CustomAuthentication

# Documentation accepts either the staff JWT or the Django admin session.
docs_permissions = {
    "authentication_classes": [CustomAuthentication, SessionAuthentication],
    "permission_classes": [IsAdminUser],
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/docs/urls/",
        SpectacularSwaggerView.as_view(url_name="schema", **docs_permissions),
        name="swagger-ui",
    ),
    path(
        "api/docs/schema/",
        SpectacularAPIView.as_view(**docs_permissions),
        name="schema",
    ),
    path("api/v1/", include("core.urls", namespace="v1")),
]
