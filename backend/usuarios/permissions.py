from rest_framework.permissions import BasePermission

from .services import tiene_rol


def TieneRol(*roles):
    """Permiso DRF: el usuario debe tener alguno de los roles (o ser superusuario).

    Uso: permission_classes = [TieneRol(roles.AUDITOR)]
    """

    class _TieneRol(BasePermission):
        message = "No tiene el rol requerido para esta acción."

        def has_permission(self, request, view):
            return tiene_rol(request.user, *roles)

    _TieneRol.__name__ = "TieneRol(" + ", ".join(roles) + ")"
    return _TieneRol
