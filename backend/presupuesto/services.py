"""Reglas del presupuesto institucional (T4.1).

Todo cambio del monto crea una `VersionPresupuesto` inmutable y un evento de bitácora con el valor
anterior y el nuevo. Estados: borrador → aprobado → cerrado.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import ANIO_MAXIMO, ANIO_MINIMO, PresupuestoInstitucional, VersionPresupuesto

ENTIDAD = "presupuesto"
Estado = PresupuestoInstitucional.Estado
Tipo = VersionPresupuesto.Tipo
MONTO_MAXIMO = Decimal("9999999999999999.99")  # NUMBER(18,2)


def instantanea(p):
    return {
        "anio": p.anio,
        "monto": f"{p.monto:.2f}",
        "version": p.version,
        "estado": p.estado,
        "descripcion": p.descripcion,
        "referencia_aprobacion": p.referencia_aprobacion,
    }


def _texto(valor):
    return (valor or "").strip()


def _validar_monto(monto, campo="monto"):
    try:
        monto = Decimal(str(monto))
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError({campo: "Monto inválido."}) from None
    if not monto.is_finite():
        raise ValidationError({campo: "Monto inválido."})
    if monto != monto.quantize(Decimal("0.01")):
        raise ValidationError({campo: "El monto admite como máximo 2 decimales."})
    if monto <= 0:
        raise ValidationError({campo: "El monto institucional debe ser mayor que cero."})
    if monto > MONTO_MAXIMO:
        raise ValidationError({campo: "El monto excede el máximo permitido."})
    return monto.quantize(Decimal("0.01"))


def _bloquear(presupuesto):
    return PresupuestoInstitucional.objects.select_for_update().get(pk=presupuesto.pk)


def _exigir_no_cerrado(p):
    if p.estado == Estado.CERRADO:
        raise ValidationError(f"El presupuesto {p.anio} está cerrado: no admite cambios.")


def _nueva_version(p, *, usuario, tipo, monto, motivo="", referencia=""):
    """Registra la versión y actualiza el presupuesto (el trigger exige que coincidan)."""
    anterior = p.monto
    p.version += 1
    VersionPresupuesto.objects.create(
        presupuesto=p, numero=p.version, tipo=tipo, monto=monto, monto_anterior=anterior,
        motivo=motivo, referencia=referencia, registrado_por=usuario,
    )
    p.monto = monto
    p.modificado_por = usuario


@transaction.atomic
def crear_presupuesto(*, usuario, anio, monto, descripcion="", request=None):
    if not ANIO_MINIMO <= anio <= ANIO_MAXIMO:
        raise ValidationError({"anio": f"El año debe estar entre {ANIO_MINIMO} y {ANIO_MAXIMO}."})
    if PresupuestoInstitucional.objects.filter(anio=anio).exists():
        raise ValidationError({"anio": f"Ya existe el presupuesto institucional del ejercicio {anio}."})
    monto = _validar_monto(monto)
    p = PresupuestoInstitucional.objects.create(
        anio=anio, monto=monto, version=1, descripcion=_texto(descripcion), creado_por=usuario, modificado_por=usuario
    )
    VersionPresupuesto.objects.create(
        presupuesto=p, numero=1, tipo=Tipo.INICIAL, monto=monto, motivo="Monto inicial", registrado_por=usuario
    )
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad=ENTIDAD, objeto_id=p.pk,
        descripcion=f"Alta del presupuesto institucional {anio} por {monto:,.2f}",
        valor_nuevo=instantanea(p), request=request,
    )
    return p


@transaction.atomic
def cambiar_monto(presupuesto, *, usuario, monto, motivo="", referencia="", request=None):
    """Ajuste (borrador) o modificación presupuestaria (aprobado; exige motivo y referencia)."""
    p = _bloquear(presupuesto)
    _exigir_no_cerrado(p)
    monto = _validar_monto(monto)
    motivo, referencia = _texto(motivo), _texto(referencia)
    if monto == p.monto:
        raise ValidationError({"monto": "El monto nuevo es igual al vigente."})
    if p.estado == Estado.APROBADO:
        errores = {}
        if not motivo:
            errores["motivo"] = "Una modificación de un presupuesto aprobado requiere el motivo."
        if not referencia:
            errores["referencia"] = "Indique el documento que autoriza la modificación."
        if errores:
            raise ValidationError(errores)
        tipo = Tipo.MODIFICACION
    else:
        tipo = Tipo.AJUSTE
    antes = instantanea(p)
    _nueva_version(p, usuario=usuario, tipo=tipo, monto=monto, motivo=motivo, referencia=referencia)
    p.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad=ENTIDAD, objeto_id=p.pk,
        descripcion=f"{Tipo(tipo).label} del presupuesto {p.anio}: {antes['monto']} → {p.monto:.2f}"
        + (f" ({motivo})" if motivo else ""),
        valor_anterior=antes, valor_nuevo=instantanea(p), request=request,
    )
    return p


@transaction.atomic
def aprobar_presupuesto(presupuesto, *, usuario, referencia, request=None):
    p = _bloquear(presupuesto)
    if p.estado != Estado.BORRADOR:
        raise ValidationError(f"Solo se aprueba un presupuesto en borrador (el de {p.anio} está {p.get_estado_display().lower()}).")
    referencia = _texto(referencia)
    if not referencia:
        raise ValidationError({"referencia": "Indique el documento de aprobación de la gerencia (p. ej. acta de junta directiva)."})
    antes = instantanea(p)
    p.version += 1
    VersionPresupuesto.objects.create(
        presupuesto=p, numero=p.version, tipo=Tipo.APROBACION, monto=p.monto, monto_anterior=p.monto,
        motivo="Aprobación de la gerencia", referencia=referencia, registrado_por=usuario,
    )
    p.estado = Estado.APROBADO
    p.referencia_aprobacion = referencia
    p.aprobado_por = usuario
    p.aprobado_en = timezone.now()
    p.modificado_por = usuario
    p.save()
    registrar_evento(
        Bitacora.Accion.APROBAR, usuario=usuario, entidad=ENTIDAD, objeto_id=p.pk,
        descripcion=f"Aprobación del presupuesto institucional {p.anio} ({referencia})",
        valor_anterior=antes, valor_nuevo=instantanea(p), request=request,
    )
    return p


@transaction.atomic
def cerrar_presupuesto(presupuesto, *, usuario, request=None):
    p = _bloquear(presupuesto)
    if p.estado != Estado.APROBADO:
        raise ValidationError("Solo se cierra un presupuesto aprobado.")
    antes = instantanea(p)
    p.estado = Estado.CERRADO
    p.modificado_por = usuario
    p.save()
    registrar_evento(
        Bitacora.Accion.CERRAR, usuario=usuario, entidad=ENTIDAD, objeto_id=p.pk,
        descripcion=f"Cierre del presupuesto institucional {p.anio}",
        valor_anterior=antes, valor_nuevo=instantanea(p), request=request,
    )
    return p


@transaction.atomic
def actualizar_descripcion(presupuesto, *, usuario, descripcion, request=None):
    p = _bloquear(presupuesto)
    _exigir_no_cerrado(p)
    descripcion = _texto(descripcion)
    if descripcion == p.descripcion:
        return p
    antes = instantanea(p)
    p.descripcion = descripcion
    p.modificado_por = usuario
    p.full_clean(exclude=["aprobado_por", "creado_por", "modificado_por"])
    p.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad=ENTIDAD, objeto_id=p.pk,
        descripcion=f"Descripción del presupuesto {p.anio}",
        valor_anterior=antes, valor_nuevo=instantanea(p), request=request,
    )
    return p
