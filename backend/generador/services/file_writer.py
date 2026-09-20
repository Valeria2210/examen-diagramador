from pathlib import Path


class FileWriter:
    def __init__(self, root):
        self.root = Path(root).resolve()

    def escribir(self, relativa, contenido):
        target = (self.root / relativa).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Ruta fuera del proyecto generado.")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(contenido, encoding="utf-8", newline="\n")
