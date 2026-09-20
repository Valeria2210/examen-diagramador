"""Explicitly refresh only the reproducible step5 demo, preserving QA test files."""
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.services.code_generator import CodeGenerator
from generador.demo_step3 import demo_ir
root = settings.BASE_DIR / "artifacts" / "step5-relations"
if not (root / "ir.json").is_file():
    raise RuntimeError("Genera primero el ejemplo mediante demo_step5.py.")
generator = CodeGenerator(demo_ir())
name = generator.generar()
with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
    archive.extractall(root)
print(generator.metricas)
