import uuid
from django.conf import settings
from django.db import models


class GeneracionBackend(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    diagrama = models.ForeignKey("diagrams.Diagram", on_delete=models.CASCADE, related_name="generaciones")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    ruta_archivo = models.CharField(max_length=500)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    descargado = models.BooleanField(default=False)
    entidades = models.JSONField(default=list)
    sha256 = models.CharField(max_length=64, blank=True)
    tamano_bytes = models.PositiveBigIntegerField(default=0)
    metricas = models.JSONField(default=dict)

    class Meta:
        ordering = ["-fecha_creacion"]
