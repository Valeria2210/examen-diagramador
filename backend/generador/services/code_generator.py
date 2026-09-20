import copy
import json
import hashlib
import tempfile
import uuid
from time import perf_counter
from .openapi_builder import OpenAPIBuilder
from .postman_converter import PostmanConverter
from pathlib import Path
from django.conf import settings
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from generador.exceptions import ErrorGeneracionCodigoError
from .file_writer import FileWriter
from .zip_packager import ZipPackager
from .validator import ValidadorIR
from .relation_helpers import nombre_tabla_intermedia


class CodeGenerator:
    def __init__(self, ir, incluir_swagger=True, incluir_docker=True, alcance="completo", correcciones=None, modelo_original=None):
        if alcance not in ("entidades", "completo"):
            raise ValueError("Alcance inválido")
        self.alcance = alcance
        self.metricas = {}
        self.ir = copy.deepcopy(ir)
        self.correcciones = list(correcciones or [])
        self.modelo_original = modelo_original
        self.opciones = {"incluir_swagger": incluir_swagger, "incluir_docker": incluir_docker}
        self.env = Environment(loader=FileSystemLoader(Path(__file__).parent.parent / "templates_springboot"),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)

    def _preparar(self):
        sql_types = {"String": "VARCHAR", "Integer": "INTEGER", "Long": "BIGINT", "BigDecimal": "NUMERIC(38,2)",
            "Double": "DOUBLE PRECISION", "Float": "REAL", "Boolean": "BOOLEAN", "UUID": "UUID",
            "LocalDate": "DATE", "LocalDateTime": "TIMESTAMP"}
        mapa = {e["nombre"]: e for e in self.ir["entidades"]}
        for e in mapa.values():
            e["pk"] = next(a for a in e["atributos"] if a["pk"])
            e["ruta"] = e["nombre"].lower() + "s"
            e["tabla"] = "uml_" + e["nombre"].lower()
            e["relaciones"] = []
            for a in e["atributos"]:
                a["getter"] = a["nombre"][:1].upper() + a["nombre"][1:]
                a["columna"] = "f_" + a["nombre"].lower()
                a["sql_tipo"] = ("TEXT" if a.get("texto_largo") else
                    (f"VARCHAR({a['longitud']})" if a["tipo"] == "String" and a.get("longitud") else
                    ("VARCHAR(255)" if a["tipo"] == "String" else sql_types[a["tipo"]])))
        for index, rel in enumerate(self.ir["relaciones"]):
            for rol in ("origen", "destino"):
                otro = "destino" if rol == "origen" else "origen"
                e = mapa[rel[rol]]
                tipo = rel["tipo"] if rol == "origen" else {"OneToMany": "ManyToOne", "ManyToOne": "OneToMany", "OneToOne": "OneToOne", "ManyToMany": "ManyToMany"}[rel["tipo"]]
                campo = rel[f"nombre_campo_{rol}"]
                many = tipo in ("OneToMany", "ManyToMany")
                e["relaciones"].append({"tipo": tipo, "campo": campo, "getter": campo[:1].upper() + campo[1:],
                    "otra_clase": rel[otro], "otro_campo": rel[f"nombre_campo_{otro}"],
                    "owner": tipo == "ManyToOne" or (tipo in ("OneToOne", "ManyToMany") and rol == "origen"),
                    "many": many, "dto_campo": campo + ("Ids" if many else "Id"),
                    "required": rel.get(f"requerida_{rol}", False),
                    "semantica": rel.get("semantica", "ASSOCIATION"),
                    "composition": rel.get("semantica") == "COMPOSITION" and rol == "origen",
                    "id_tipo": mapa[rel[otro]]["pk"]["tipo"], "id_getter": mapa[rel[otro]]["pk"]["getter"],
                    "id_sql_tipo": mapa[rel[otro]]["pk"]["sql_tipo"],
                    "otra_tabla": mapa[rel[otro]]["tabla"], "otra_pk_columna": mapa[rel[otro]]["pk"]["columna"],
                    "join": f"r_{index}_{campo.lower()}", "join_table": nombre_tabla_intermedia(rel),
                    "repo_var": f"relRepo{index}{rol}", "repo_tipo": rel[otro] + "Repository"})

    def generar(self):
        inicio = perf_counter()
        ValidadorIR(self.ir).validar()
        base = Path(settings.GENERADOR_TMP_DIR).resolve()
        ruta = base / f"{uuid.uuid4()}.zip"
        try:
            self._preparar()
            base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="proyecto_", dir=base) as root:
                writer = FileWriter(root)
                paquete = self.ir["proyecto"]["paquete_base"]
                java = "src/main/java/" + paquete.replace(".", "/")
                ctx = {"paquete_base": paquete, "proyecto": self.ir["proyecto"], **self.opciones, "solo_entidades": self.alcance == "entidades"}
                for folder in ("entidades", "repositorios", "dto", "mappers", "servicios", "controladores", "excepciones", "config", "seguridad"):
                    (Path(root) / java / folder).mkdir(parents=True, exist_ok=True)
                def render(template, destination, **extra):
                    writer.escribir(destination, self.env.get_template(template + ".j2").render(**ctx, **extra))
                render("pom.xml", "pom.xml")
                render("application.yml", "src/main/resources/application.yml")
                render("Application.java", java + "/Application.java")
                if self.alcance == "completo":
                    for name in ("UserRole", "AppUser", "AuthToken", "AppUserRepository", "AuthTokenRepository",
                            "AuthModels", "TokenService", "BearerTokenFilter", "AuthController", "SecurityConfig"):
                        render(name + ".java", f"{java}/seguridad/{name}.java")
                    if self.opciones["incluir_swagger"]:
                        render("OpenApiConfig.java", java + "/config/OpenApiConfig.java")
                render("README.md", "README.md", entidades=self.ir["entidades"])
                if self.alcance == "completo":
                    render("start-backend.ps1", "start-backend.ps1")
                for name in (() if self.alcance == "entidades" else ("GlobalExceptionHandler", "ResourceNotFoundException")):
                    render(name + ".java", f"{java}/excepciones/{name}.java")
                if self.opciones["incluir_docker"]:
                    render("docker-compose.yml", "docker-compose.yml")
                    render("Dockerfile", "Dockerfile")
                    render("env.example", ".env.example")
                for e in self.ir["entidades"]:
                    for template, folder, suffix in (("Entity", "entidades", ""), ("Repository", "repositorios", "Repository"),
                        ("DTO", "dto", "DTO"), ("Mapper", "mappers", "Mapper"), ("Service", "servicios", "Service"), ("Controller", "controladores", "Controller")):
                        if self.alcance == "entidades" and template != "Entity":
                            continue
                        render(template + ".java", f"{java}/{folder}/{e['nombre']}{suffix}.java", entidad=e)
                if self.alcance == "completo":
                    render("V1__initial_schema.sql", "src/main/resources/db/migration/V1__initial_schema.sql",
                        entidades=self.ir["entidades"])
                writer.escribir("ir.json", json.dumps(self.ir, ensure_ascii=False, indent=2))
                writer.escribir("docs/correcciones.json", json.dumps({"correcciones": self.correcciones,
                    "diagrama_original_modificado": False}, ensure_ascii=False, indent=2))
                if self.modelo_original is not None:
                    writer.escribir("diagrama_original.json", json.dumps(self.modelo_original, ensure_ascii=False, indent=2))
                writer.escribir("opciones.json", json.dumps(self.opciones, indent=2))
                writer.escribir(".gitignore", "target/\n.env\n")
                if self.alcance == "completo":
                    spec = OpenAPIBuilder(self.ir).construir()
                    collection = PostmanConverter(spec, self.ir["proyecto"]["nombre"]).convertir()
                    writer.escribir("docs/openapi.json", json.dumps(spec, indent=2, ensure_ascii=False))
                    writer.escribir("docs/postman_collection.json", json.dumps(collection, indent=2, ensure_ascii=False))
                    # Keep the existing download path compatible.
                    writer.escribir("postman_collection.json", json.dumps(collection, indent=2, ensure_ascii=False))
                archivos = list(Path(root).rglob("*.java"))
                elapsed = perf_counter() - inicio
                self.metricas = {"alcance": self.alcance, "entidades": len(self.ir["entidades"]),
                    "relaciones": len(self.ir["relaciones"]),
                    "relaciones_por_tipo": {tipo: sum(r["tipo"] == tipo for r in self.ir["relaciones"])
                        for tipo in ("OneToMany", "ManyToOne", "OneToOne", "ManyToMany")},
                    "archivos_java": len(archivos),
                    "lineas_java": sum(len(p.read_text(encoding="utf-8").splitlines()) for p in archivos),
                    "duracion_generacion_ms": round(elapsed * 1000, 2),
                    "entidades_por_segundo": round(len(self.ir["entidades"]) / max(elapsed, 0.000001), 2),
                    "ir_validado": True, "compilacion": "PENDIENTE",
                    "endpoints_documentados": len(self.ir["entidades"]) * 5 if self.alcance == "completo" else 0}
                writer.escribir("docs/metricas.json", json.dumps(self.metricas, indent=2))
                manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(Path(root).rglob("*")) if p.is_file()}
                writer.escribir("docs/manifest.json", json.dumps({"algoritmo": "SHA-256", "archivos": manifest}, indent=2))
                return ZipPackager(root).empaquetar(ruta)
        except Exception as exc:
            ruta.unlink(missing_ok=True)
            raise ErrorGeneracionCodigoError("No se pudo generar el proyecto Spring Boot.") from exc

