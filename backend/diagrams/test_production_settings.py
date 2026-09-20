import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class ProductionSettingsTests(SimpleTestCase):
    def import_settings(self, **changes):
        environment = {
            **os.environ,
            'DEBUG': 'release',
            'DB_ENGINE': 'postgres',
            'SECRET_KEY': 'verify-only-0123456789-abcdefghijklmnopqrstuvwxyz-ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'ALLOWED_HOSTS': 'uml.example.com',
            'DB_NAME': 'diagrama', 'DB_USER': 'app', 'DB_PASSWORD': 'verify-only',
            'DB_HOST': 'db.example.com',
            'DB_SSLMODE': 'require',
            'GENERADOR_TMP_DIR': str(settings.BASE_DIR / 'generados'),
            **changes,
        }
        return subprocess.run([
            sys.executable, '-c',
            'from backend import settings_production as s; '
            'assert s.DEBUG is False; assert s.SECURE_SSL_REDIRECT; '
            'assert s.SESSION_COOKIE_SECURE and s.CSRF_COOKIE_SECURE; '
            'assert not s.CORS_ALLOW_ALL_ORIGINS; '
            'assert s.DATABASES["default"]["OPTIONS"]["sslmode"] == "require"',
        ], cwd=settings.BASE_DIR, env=environment, capture_output=True, text=True)

    def test_production_overrides_inherited_debug_and_enforces_https(self):
        result = self.import_settings()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_missing_secret_fails_closed(self):
        result = self.import_settings(SECRET_KEY='')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Falta la variable de producción SECRET_KEY', result.stderr)

    def test_wildcard_host_is_rejected(self):
        result = self.import_settings(ALLOWED_HOSTS='*')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('hosts concretos', result.stderr)

    def test_sqlite_cannot_be_selected_in_production(self):
        result = self.import_settings(DB_ENGINE='sqlite')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Producción requiere PostgreSQL', result.stderr)
