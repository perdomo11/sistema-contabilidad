"""Endpoint de salud: verifica que el backend se conecta a Oracle."""
from django.db import DatabaseError, connection
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


def _consultar_version():
    with connection.cursor() as cursor:
        try:
            cursor.execute("SELECT banner FROM v$version FETCH FIRST 1 ROWS ONLY")
            fila = cursor.fetchone()
            return fila[0] if fila else None
        except DatabaseError:
            # El usuario de la aplicación puede no tener permiso sobre v$version.
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.fetchone()
            return "desconocida (sin permiso para v$version)"


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health(request):
    try:
        version = _consultar_version()
    except Exception as exc:  # noqa: BLE001 - se reporta cualquier fallo de conexión
        return Response(
            {"status": "error", "database": "sin conexión", "detalle": str(exc)},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return Response({"status": "ok", "database": "conectada", "version": version})
