"""Lógica de negocio de usuarios, roles y bitácora de auditoría."""
from datetime import datetime, time

from django.utils import timezone

from .models import Bitacora


# --- Roles -------------------------------------------------------------------

def roles_de(usuario):
    if not usuario or not usuario.is_authenticated:
        return []
    return sorted(usuario.groups.values_list("name", flat=True))


def tiene_rol(usuario, *roles):
    """True si el usuario tiene alguno de los roles indicados. El superusuario los tiene todos."""
    if not usuario or not usuario.is_authenticated or not usuario.is_active:
        return False
    if usuario.is_superuser:
        return True
    return usuario.groups.filter(name__in=roles).exists()


def datos_usuario(usuario):
    return {
        "id": usuario.pk,
        "username": usuario.username,
        "nombre": usuario.get_full_name() or usuario.username,
        "email": usuario.email,
        "roles": roles_de(usuario),
        "es_admin": usuario.is_superuser,
    }


def instantanea_usuario(usuario):
    """Estado auditable de un usuario (sin contraseña), para valor anterior/nuevo."""
    return {
        "username": usuario.username,
        "nombre": usuario.first_name,
        "apellido": usuario.last_name,
        "email": usuario.email,
        "activo": usuario.is_active,
        "staff": usuario.is_staff,
        "superusuario": usuario.is_superuser,
        "roles": roles_de(usuario) if usuario.pk else [],
    }


# --- Bitácora ----------------------------------------------------------------

def ip_de(request):
    """IP del cliente. En desarrollo el proxy de Vite agrega X-Forwarded-For."""
    if request is None:
        return None
    reenviada = request.META.get("HTTP_X_FORWARDED_FOR")
    if reenviada:
        return reenviada.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def registrar_evento(
    accion,
    *,
    usuario=None,
    nombre_usuario=None,
    entidad="",
    objeto_id="",
    descripcion="",
    valor_anterior=None,
    valor_nuevo=None,
    request=None,
):
    """Crea un registro en la bitácora de auditoría y lo devuelve."""
    if usuario is not None and not usuario.is_authenticated:
        usuario = None
    if nombre_usuario is None:
        nombre_usuario = usuario.username if usuario else ""
    return Bitacora.objects.create(
        usuario=usuario,
        nombre_usuario=(nombre_usuario or "")[:150],
        accion=accion,
        entidad=entidad,
        objeto_id=str(objeto_id) if objeto_id not in (None, "") else "",
        descripcion=(descripcion or "")[:500],
        valor_anterior=valor_anterior,
        valor_nuevo=valor_nuevo,
        ip=ip_de(request),
    )


def _inicio_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.min))


def _fin_dia(fecha):
    return timezone.make_aware(datetime.combine(fecha, time.max))


def consultar_bitacora(*, usuario=None, accion=None, desde=None, hasta=None):
    """Bitácora filtrada. `desde`/`hasta` son fechas (date), inclusivas."""
    qs = Bitacora.objects.select_related("usuario").order_by("-fecha", "-id")
    if usuario:
        qs = qs.filter(nombre_usuario__icontains=usuario)
    if accion:
        qs = qs.filter(accion=accion)
    if desde:
        qs = qs.filter(fecha__gte=_inicio_dia(desde))
    if hasta:
        qs = qs.filter(fecha__lte=_fin_dia(hasta))
    return qs
