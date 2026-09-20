from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle


class AuthThrottle(SimpleRateThrottle):
    scope = 'auth'

    def get_rate(self):
        return settings.AUTH_RATE

    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': self.get_ident(request)}


class AIThrottle(UserRateThrottle):
    scope = 'ai'

    def get_rate(self):
        return settings.AI_RATE
