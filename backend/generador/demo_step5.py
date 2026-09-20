"""Generate a separate full CRUD example; preserves previous demo artifacts."""
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.demo_step3 import demo_ir
from generador.services.code_generator import CodeGenerator

root = settings.BASE_DIR / "artifacts" / "step5-relations"
if root.exists():
    raise RuntimeError("El ejemplo ya existe; usa otra carpeta para conservarlo.")
generator = CodeGenerator(demo_ir())
name = generator.generar()
with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
    archive.extractall(root)
print(root)
print(generator.metricas)
