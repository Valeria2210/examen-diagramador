"""Verify the running Django generation/download pipeline with disposable data.

Run via manage.py shell. Uses an existing owner's token without printing it.
"""
import io
import json
import uuid
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile
from django.conf import settings
from rest_framework.authtoken.models import Token
from diagrams.models import Project, Diagram, UMLClass, Attribute, Relation
from generador.models import GeneracionBackend


def run():
    token = Token.objects.filter(user__projects__isnull=False).distinct().first()
    if token is None:
        raise RuntimeError("Inicia sesión como propietario antes de ejecutar la prueba HTTP.")
    project = Project.objects.filter(owner=token.user).first()
    diagram = Diagram.objects.create(project=project, name="Prueba generador " + uuid.uuid4().hex[:8])
    filename = None
    try:
        cliente = UMLClass.objects.create(diagram=diagram, name="Cliente")
        pedido = UMLClass.objects.create(diagram=diagram, name="Pedido")
        for clase in (cliente, pedido):
            Attribute.objects.create(uml_class=clase, name="codigo", data_type="Long", es_pk=True)
        Relation.objects.create(diagram=diagram, source=cliente, target=pedido, multiplicity_target="*", nombre_campo_origen="pedidos", nombre_campo_destino="cliente")
        req = Request("http://127.0.0.1:8000/api/generador/generar-backend/", method="POST",
            data=json.dumps({"diagrama_id": diagram.pk}).encode(),
            headers={"Authorization": "Token " + token.key, "Content-Type": "application/json"})
        with urlopen(req, timeout=60) as response:
            assert response.status == 201
            data = json.load(response)
        assert data["estado"] == "SPRING_BOOT_GENERADO" and data["backend_ejecutable"]
        generation = GeneracionBackend.objects.get(pk=data["generacion_id"])
        filename = generation.ruta_archivo
        with urlopen(Request(data["zip_url"], headers={"Authorization": "Token " + token.key}), timeout=30) as response:
            assert response.status == 200 and response.headers["Content-Type"] == "application/zip"
            payload = response.read()
        with ZipFile(io.BytesIO(payload)) as archive:
            assert "pom.xml" in archive.namelist()
            assert "postman_collection.json" in archive.namelist()
        generation.refresh_from_db()
        assert generation.descargado
        print("PASS: live Django POST 201, audit row, authenticated ZIP GET 200, Maven project and download flag.")
    finally:
        # Collect filenames even if the HTTP request failed after creating a row.
        filenames = list(diagram.generaciones.values_list("ruta_archivo", flat=True))
        diagram.delete()
        base = Path(settings.GENERADOR_TMP_DIR).resolve()
        for name in set(filenames + ([filename] if filename else [])):
            path = (base / name).resolve()
            if path.parent == base and path.suffix == ".zip":
                path.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
