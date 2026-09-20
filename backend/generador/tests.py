import json
import hashlib
from datetime import timedelta
from io import StringIO
import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient
from diagrams.models import Attribute, Diagram, Project, Relation, UMLClass
from diagrams.views import create_diagram_version
from .models import GeneracionBackend
from .services.ir_builder import IRBuilder, normalizar
from .services.validator import ValidadorIR
from .exceptions import ValidacionIRError


@override_settings(ALLOWED_HOSTS=["testserver"], GENERADOR_RATE="1000/min")
class GeneratorTests(TestCase):
    def setUp(self):
        cache.clear()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        override = override_settings(GENERADOR_TMP_DIR=Path(self.temp.name))
        override.enable(); self.addCleanup(override.disable)
        self.owner = User.objects.create_user(username="generator-owner")
        self.other = User.objects.create_user(username="generator-other")
        self.project = Project.objects.create(name="Ventas", owner=self.owner)
        self.diagram = Diagram.objects.create(project=self.project, name="Ventas local")
        self.clase = UMLClass.objects.create(diagram=self.diagram, name="Cliente_VIP")
        self.pk = Attribute.objects.create(uml_class=self.clase, name="id", data_type="Long", es_pk=True)
        self.client = APIClient(); self.client.force_authenticate(self.owner)

    def post(self, **extra):
        return self.client.post("/api/generador/generar-backend/", {"diagrama_id": self.diagram.pk, **extra}, format="json")

    def test_normalization_and_simple_ir(self):
        self.assertEqual({normalizar(n, True) for n in ("cliente vip", "Cliente_VIP", "ClienteVip")}, {"ClienteVip"})
        ir = IRBuilder(self.diagram).construir(); ValidadorIR(ir).validar()
        self.assertEqual(ir["entidades"][0]["atributos"][0]["tipo"], "Long")
        self.assertFalse(ir["entidades"][0]["atributos"][0]["nullable"])

    def test_imported_java_name_is_rejected_or_corrected(self):
        self.clase.name = 'Objects'
        self.clase.save()
        with self.assertRaises(ValidacionIRError):
            ValidadorIR(IRBuilder(self.diagram).construir()).validar()
        builder = IRBuilder(self.diagram, autocorregir=True)
        ir = builder.construir()
        ValidadorIR(ir).validar()
        self.assertEqual(ir['entidades'][0]['nombre'], 'ObjectsModelo')

    def test_sql_text_keeps_long_text_storage(self):
        Attribute.objects.create(uml_class=self.clase, name='descripcion', data_type=' TEXT ')
        ir = IRBuilder(self.diagram).construir()
        field = next(a for a in ir['entidades'][0]['atributos'] if a['nombre'] == 'descripcion')
        self.assertTrue(field['texto_largo'])
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        with ZipFile(Path(self.temp.name) / GeneracionBackend.objects.get().ruta_archivo) as archive:
            entity = archive.read('src/main/java/com/generado/ventaslocal/entidades/ClienteVip.java').decode()
            self.assertIn('columnDefinition = "text"', entity)

    def test_entities_scope_api_and_invalid_scope(self):
        self.assertEqual(self.post(alcance="desconocido").status_code, 400)
        response = self.post(alcance="entidades")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["estado"], "ENTIDADES_GENERADAS")
        self.assertFalse(response.data["backend_ejecutable"])
        self.assertEqual(response.data["compilacion"], "PENDIENTE")
        self.assertEqual(response.data["metricas"]["archivos_java"], 2)

    def test_one_to_many_ir(self):
        pedido = UMLClass.objects.create(diagram=self.diagram, name="Pedido")
        Attribute.objects.create(uml_class=pedido, name="id", data_type="Long", es_pk=True)
        Relation.objects.create(diagram=self.diagram, source=self.clase, target=pedido, multiplicity_target="*", nombre_campo_origen="pedidos")
        ir = IRBuilder(self.diagram).construir(); ValidadorIR(ir).validar()
        self.assertEqual(ir["relaciones"][0]["tipo"], "OneToMany")
        self.assertEqual(ir["relaciones"][0]["nombre_campo_origen"], "pedidos")

    def test_input_auth_ownership_and_empty(self):
        self.assertEqual(self.client.post("/api/generador/generar-backend/", {}, format="json").status_code, 400)
        self.assertEqual(self.post(diagrama_id="").status_code, 400)
        self.assertEqual(self.post(diagrama_id=-1).status_code, 400)
        self.client.force_authenticate(self.other); self.assertEqual(self.post().status_code, 404)
        self.client.force_authenticate(None); self.assertEqual(self.post().status_code, 401)
        self.client.force_authenticate(self.owner)
        self.clase.delete(); self.assertEqual(self.post().status_code, 400)
        self.assertEqual(GeneracionBackend.objects.count(), 0)

    def test_invalid_type_missing_pk_and_limit(self):
        self.pk.data_type = "Unknown"; self.pk.save(); self.assertEqual(self.post().status_code, 400)
        self.pk.data_type = "Long"; self.pk.es_pk = False; self.pk.save(); self.assertEqual(self.post().status_code, 400)
        with override_settings(GENERADOR_MAX_ENTIDADES=0):
            self.assertEqual(self.post().status_code, 400)

    def test_complete_pk_reuses_id_and_keeps_diagram_unchanged(self):
        self.pk.es_pk = False; self.pk.save()
        response = self.post(completar_pk=True)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(len(response.data["avisos"]), 1)
        self.pk.refresh_from_db(); self.assertFalse(self.pk.es_pk)
        with ZipFile(Path(self.temp.name) / GeneracionBackend.objects.get().ruta_archivo) as archive:
            entity = json.loads(archive.read("ir.json"))["entidades"][0]
            self.assertEqual([a["nombre"] for a in entity["atributos"] if a["pk"]], ["id"])
            self.assertIn("@GeneratedValue", archive.read("src/main/java/com/generado/ventaslocal/entidades/ClienteVip.java").decode())

    def test_complete_pk_does_not_guess_foreign_key(self):
        self.pk.name = "idProfesor"; self.pk.es_pk = False; self.pk.save()
        builder = IRBuilder(self.diagram, completar_pk=True)
        ir = builder.construir(); ValidadorIR(ir).validar()
        attrs = ir["entidades"][0]["atributos"]
        self.assertEqual([a["nombre"] for a in attrs if a["pk"]], ["id"])
        self.assertFalse(next(a for a in attrs if a["nombre"] == "idProfesor")["pk"])

    def test_complete_pk_preserves_explicit_pk_and_avoids_name_collision(self):
        ir = IRBuilder(self.diagram, completar_pk=True).construir()
        self.assertEqual(len(ir["entidades"][0]["atributos"]), 1)
        self.pk.data_type = "Boolean"; self.pk.es_pk = False; self.pk.save()
        ir = IRBuilder(self.diagram, completar_pk=True).construir(); ValidadorIR(ir).validar()
        self.assertEqual([a["nombre"] for a in ir["entidades"][0]["atributos"] if a["pk"]], ["idGenerado"])

    def test_complete_pk_rejects_multiple_explicit_primary_keys(self):
        Attribute.objects.create(uml_class=self.clase, name="otroId", data_type="Long", es_pk=True)
        self.assertEqual(self.post(completar_pk=True).status_code, 400)

    def test_autocorrection_names_and_reference_identity(self):
        other = UMLClass.objects.create(diagram=self.diagram, name="Cliente VIP")
        reserved = UMLClass.objects.create(diagram=self.diagram, name="Entity")
        Attribute.objects.create(uml_class=reserved, name="class", data_type="String")
        Attribute.objects.create(uml_class=other, name="123 nombre", data_type="String")
        Relation.objects.create(diagram=self.diagram, source=self.clase, target=other, multiplicity_target="1..n")
        builder = IRBuilder(self.diagram, autocorregir=True)
        ir = builder.construir(); ValidadorIR(ir).validar()
        self.assertEqual([e["nombre"] for e in ir["entidades"]], ["ClienteVip", "ClienteVip2", "EntityModelo"])
        self.assertEqual(ir["relaciones"][0]["destino"], "ClienteVip2")
        self.assertEqual(ir["relaciones"][0]["tipo"], "OneToMany")
        self.assertTrue(builder.avisos)
        reserved.refresh_from_db(); self.assertEqual(reserved.name, "Entity")

    def test_autocorrection_duplicate_attributes_and_sql_types(self):
        Attribute.objects.create(uml_class=self.clase, name="nombre completo", data_type="VARCHAR(120)")
        Attribute.objects.create(uml_class=self.clase, name="nombre_completo", data_type="String")
        Attribute.objects.create(uml_class=self.clase, name="edad", data_type="SMALLINT", longitud=50)
        ir = IRBuilder(self.diagram, autocorregir=True).construir(); ValidadorIR(ir).validar()
        attrs = {a["nombre"]: a for a in ir["entidades"][0]["atributos"]}
        self.assertEqual(attrs["nombreCompleto"]["longitud"], 120)
        self.assertIn("nombreCompleto2", attrs)
        self.assertEqual(attrs["edad"]["tipo"], "Integer")
        self.assertIsNone(attrs["edad"]["longitud"])

    def test_autocorrection_relation_entity_and_dto_collisions(self):
        other = UMLClass.objects.create(diagram=self.diagram, name="Pedido")
        Attribute.objects.create(uml_class=self.clase, name="pedidosIds", data_type="String")
        Relation.objects.create(diagram=self.diagram, source=self.clase, target=other, multiplicity_target="n", nombre_campo_origen="pedidos")
        Relation.objects.create(diagram=self.diagram, source=self.clase, target=self.clase, nombre_campo_origen="id", nombre_campo_destino="id")
        ir = IRBuilder(self.diagram, autocorregir=True).construir(); ValidadorIR(ir).validar()
        self.assertEqual(ir["relaciones"][0]["nombre_campo_origen"], "pedidos2")
        rel = ir["relaciones"][1]
        self.assertNotEqual(rel["nombre_campo_origen"], rel["nombre_campo_destino"])

    def test_autocorrection_zip_records_original_and_report(self):
        self.pk.es_pk = False; self.pk.save()
        response = self.post(autocorregir=True)
        self.assertEqual(response.status_code, 201, response.data)
        with ZipFile(Path(self.temp.name) / GeneracionBackend.objects.get().ruta_archivo) as archive:
            report = json.loads(archive.read("docs/correcciones.json"))
            original = json.loads(archive.read("diagrama_original.json"))
            self.assertEqual(report["correcciones"], response.data["avisos"])
            self.assertFalse(report["diagrama_original_modificado"])
            self.assertFalse(original["classes"][0]["attributes"][0]["es_pk"])
            self.assertIn("methods", original["classes"][0])
            self.assertIn("width", original["classes"][0])
            manifest = json.loads(archive.read("docs/manifest.json"))["archivos"]
            self.assertIn("docs/correcciones.json", manifest)
            self.assertIn("diagrama_original.json", manifest)

    def test_autocorrection_never_invents_unknown_type_or_ambiguous_pk(self):
        self.pk.data_type = "[]"; self.pk.save()
        self.assertEqual(self.post(autocorregir=True).status_code, 400)
        self.pk.data_type = "Long"; self.pk.save()
        Attribute.objects.create(uml_class=self.clase, name="otroId", data_type="Long", es_pk=True)
        self.assertEqual(self.post(autocorregir=True).status_code, 400)
        self.assertFalse(GeneracionBackend.objects.exists())

    def test_zip_audit_and_protected_download(self):
        response = self.post(incluir_swagger=False, incluir_docker=False)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data["backend_ejecutable"])
        generation = GeneracionBackend.objects.get()
        with ZipFile(Path(self.temp.name) / generation.ruta_archivo) as archive:
            self.assertEqual(json.loads(archive.read("ir.json"))["entidades"][0]["nombre"], "ClienteVip")
            self.assertEqual(json.loads(archive.read("opciones.json")), {"incluir_swagger": False, "incluir_docker": False})
        path = f"/api/generador/descargar/{generation.ruta_archivo}/"
        self.client.force_authenticate(self.other); self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_authenticate(None); self.assertEqual(self.client.get(path).status_code, 401)
        self.client.force_authenticate(self.owner)
        download = self.client.get(path); self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Content-Type"], "application/zip")
        # Closing a test FileResponse fires request_finished and closes the PostgreSQL
        # connection inside TestCase's transaction; close the file itself here.
        with patch("django.http.response.signals.request_finished.send"):
            download.close()
        generation.refresh_from_db(); self.assertTrue(generation.descargado)
        (Path(self.temp.name) / generation.ruta_archivo).unlink()
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_internal_error_is_generic_and_removes_orphan(self):
        with patch("generador.views.GeneracionBackend.objects.create", side_effect=RuntimeError("secret internal path")):
            with self.assertLogs("generador", level="ERROR"):
                response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("secret", str(response.data))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_copy_restore_preserves_metadata(self):
        self.pk.es_unico = True; self.pk.nullable = False; self.pk.save()
        version = create_diagram_version(self.diagram, self.owner)
        copy = self.client.post(f"/api/diagrams/{self.diagram.pk}/save_as/", {"name": "Copia"}, format="json")
        self.assertEqual(copy.status_code, 201, copy.data)
        self.assertTrue(copy.data["classes"][0]["attributes"][0]["es_pk"])
        self.pk.es_pk = False; self.pk.save()
        response = self.client.post(f"/api/diagrams/{self.diagram.pk}/restore_version/", {"version_id": version.pk}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Attribute.objects.get(uml_class__diagram=self.diagram).es_pk)

    def test_duplicate_and_orphan_ir(self):
        ir = IRBuilder(self.diagram).construir()
        ir["entidades"].append(ir["entidades"][0])
        with self.assertRaises(ValidacionIRError): ValidadorIR(ir).validar()
        ir = IRBuilder(self.diagram).construir()
        ir["relaciones"].append({"origen": "Missing", "destino": "ClienteVip"})
        with self.assertRaises(ValidacionIRError): ValidadorIR(ir).validar()

    def test_download_rejects_resolved_path_outside_directory(self):
        # Even a corrupt database record must not allow backslashes to escape
        # the configured directory on Windows.
        name = "..\\outside.zip"
        GeneracionBackend.objects.create(diagrama=self.diagram, usuario=self.owner, ruta_archivo=name)
        response = self.client.get("/api/generador/descargar/..%5Coutside.zip/")
        self.assertEqual(response.status_code, 404)

    def test_preview_creates_no_generation(self):
        response = self.client.post("/api/generador/validar/", {"diagrama_id": self.diagram.pk}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn("ir", response.data)
        self.assertEqual(GeneracionBackend.objects.count(), 0)
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])

    def test_templates_and_options(self):
        response = self.post(incluir_swagger=False, incluir_docker=False)
        self.assertEqual(response.status_code, 201, response.data)
        generation = GeneracionBackend.objects.get()
        with ZipFile(Path(self.temp.name) / generation.ruta_archivo) as archive:
            names = archive.namelist()
            self.assertIn("pom.xml", names)
            self.assertIn("postman_collection.json", names)
            self.assertNotIn("docker-compose.yml", names)
            self.assertNotIn("springdoc", archive.read("pom.xml").decode())
            self.assertNotIn("springdoc", archive.read("src/main/resources/application.yml").decode())
            service = archive.read("src/main/java/com/generado/ventaslocal/servicios/ClienteVipService.java").decode()
            self.assertIn("mapper.update(dto, entidad)", service)
        self.assertFalse(any(p.is_dir() for p in Path(self.temp.name).iterdir()))

    def test_template_failure_cleans_project_and_zip(self):
        with patch("generador.services.code_generator.Environment.get_template", side_effect=RuntimeError("template internal detail")):
            with self.assertLogs("generador", level="WARNING"):
                response = self.post()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn("template internal detail", str(response.data))
        self.assertEqual(list(Path(self.temp.name).iterdir()), [])
        self.assertEqual(GeneracionBackend.objects.count(), 0)

    def test_reserved_entity_and_dto_collision_rejected(self):
        self.clase.name = "Entity"; self.clase.save()
        self.assertEqual(self.post().status_code, 400)

        self.clase.name = "Cliente"; self.clase.save()
        otro = UMLClass.objects.create(diagram=self.diagram, name="Pedido")
        Attribute.objects.create(uml_class=otro, name="id", data_type="Long", es_pk=True)
        Attribute.objects.create(uml_class=otro, name="clienteId", data_type="Long")
        Relation.objects.create(diagram=self.diagram, source=self.clase, target=otro, multiplicity_target="*", nombre_campo_origen="pedidos", nombre_campo_destino="cliente")
        self.assertEqual(self.post().status_code, 400)

    def test_delivery_manifest_digest_and_alias(self):
        response = self.client.post("/api/generar-backend/", {"diagrama_id": self.diagram.pk}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        record = GeneracionBackend.objects.get()
        path = Path(self.temp.name) / record.ruta_archivo
        self.assertEqual(response.data["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(response.data["tamano_bytes"], path.stat().st_size)
        self.assertTrue(record.metricas["ir_validado"])
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read("docs/manifest.json"))["archivos"]
            self.assertEqual(set(manifest), set(archive.namelist()) - {"docs/manifest.json"})
            for name, digest in manifest.items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(), digest)
        download = self.client.get(f"/api/generador/descargar/{record.ruta_archivo}/")
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        with patch("django.http.response.signals.request_finished.send"):
            download.close()

    def test_expired_or_corrupt_zip_is_not_delivered(self):
        self.assertEqual(self.post().status_code, 201)
        record = GeneracionBackend.objects.get()
        endpoint = f"/api/generador/descargar/{record.ruta_archivo}/"
        path = Path(self.temp.name) / record.ruta_archivo
        original = path.read_bytes()
        path.write_bytes(b"corrupt")
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        path.write_bytes(original)
        GeneracionBackend.objects.filter(pk=record.pk).update(fecha_creacion=timezone.now() - timedelta(days=2))
        self.assertEqual(self.client.get(endpoint).status_code, 404)
        self.assertTrue(self.client.get("/api/generador/historial/").data[0]["expirado"])

    @override_settings(GENERADOR_RATE="1/min")
    def test_generation_rate_limit(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(GeneracionBackend.objects.count(), 1)

    def test_cleanup_retains_active_files_and_history(self):
        self.post()
        expired = GeneracionBackend.objects.get()
        GeneracionBackend.objects.filter(pk=expired.pk).update(fecha_creacion=timezone.now() - timedelta(days=2))
        self.post()
        active = GeneracionBackend.objects.exclude(pk=expired.pk).get()
        outside = Path(self.temp.name) / "preservar.zip"
        outside.write_bytes(b"unrelated")
        call_command("limpiar_generaciones", dry_run=True, stdout=StringIO())
        self.assertTrue((Path(self.temp.name) / expired.ruta_archivo).exists())
        call_command("limpiar_generaciones", stdout=StringIO())
        self.assertFalse((Path(self.temp.name) / expired.ruta_archivo).exists())
        self.assertTrue((Path(self.temp.name) / active.ruta_archivo).exists())
        self.assertTrue(outside.exists())
        self.assertEqual(GeneracionBackend.objects.count(), 2)
