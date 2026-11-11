"""Configuración de Django para el Sistema Contable.

Todos los valores dependientes del entorno se leen de variables de entorno
(ver `.env.example`).
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(nombre, defecto=False):
    return os.environ.get(nombre, str(defecto)).strip().lower() in ("1", "true", "yes", "si", "sí")


def env_list(nombre, defecto=""):
    return [v.strip() for v in os.environ.get(nombre, defecto).split(",") if v.strip()]


SECRET_KEY = os.environ.get("SECRET_KEY", "clave-insegura-solo-desarrollo")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "usuarios",
    "contabilidad",
    "centros_costo",
    "tesoreria",
    "presupuesto",
    "reportes",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Base de datos: Oracle XE 21c con python-oracledb en modo thin.
# Se usa la cadena Easy Connect "host:puerto/servicio" para conectar por
# SERVICE NAME (XEPDB1); si se pasaran HOST/PORT por separado, Django
# interpretaría NAME como SID y la conexión a la PDB fallaría.
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "1521")
DB_NAME = os.environ.get("DB_NAME", "XEPDB1")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.oracle",
        "NAME": f"{DB_HOST}:{DB_PORT}/{DB_NAME}",
        "USER": os.environ.get("DB_USER", "contable"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": "",
        "PORT": "",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
TIME_ZONE = "America/El_Salvador"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    # Toda la API exige JWT salvo las vistas que declaren lo contrario.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "EXCEPTION_HANDLER": "config.excepciones.manejador_excepciones",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_MINUTOS", "30"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(hours=int(os.environ.get("JWT_REFRESH_HORAS", "8"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

# Datos de la empresa para el encabezado de los libros y reportes exportados (T7.1).
EMPRESA_NOMBRE = os.environ.get("EMPRESA_NOMBRE", "Banco Demostración, S.A.")
EMPRESA_NIT = os.environ.get("EMPRESA_NIT", "0614-150395-101-7")
EMPRESA_NRC = os.environ.get("EMPRESA_NRC", "123456-7")
