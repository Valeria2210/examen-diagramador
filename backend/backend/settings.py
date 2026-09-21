from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="dev-secret-key-change-me")
DEBUG = str(config("DEBUG", default="True")).lower() in ("true", "1", "yes", "on")
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "diagrams",
    "generador",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "backend.wsgi.application"
ASGI_APPLICATION = "backend.asgi.application"

# Base de datos: PostgreSQL por defecto.
# Para pruebas rápidas sin Docker se puede forzar sqlite con DB_ENGINE=sqlite
if config("DB_ENGINE", default="postgres") == "sqlite":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME", default="diagrama"),
            "USER": config("DB_USER", default="valeria"),
            "PASSWORD": config("DB_PASSWORD", default="123456789"),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/La_Paz"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
GENERADOR_TMP_DIR = Path(config("GENERADOR_TMP_DIR", default=str(BASE_DIR / "generados")))
GENERADOR_MAX_ENTIDADES = config("GENERADOR_MAX_ENTIDADES", default=50, cast=int)
GENERADOR_ZIP_TTL_HORAS = config("GENERADOR_ZIP_TTL_HORAS", default=24, cast=int)
GENERADOR_RATE = config("GENERADOR_RATE", default="10/min")
GENERADOR_MAX_ATRIBUTOS = config("GENERADOR_MAX_ATRIBUTOS", default=200, cast=int)
GENERADOR_MAX_RELACIONES = config("GENERADOR_MAX_RELACIONES", default=500, cast=int)

# CORS: en desarrollo se abre para el front en React (ajustar en producción)
CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = config("CORS_ALLOWED_ORIGINS", default="http://localhost:5173,http://127.0.0.1:5173", cast=Csv())

# Keep manual restore points; bound the space used by automatic snapshots.
DIAGRAM_AUTO_VERSION_LIMIT = config("DIAGRAM_AUTO_VERSION_LIMIT", default=100, cast=int)
AUTH_RATE = config('AUTH_RATE', default='30/min')
AI_RATE = config('AI_RATE', default='10/min')

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}
