"""Production settings for an HTTPS reverse proxy and a private PostgreSQL database."""
import os

from django.core.exceptions import ImproperlyConfigured

# Production must ignore a development DEBUG value inherited from the host.
os.environ['DEBUG'] = 'False'
from .settings import *  # noqa: F403,E402


def required_environment(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'Falta la variable de producción {name}.')
    return value


SECRET_KEY = required_environment('SECRET_KEY')
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith('django-insecure-'):
    raise ImproperlyConfigured('SECRET_KEY debe ser aleatoria y tener al menos 50 caracteres.')
ALLOWED_HOSTS = [host.strip() for host in required_environment('ALLOWED_HOSTS').split(',') if host.strip()]
if '*' in ALLOWED_HOSTS:
    raise ImproperlyConfigured('Define los hosts concretos de producción; no uses *.')
if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured('Producción requiere PostgreSQL.')
for environment_name, database_key in [('DB_NAME', 'NAME'), ('DB_USER', 'USER'), ('DB_PASSWORD', 'PASSWORD'), ('DB_HOST', 'HOST')]:
    DATABASES['default'][database_key] = required_environment(environment_name)
DATABASES['default']['CONN_MAX_AGE'] = 60
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
DATABASES['default']['OPTIONS'] = {'sslmode': os.environ.get('DB_SSLMODE', 'require')}

CORS_ALLOW_ALL_ORIGINS = False
AUTH_RATE = os.environ.get('AUTH_RATE', '10/min')
REST_FRAMEWORK = {**REST_FRAMEWORK, 'NUM_PROXIES': 1}
CORS_ALLOWED_ORIGINS = [origin.strip() for origin in os.environ.get('CORS_ALLOWED_ORIGINS', '').split(',') if origin.strip()]
CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in os.environ.get('CSRF_TRUSTED_ORIGINS', '').split(',') if origin.strip()]
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 3600
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
# Enable only when the trusted proxy overwrites X-Forwarded-Proto and the
# application port is inaccessible to public clients.
if os.environ.get('TRUST_PROXY_SSL_HEADER', 'false').lower() == 'true':
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
STATIC_ROOT = BASE_DIR / 'staticfiles'
GENERADOR_TMP_DIR = Path(required_environment('GENERADOR_TMP_DIR'))
CACHES = {'default': {
    'BACKEND': 'django.core.cache.backends.filebased.FileBasedCache',
    'LOCATION': os.environ.get('THROTTLE_CACHE_DIR', '/var/lib/uml/cache'),
}}
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}
