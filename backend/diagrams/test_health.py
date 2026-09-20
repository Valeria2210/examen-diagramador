from unittest.mock import patch

from django.db.utils import OperationalError
from django.test import TestCase, override_settings


@override_settings(ALLOWED_HOSTS=['testserver'])
class HealthTests(TestCase):
    def test_ready_when_database_is_available(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok'})

    def test_unavailable_does_not_expose_database_error(self):
        with patch('backend.health.connection.cursor', side_effect=OperationalError('private database details')):
            response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'status': 'unavailable'})
