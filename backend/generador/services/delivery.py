import hashlib
import re
from datetime import timedelta
from pathlib import Path
from django.conf import settings

ZIP_NAME = re.compile(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}\.zip")


def ruta_zip(nombre):
    if not ZIP_NAME.fullmatch(nombre):
        raise ValueError("Nombre de ZIP inválido.")
    base = Path(settings.GENERADOR_TMP_DIR).resolve()
    raw = base / nombre
    if raw.is_symlink() or raw.resolve().parent != base:
        raise ValueError("Ruta de ZIP inválida.")
    return raw


def sha256_archivo(archivo):
    digest = hashlib.sha256()
    for chunk in iter(lambda: archivo.read(65536), b""):
        digest.update(chunk)
    return digest.hexdigest()


def expiracion(generacion):
    return generacion.fecha_creacion + timedelta(hours=settings.GENERADOR_ZIP_TTL_HORAS)
