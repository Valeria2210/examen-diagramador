import json
import tempfile
from pathlib import Path
from zipfile import ZipFile
from django.test import SimpleTestCase, override_settings
from .demo_step3 import demo_ir
from .services.code_generator import CodeGenerator


class Step4Tests(SimpleTestCase):
    def generate(self, scope):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        with override_settings(GENERADOR_TMP_DIR=Path(temp.name)):
            generator = CodeGenerator(demo_ir(), alcance=scope)
            name = generator.generar()
        archive = ZipFile(Path(temp.name) / name)
        self.addCleanup(archive.close)
        return archive, generator

    def test_entities_only_preserves_jpa_types_and_relationships(self):
        archive, generator = self.generate("entidades")
        java = [n for n in archive.namelist() if n.endswith(".java")]
        self.assertEqual(len(java), 5)
        self.assertFalse(any("Repository" in n or "Controller" in n for n in java))
        self.assertNotIn("docs/openapi.json", archive.namelist())
        self.assertNotIn("start-backend.ps1", archive.namelist())
        cliente = archive.read(next(n for n in java if n.endswith("Cliente.java"))).decode()
        self.assertIn("@Id", cliente)
        self.assertIn("GenerationType.IDENTITY", cliente)
        self.assertIn("List<Pedido>", cliente)
        perfil = archive.read(next(n for n in java if n.endswith("Perfil.java"))).decode()
        self.assertIn("GenerationType.UUID", perfil)
        self.assertIn("mvn compile", archive.read("README.md").decode())
        self.assertEqual(generator.metricas["compilacion"], "PENDIENTE")
        self.assertEqual(json.loads(archive.read("docs/metricas.json")), generator.metricas)

    def test_offline_contract_matches_dto_fields_and_pk_types(self):
        archive, generator = self.generate("completo")
        spec = json.loads(archive.read("docs/openapi.json"))
        collection = json.loads(archive.read("docs/postman_collection.json"))
        self.assertEqual(len(collection["item"]), 5)
        entity_folders = [folder for folder in collection["item"] if folder["name"] != "Auth"]
        self.assertTrue(all(len(folder["item"]) == 5 for folder in entity_folders))
        self.assertEqual(len(next(folder for folder in collection["item"] if folder["name"] == "Auth")["item"]), 4)
        self.assertEqual(spec["paths"]["/api/perfils/{id}"]["get"]["parameters"][0]["schema"]["format"], "uuid")
        self.assertEqual(spec["paths"]["/api/etiquetas/{id}"]["get"]["parameters"][0]["schema"]["type"], "string")
        for folder in entity_folders:
            props = spec["components"]["schemas"][folder["name"] + "DTO"]["properties"]
            dto = archive.read(next(n for n in archive.namelist() if n.endswith("/" + folder["name"] + "DTO.java"))).decode()
            for field in props:
                self.assertIn(" " + field + ";", dto)
            post = next(item for item in folder["item"] if item["request"]["method"] == "POST")
            body = json.loads(post["request"]["body"]["raw"])
            self.assertEqual(set(body), {n for n, f in props.items() if not f.get("readOnly") and not f.get("x-generated-id")})
            self.assertIn("event", post)
            if folder["name"] == "Pedido":
                self.assertEqual(body["fecha"], "2026-01-15")
                self.assertEqual(body["creado"], "2026-01-15T10:30:00")
                self.assertIsNone(body["clienteId"])
        self.assertEqual(generator.metricas["endpoints_documentados"], 20)
        self.assertEqual(spec["security"], [{"BearerAuth": []}])
        self.assertEqual(spec["paths"]["/api/auth/login"]["post"]["security"], [])
        auth_login = next(item for folder in collection["item"] if folder["name"] == "Auth"
            for item in folder["item"] if item["name"] == "Iniciar sesión")
        self.assertIn("access_token", "\n".join(auth_login["event"][0]["script"]["exec"]))
        self.assertEqual(collection["auth"]["type"], "bearer")
        self.assertIn("src/main/java/com/generado/ventasdemo/seguridad/BearerTokenFilter.java", archive.namelist())
        self.assertIn("src/main/java/com/generado/ventasdemo/seguridad/SecurityConfig.java", archive.namelist())
        errors = archive.read("src/main/java/com/generado/ventasdemo/excepciones/GlobalExceptionHandler.java").decode()
        self.assertIn("AccessDeniedException", errors)
        self.assertIn('error(403, "ACCESS_DENIED"', errors)
        self.assertIn("src/main/resources/db/migration/V1__initial_schema.sql", archive.namelist())
        self.assertIn("Dockerfile", archive.namelist())
        self.assertIn(".env.example", archive.namelist())
        self.assertIn("start-backend.ps1", archive.namelist())
        script = archive.read("start-backend.ps1").decode()
        self.assertIn("docker compose --env-file .env up -d --build --wait", script)
        self.assertIn("{{.ServerVersion}}", script)
        self.assertNotIn(".api-key.local", archive.read(".gitignore").decode())

    def test_documentation_is_independent_of_swagger(self):
        with tempfile.TemporaryDirectory() as temp, override_settings(GENERADOR_TMP_DIR=Path(temp)):
            name = CodeGenerator(demo_ir(), incluir_swagger=False).generar()
            with ZipFile(Path(temp) / name) as archive:
                self.assertIn("docs/openapi.json", archive.namelist())
                self.assertNotIn("springdoc", archive.read("pom.xml").decode())
