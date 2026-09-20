from django.contrib import admin
from django.urls import path, include
from generador.views import GenerarBackendView
from .health import health

urlpatterns = [
    path('api/health/', health, name='health'),
    path("admin/", admin.site.urls),
    path("api/", include("diagrams.urls")),
    path("api/generador/", include("generador.urls")),
    path("api/generar-backend/", GenerarBackendView.as_view(), name="generar-backend-directo"),
]
