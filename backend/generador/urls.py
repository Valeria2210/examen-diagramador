from django.urls import path
from .views import GenerarBackendView, ValidarBackendView, DescargarBackendView, HistorialBackendView

urlpatterns = [
    path("validar/", ValidarBackendView.as_view(), name="validar-backend"),
    path("generar-backend/", GenerarBackendView.as_view(), name="generar-backend"),
    path("descargar/<str:nombre_archivo>/", DescargarBackendView.as_view(), name="descargar-backend"),
    path("historial/", HistorialBackendView.as_view(), name="historial-backend"),
]
