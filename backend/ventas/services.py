"""Reglas de negocio del catálogo de clientes (T7.3)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import Cliente

ENTIDAD = "cliente"
CAMPOS_EDITABLES = {"nombre", "tipo", "nit", "nrc", "activo"}


def instantanea(cliente):
    return {"nombre": cliente.nombre, "tipo": cliente.tipo, "nit": cliente.nit or "", "nrc": cliente.nrc or "", "activo": cliente.activo}


def _limpiar(datos):
    return {c: (v.strip() if isinstance(v, str) else v) for c, v in datos.items()}


def _validar(cliente, excluir=None):
    errores = {}
    if not cliente.nombre:
        errores["nombre"] = "Indique el nombre del cliente."
    if cliente.tipo not in Cliente.Tipo.values:
        errores["tipo"] = "Tipo de cliente inválido."
    if cliente.tipo == Cliente.Tipo.CONTRIBUYENTE:
        if not cliente.nit:
            errores["nit"] = "Un contribuyente necesita NIT."
        if not cliente.nrc:
            errores["nrc"] = "Un contribuyente necesita NRC (número de registro de contribuyente)."
    if errores:
        raise ValidationError(errores)
    if cliente.nit:
        qs = Cliente.objects.filter(nit=cliente.nit)
        if excluir is not None:
            qs = qs.exclude(pk=excluir.pk)
        if qs.exists():
            raise ValidationError({"nit": f"Ya existe un cliente con el NIT {cliente.nit}."})
    # Formato de NIT y NRC (la unicidad y las restricciones ya se revisaron arriba: en Oracle '' = NULL).
    cliente.full_clean(validate_unique=False, validate_constraints=False)


def _en_uso(cliente):
    return cliente.documentos.exists()


@transaction.atomic
def crear_cliente(*, usuario, nombre, tipo, nit="", nrc="", activo=True, request=None):
    datos = _limpiar({"nombre": nombre, "tipo": tipo, "nit": nit or "", "nrc": nrc or "", "activo": activo})
    cliente = Cliente(**{**datos, "nit": datos["nit"] or None}, creado_por=usuario, modificado_por=usuario)
    _validar(cliente)
    cliente.save()
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad=ENTIDAD, objeto_id=cliente.pk,
        descripcion=f"Alta del cliente {cliente}", valor_nuevo=instantanea(cliente), request=request,
    )
    return cliente


@transaction.atomic
def actualizar_cliente(cliente, *, usuario, datos, request=None):
    desconocidos = set(datos) - CAMPOS_EDITABLES
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    antes = instantanea(cliente)
    for campo, valor in _limpiar(datos).items():
        setattr(cliente, campo, (valor or None) if campo == "nit" else valor)
    despues = instantanea(cliente)
    if antes == despues:
        return cliente
    if _en_uso(cliente) and (despues["nit"] != antes["nit"] or despues["nrc"] != antes["nrc"] or despues["tipo"] != antes["tipo"]):
        raise ValidationError("El cliente ya tiene documentos de venta: su tipo, NIT y NRC no se pueden cambiar.")
    _validar(cliente, excluir=cliente)
    cliente.modificado_por = usuario
    cliente.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad=ENTIDAD, objeto_id=cliente.pk,
        descripcion=f"Modificación del cliente {cliente}", valor_anterior=antes, valor_nuevo=despues, request=request,
    )
    return cliente


@transaction.atomic
def eliminar_cliente(cliente, *, usuario, request=None):
    cliente = Cliente.objects.select_for_update().get(pk=cliente.pk)
    if _en_uso(cliente):
        raise ValidationError("El cliente tiene documentos de venta: desactívelo en lugar de eliminarlo.")
    antes = instantanea(cliente)
    pk, descripcion = cliente.pk, f"Baja del cliente {cliente}"
    cliente.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR, usuario=usuario, entidad=ENTIDAD, objeto_id=pk, descripcion=descripcion,
        valor_anterior=antes, request=request,
    )


def consultar_clientes(*, q=None, activo=None, tipo=None):
    qs = Cliente.objects.order_by("nombre")
    if q:
        q = q.strip()
        qs = qs.filter(Q(nombre__icontains=q) | Q(nit__icontains=q) | Q(nrc__icontains=q))
    if activo is not None:
        qs = qs.filter(activo=activo)
    if tipo:
        qs = qs.filter(tipo=tipo)
    return qs
