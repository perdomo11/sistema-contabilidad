"""Reglas de negocio del catálogo de proveedores."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import Proveedor

ENTIDAD = "proveedor"
CAMPOS_EDITABLES = {"nit", "nombre", "nrc", "activo"}


def instantanea(proveedor):
    return {"nit": proveedor.nit, "nombre": proveedor.nombre, "nrc": proveedor.nrc, "activo": proveedor.activo}


def _limpiar(datos):
    return {c: (v.strip() if isinstance(v, str) else v) for c, v in datos.items()}


def _validar_nit_unico(nit, excluir=None):
    qs = Proveedor.objects.filter(nit=nit)
    if excluir is not None:
        qs = qs.exclude(pk=excluir.pk)
    if qs.exists():
        raise ValidationError({"nit": f"Ya existe un proveedor con el NIT {nit}."})


def _en_uso(proveedor):
    # Importación local: contabilidad y centros_costo dependen de esta app.
    from centros_costo.models import ReglaAsignacion
    from contabilidad.models import Asiento

    return Asiento.objects.filter(proveedor=proveedor).exists() or ReglaAsignacion.objects.filter(proveedor=proveedor).exists()


@transaction.atomic
def crear_proveedor(*, usuario, nit, nombre, nrc="", activo=True, request=None):
    datos = _limpiar({"nit": nit, "nombre": nombre, "nrc": nrc or "", "activo": activo})
    _validar_nit_unico(datos["nit"])
    proveedor = Proveedor(**datos, creado_por=usuario, modificado_por=usuario)
    proveedor.full_clean()
    proveedor.save()
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=proveedor.pk,
        descripcion=f"Alta del proveedor {proveedor}",
        valor_nuevo=instantanea(proveedor),
        request=request,
    )
    return proveedor


@transaction.atomic
def actualizar_proveedor(proveedor, *, usuario, datos, request=None):
    desconocidos = set(datos) - CAMPOS_EDITABLES
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})
    proveedor = Proveedor.objects.select_for_update().get(pk=proveedor.pk)
    antes = instantanea(proveedor)
    for campo, valor in _limpiar(datos).items():
        setattr(proveedor, campo, valor)
    if proveedor.nit != antes["nit"]:
        if _en_uso(proveedor):
            raise ValidationError({"nit": "El proveedor ya se usó en asientos o reglas: el NIT no se puede cambiar."})
        _validar_nit_unico(proveedor.nit, excluir=proveedor)
    despues = instantanea(proveedor)
    if antes == despues:
        return proveedor
    proveedor.modificado_por = usuario
    proveedor.full_clean()
    proveedor.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=proveedor.pk,
        descripcion=f"Modificación del proveedor {proveedor}",
        valor_anterior=antes,
        valor_nuevo=despues,
        request=request,
    )
    return proveedor


@transaction.atomic
def eliminar_proveedor(proveedor, *, usuario, request=None):
    proveedor = Proveedor.objects.select_for_update().get(pk=proveedor.pk)
    if _en_uso(proveedor):
        raise ValidationError("El proveedor se usó en asientos o reglas de asignación: desactívelo en lugar de eliminarlo.")
    antes = instantanea(proveedor)
    pk, descripcion = proveedor.pk, f"Baja del proveedor {proveedor}"
    proveedor.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=pk,
        descripcion=descripcion,
        valor_anterior=antes,
        request=request,
    )


def validar_proveedor_activo(proveedor, campo="proveedor"):
    """Relee el proveedor y exige que esté activo. Devuelve el proveedor (o None)."""
    if proveedor is None:
        return None
    proveedor = Proveedor.objects.get(pk=proveedor.pk)
    if not proveedor.activo:
        raise ValidationError({campo: f"El proveedor {proveedor.nombre} está inactivo."})
    return proveedor


def consultar_proveedores(*, q=None, activo=None):
    qs = Proveedor.objects.order_by("nombre")
    if q:
        q = q.strip()
        qs = qs.filter(Q(nombre__icontains=q) | Q(nit__icontains=q) | Q(nrc__icontains=q))
    if activo is not None:
        qs = qs.filter(activo=activo)
    return qs
