import hashlib
import json
import tempfile
import uuid
from pathlib import Path

from django.conf import settings
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from generador.exceptions import ErrorGeneracionCodigoError
from .file_writer import FileWriter
from .zip_packager import ZipPackager


class FlutterGenerator:
    def __init__(self, ir, api_base_url, incluir_ia_local=True, backend_generacion_id=None):
        self.ir = ir
        self.api_base_url = api_base_url.rstrip("/")
        self.incluir_ia_local = incluir_ia_local
        self.backend_generacion_id = str(backend_generacion_id or "")
        self.metricas = {}
        self.env = Environment(
            loader=FileSystemLoader(Path(__file__).parent.parent / "templates_flutter"),
            undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True,
        )

    def generar(self):
        base = Path(settings.GENERADOR_TMP_DIR).resolve()
        destination = base / f"{uuid.uuid4()}.zip"
        try:
            base.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix="flutter_", dir=base) as root:
                writer = FileWriter(root)
                context = {
                    "proyecto": self.ir["proyecto"], "entidades": self.ir["entidades"],
                    "api_base_url": self.api_base_url, "incluir_ia_local": self.incluir_ia_local,
                    "backend_generacion_id": self.backend_generacion_id,
                }
                def render(name, target):
                    writer.escribir(target, self.env.get_template(name + ".j2").render(**context))

                for name, target in (
                    ("pubspec.yaml", "pubspec.yaml"), ("analysis_options.yaml", "analysis_options.yaml"),
                    ("main.dart", "lib/main.dart"), ("app_config.dart", "lib/app_config.dart"),
                    ("entity_definition.dart", "lib/models/entity_definition.dart"),
                    ("api_client.dart", "lib/services/api_client.dart"),
                    ("login_screen.dart", "lib/screens/login_screen.dart"),
                    ("home_screen.dart", "lib/screens/home_screen.dart"),
                    ("entity_screen.dart", "lib/screens/entity_screen.dart"),
                    ("local_ai_screen.dart", "lib/screens/local_ai_screen.dart"),
                    ("bootstrap.ps1", "bootstrap.ps1"), ("README.md", "README.md"),
                ):
                    render(name, target)
                writer.escribir("config.json.example", json.dumps({"API_BASE_URL": self.api_base_url}, indent=2))
                writer.escribir(".gitignore", ".dart_tool/\n.buildlog\n/build/\nconfig.json\nandroid/.gradle/\nios/Pods/\n")
                writer.escribir("docs/backend_ir.json", json.dumps(self.ir, ensure_ascii=False, indent=2))
                files = [item for item in Path(root).rglob("*") if item.is_file()]
                self.metricas = {
                    "producto": "flutter", "entidades": len(self.ir["entidades"]),
                    "archivos_flutter": len(files), "ia_local": self.incluir_ia_local,
                    "backend_generacion_id": self.backend_generacion_id,
                    "ir_validado": True, "compilacion": "PENDIENTE",
                }
                writer.escribir("docs/metricas.json", json.dumps(self.metricas, indent=2))
                manifest = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(Path(root).rglob("*")) if p.is_file()}
                writer.escribir("docs/manifest.json", json.dumps({"algoritmo": "SHA-256", "archivos": manifest}, indent=2))
                return ZipPackager(root).empaquetar(destination)
        except Exception as exc:
            destination.unlink(missing_ok=True)
            raise ErrorGeneracionCodigoError("No se pudo generar el proyecto Flutter.") from exc
