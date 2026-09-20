import logging
from time import perf_counter
from pathlib import Path
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from diagrams.models import Diagram
from diagrams.serializers import DiagramDetailSerializer
from diagrams.views import lock_diagram
from .exceptions import GeneradorBaseError, ValidacionIRError
from .models import GeneracionBackend
from .serializers import GenerarBackendRequestSerializer
from .services.ir_builder import IRBuilder
from .services.validator import ValidadorIR
from .services.code_generator import CodeGenerator
from .services.delivery import ruta_zip, sha256_archivo, expiracion
from .throttles import GenerationThrottle

logger = logging.getLogger("generador")


class GenerarBackendView(APIView):
    permission_classes = [IsAuthenticated]
    solo_ir = False
    throttle_classes = [GenerationThrottle]

    def post(self, request):
        inicio = perf_counter()
        serializer = GenerarBackendRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"error": "Datos de solicitud inválidos", "detalles": serializer.errors}, status=400)
        datos = serializer.validated_data
        nombre_archivo = None
        # Ownership is required for generation, even on shared diagrams.
        diagrama = get_object_or_404(Diagram, pk=datos["diagrama_id"], project__owner=request.user)
        try:
            with transaction.atomic():
                lock_diagram(diagrama.pk)
                if diagrama.classes.count() > settings.GENERADOR_MAX_ENTIDADES:
                    raise ValidacionIRError(f"Máximo {settings.GENERADOR_MAX_ENTIDADES} entidades por generación.")
                diagrama = Diagram.objects.select_related("project").prefetch_related("classes__attributes", "classes__methods", "relations").get(pk=diagrama.pk)
                builder = IRBuilder(diagrama, completar_pk=datos["completar_pk"], autocorregir=datos["autocorregir"])
                ir = builder.construir()
                ValidadorIR(ir).validar()
                if self.solo_ir:
                    return Response({"ir": ir, "avisos": builder.avisos})
                original = DiagramDetailSerializer(diagrama, context={"request": request}).data
                generator = CodeGenerator(ir, incluir_swagger=datos["incluir_swagger"], incluir_docker=datos["incluir_docker"], alcance=datos["alcance"],
                    correcciones=builder.avisos, modelo_original=original)
                nombre_archivo = generator.generar()
                ruta = ruta_zip(nombre_archivo)
                with ruta.open("rb") as archivo:
                    digest = sha256_archivo(archivo)
                metricas = {**generator.metricas, "duracion_total_ms": round((perf_counter() - inicio) * 1000, 2)}
                generacion = GeneracionBackend.objects.create(diagrama=diagrama, usuario=request.user,
                    ruta_archivo=nombre_archivo, entidades=[e["nombre"] for e in ir["entidades"]],
                    sha256=digest, tamano_bytes=ruta.stat().st_size, metricas=metricas)
        except GeneradorBaseError as exc:
            logger.warning("Error esperado en diagrama %s: %s", diagrama.pk, exc, exc_info=exc.codigo_http >= 500)
            return Response({"error": str(exc)}, status=exc.codigo_http)
        except Exception:
            if nombre_archivo:
                try:
                    (Path(settings.GENERADOR_TMP_DIR) / nombre_archivo).unlink(missing_ok=True)
                except OSError:
                    logger.exception("No se pudo limpiar el ZIP de una generación fallida")
            logger.exception("Error inesperado generando diagrama %s", diagrama.pk)
            return Response({"error": "Ocurrió un error inesperado al preparar el backend."}, status=500)
        return Response({"mensaje": "Proyecto Spring Boot generado exitosamente",
            "avisos": builder.avisos,
            "estado": "ENTIDADES_GENERADAS" if datos["alcance"] == "entidades" else "SPRING_BOOT_GENERADO",
            "backend_ejecutable": datos["alcance"] == "completo", "compilacion": "PENDIENTE", "metricas": metricas,
            "sha256": generacion.sha256, "tamano_bytes": generacion.tamano_bytes, "expira_en": expiracion(generacion),
            "generacion_id": str(generacion.pk), "zip_url": request.build_absolute_uri(
                f"/api/generador/descargar/{nombre_archivo}/"), "entidades_generadas": generacion.entidades}, status=201)


class ValidarBackendView(GenerarBackendView):
    solo_ir = True


class DescargarBackendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, nombre_archivo):
        generacion = get_object_or_404(GeneracionBackend, ruta_archivo=nombre_archivo,
            usuario=request.user, diagrama__project__owner=request.user)
        if timezone.now() >= expiracion(generacion):
            raise Http404("El archivo ya no existe o expiró.")
        try:
            ruta = ruta_zip(nombre_archivo)
        except ValueError:
            raise Http404("El archivo ya no existe o expiró.") from None
        if not ruta.is_file():
            raise Http404("El archivo ya no existe o expiró.")
        try:
            archivo = ruta.open("rb")
        except OSError:
            raise Http404("El archivo ya no existe o expiró.") from None
        try:
            if generacion.sha256 and sha256_archivo(archivo) != generacion.sha256:
                archivo.close()
                raise Http404("El archivo no está disponible; genera el backend nuevamente.")
            archivo.seek(0)
            GeneracionBackend.objects.filter(pk=generacion.pk).update(descargado=True)
        except Exception:
            archivo.close()
            raise
        response = FileResponse(archivo, as_attachment=True, filename=nombre_archivo, content_type="application/zip")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class HistorialBackendView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        items = GeneracionBackend.objects.filter(usuario=request.user, diagrama__project__owner=request.user)[:50]
        return Response([{"id": str(g.pk), "diagrama_id": g.diagrama_id,
            "fecha_creacion": g.fecha_creacion, "descargado": g.descargado,
            "expira_en": expiracion(g), "expirado": timezone.now() >= expiracion(g),
            "sha256": g.sha256, "tamano_bytes": g.tamano_bytes, "metricas": g.metricas,
            "entidades_generadas": g.entidades, "zip_url": request.build_absolute_uri(
                f"/api/generador/descargar/{g.ruta_archivo}/")} for g in items])
