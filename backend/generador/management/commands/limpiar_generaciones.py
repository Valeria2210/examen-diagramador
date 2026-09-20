from datetime import timedelta
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from generador.services.delivery import ZIP_NAME, ruta_zip
from generador.models import GeneracionBackend


class Command(BaseCommand):
    help = "Elimina ZIP expirados y huérfanos antiguos; conserva el historial."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Solo muestra los archivos que se eliminarían.")

    def handle(self, *args, **options):
        if settings.GENERADOR_ZIP_TTL_HORAS <= 0:
            raise CommandError("GENERADOR_ZIP_TTL_HORAS debe ser positivo.")
        base = Path(settings.GENERADOR_TMP_DIR).resolve()
        cutoff = timezone.now() - timedelta(hours=settings.GENERADOR_ZIP_TTL_HORAS)
        removed = 0
        if not base.is_dir():
            self.stdout.write("0 archivos.")
            return
        active = set(GeneracionBackend.objects.filter(fecha_creacion__gt=cutoff).values_list("ruta_archivo", flat=True))
        expired = set(GeneracionBackend.objects.filter(fecha_creacion__lte=cutoff).values_list("ruta_archivo", flat=True))
        for file in base.iterdir():
            if not ZIP_NAME.fullmatch(file.name) or file.name in active:
                continue
            try:
                path = ruta_zip(file.name)
                if not path.is_file():
                    continue
                if file.name not in expired and path.stat().st_mtime > cutoff.timestamp():
                    continue
                if not options["dry_run"]:
                    path.unlink()
                removed += 1
            except (ValueError, FileNotFoundError):
                continue
        self.stdout.write(f"{removed} archivos {'identificados' if options['dry_run'] else 'eliminados'}.")
