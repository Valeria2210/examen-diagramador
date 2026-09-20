"""Explicitly refresh final generated sources, preserving QA evidence files."""
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.demo_step3 import demo_ir
from generador.services.code_generator import CodeGenerator

root = settings.BASE_DIR / "artifacts" / "step67-delivery"
if not (root / "ir.json").is_file():
    raise RuntimeError("Genera primero demo_delivery.py.")
generator = CodeGenerator(demo_ir())
name = generator.generar()
with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
    archive.extractall(root)
print(generator.metricas)
