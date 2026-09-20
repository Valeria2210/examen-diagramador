"""Generate final phase-2 delivery without altering previous demo projects."""
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.demo_step3 import demo_ir
from generador.services.code_generator import CodeGenerator

root = settings.BASE_DIR / "artifacts" / "step67-delivery"
if root.exists():
    raise RuntimeError("El ejemplo final ya existe; conserva su verificación.")
generator = CodeGenerator(demo_ir())
name = generator.generar()
with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
    archive.extractall(root)
print(root)
print(generator.metricas)
