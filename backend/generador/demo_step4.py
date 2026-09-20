"""Run: python manage.py shell -c \"exec(open('generador/demo_step4.py').read())\"."""
from pathlib import Path
from zipfile import ZipFile
from django.conf import settings
from generador.demo_step3 import demo_ir
from generador.services.code_generator import CodeGenerator

root = settings.BASE_DIR / "artifacts" / "step4-entities"
if root.exists():
    raise RuntimeError("El ejemplo ya existe; conserva su verificación antes de regenerarlo.")
generator = CodeGenerator(demo_ir(), incluir_swagger=False, incluir_docker=False, alcance="entidades")
name = generator.generar()
with ZipFile(Path(settings.GENERADOR_TMP_DIR) / name) as archive:
    archive.extractall(root)
print(root)
print(generator.metricas)
