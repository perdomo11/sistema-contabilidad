from rest_framework.permissions import BasePermission

from .services import tiene_rol


class EsSuperusuario(BasePermission):
    message = "Solo el administrador (superusuario) puede realizar esta acción."

    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and usuario.is_active and usuario.is_superuser)


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
