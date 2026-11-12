"""Endpoint de salud: verifica que el backend se conecta a la base de datos.

Lo usa el health check de Render y el monitoreo externo; no requiere autenticación.
"""
import logging

from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - cualquier fallo de conexión se reporta como 503
        logger.exception("Health check: sin conexión a la base de datos")
        return Response({"status": "error", "db": connection.vendor}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return Response({"status": "ok", "db": connection.vendor})
