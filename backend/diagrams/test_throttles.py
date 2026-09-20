from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


@override_settings(ALLOWED_HOSTS=['testserver'], AUTH_RATE='1/min', AI_RATE='1/min')
class EndpointThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient()

    def test_failed_login_and_registration_share_ip_limit(self):
        response = self.client.post('/api/auth/login/', {'username': 'invalid', 'password': 'invalid'}, format='json')
        self.assertEqual(response.status_code, 400)
        response = self.client.post('/api/auth/register/', {}, format='json')
        self.assertEqual(response.status_code, 429)

    def test_ai_limit_applies_per_authenticated_user_before_external_calls(self):
        self.client.force_authenticate(User.objects.create_user(username='ai-limit'))
        with patch('diagrams.views.config', return_value=''):
            response = self.client.post('/api/ai/interpret-uml/', {'description': 'Un cliente'}, format='json')
            self.assertEqual(response.status_code, 503)
            response = self.client.post('/api/ai/interpret-uml/', {'description': 'Un cliente'}, format='json')
            self.assertEqual(response.status_code, 429)
