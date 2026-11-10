"""Manejo uniforme de errores de la API."""
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def manejador_excepciones(exc, context):
    """Convierte los ValidationError de Django (lanzados por los services) en respuestas 400.

    - Errores por campo: {"campo": ["mensaje"], ...}
    - Errores generales: {"detail": "mensaje"}
    """
    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "error_dict"):
            datos = exc.message_dict
            generales = datos.pop("__all__", None)
            if generales:
                datos["detail"] = " ".join(generales)
        else:
            datos = {"detail": " ".join(exc.messages)}
        return Response(datos, status=status.HTTP_400_BAD_REQUEST)
    return exception_handler(exc, context)
