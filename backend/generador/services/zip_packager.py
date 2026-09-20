from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED


class ZipPackager:
    def __init__(self, carpeta_proyecto):
        self.root = Path(carpeta_proyecto)

    def empaquetar(self, destino):
        destino = Path(destino)
        root = self.root.resolve()
        if destino.resolve().is_relative_to(root):
            raise ValueError("El ZIP debe estar fuera de su carpeta fuente.")
        if destino.exists():
            raise FileExistsError(destino)
        partial = destino.with_suffix(".zip.part")
        created = False
        try:
            with partial.open("xb") as output:
                created = True
                with ZipFile(output, "w", ZIP_DEFLATED) as archive:
                    for file in sorted(root.rglob("*")):
                        if file.is_symlink() or not file.resolve().is_relative_to(root):
                            raise ValueError("No se permiten enlaces fuera del proyecto generado.")
                        if file.is_file():
                            archive.write(file, file.relative_to(root).as_posix())
            with ZipFile(partial) as archive:
                if archive.testzip() is not None:
                    raise ValueError("El ZIP generado está corrupto.")
            partial.rename(destino)
            return destino.name
        finally:
            if created:
                partial.unlink(missing_ok=True)
