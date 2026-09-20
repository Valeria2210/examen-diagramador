from django.conf import settings
from rest_framework.throttling import UserRateThrottle


class GenerationThrottle(UserRateThrottle):
    scope = "backend_generation"

    def get_rate(self):
        return settings.GENERADOR_RATE
