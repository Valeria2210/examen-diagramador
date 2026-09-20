import tempfile
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from django.test import SimpleTestCase
from .services.zip_packager import ZipPackager


class PackagingTests(SimpleTestCase):
    def test_failed_archive_is_not_published_and_existing_zip_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "source"
            root.mkdir()
            (root / "README.md").write_text("example")
            target = Path(temp) / "project.zip"
            with patch.object(ZipFile, "write", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    ZipPackager(root).empaquetar(target)
            self.assertFalse(target.exists())
            self.assertFalse(target.with_suffix(".zip.part").exists())
            ZipPackager(root).empaquetar(target)
            original = target.read_bytes()
            with self.assertRaises(FileExistsError):
                ZipPackager(root).empaquetar(target)
            self.assertEqual(target.read_bytes(), original)
            with self.assertRaises(ValueError):
                ZipPackager(root).empaquetar(root / "recursive.zip")
