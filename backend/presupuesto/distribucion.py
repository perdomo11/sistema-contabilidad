"""Distribución top-down del presupuesto institucional (T4.2).

Nivel 1: asignación anual a departamentos (Σ ≤ monto institucional; diferencia = saldo sin distribuir).
Nivel 2: detalle de cada departamento por cuenta de gasto y mes (Σ ≤ asignación; diferencia = sin detallar).
Cada asignación o celda que cambia queda en `CambioDistribucion` (inmutable) y cada operación en la bitácora.
Los mismos topes los verifica Oracle (migración 0004).
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from centros_costo.models import CentroCosto
from contabilidad.models import Cuenta
from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import AsignacionPresupuesto, CambioDistribucion, DetallePresupuesto, PresupuestoInstitucional
from .services import _bloquear, _texto, _validar_monto

ENTIDAD = "distribucion_presupuesto"
CERO = Decimal("0.00")
MESES = 12


def _t(monto):
    return f"{monto + CERO:.2f}"


def _porcentaje(parte, base):
    return f"{(parte * 100 / base).quantize(CERO) + CERO:.2f}" if base else None


def _exigir_editable(p):
    if p.estado == PresupuestoInstitucional.Estado.CERRADO:
        raise ValidationError(f"El presupuesto {p.anio} está cerrado: su distribución no admite cambios.")


def _validar_monto_cero(monto, campo="monto"):
    """Como `_validar_monto`, pero admite cero (quitar). Vacío = cero."""
    if monto in (None, ""):
        return CERO
    try:
        if Decimal(str(monto)) == 0:
            return CERO
    except (InvalidOperation, ValueError):
        pass  # `_validar_monto` informa "Monto inválido"
    return _validar_monto(monto, campo)


def _vigente_en_anio(centro, anio):
    return centro.vigente_desde <= date(anio, 12, 31) and (centro.vigente_hasta is None or centro.vigente_hasta >= date(anio, 1, 1))


def _vigente_en_mes(centro, anio, mes):
    inicio, fin = date(anio, mes, 1), date(anio, mes, monthrange(anio, mes)[1])
    return centro.vigente_desde <= fin and (centro.vigente_hasta is None or centro.vigente_hasta >= inicio)


def _validar_centro(centro, anio):
    if not centro.acepta_movimientos:
        raise ValidationError({"centro": f"El centro {centro.codigo} es de agrupación: asigne a sus departamentos de detalle."})
    if not _vigente_en_anio(centro, anio):
        raise ValidationError({"centro": f"El centro {centro.codigo} no está vigente en {anio}."})


def total_distribuido(presupuesto):
    return presupuesto.asignaciones.aggregate(t=Sum("monto"))["t"] or CERO


def _detallado_por_asignacion(presupuesto):
    filas = (
        DetallePresupuesto.objects.filter(asignacion__presupuesto=presupuesto)
        .values("asignacion_id").annotate(t=Sum("monto"))
    )
    return {f["asignacion_id"]: f["t"] for f in filas}


def _centro_json(c):
    return {"id": c.pk, "codigo": c.codigo, "nombre": c.nombre, "tipo": c.tipo, "tipo_display": c.get_tipo_display()}


# =============================================================================
# Consultas
# =============================================================================

def resumen_distribucion(presupuesto):
    asignaciones = list(presupuesto.asignaciones.select_related("centro_costo").order_by("centro_costo__codigo"))
    detallado = _detallado_por_asignacion(presupuesto)
    distribuido = sum((a.monto for a in asignaciones), CERO)
    total_detallado = sum(detallado.values(), CERO)
    return {
        "presupuesto": {
            "id": presupuesto.pk, "anio": presupuesto.anio, "estado": presupuesto.estado,
            "estado_display": presupuesto.get_estado_display(), "version": presupuesto.version,
        },
        "monto_institucional": _t(presupuesto.monto),
        "distribuido": _t(distribuido),
        "sin_distribuir": _t(presupuesto.monto - distribuido),
        "porcentaje_distribuido": _porcentaje(distribuido, presupuesto.monto),
        "detallado": _t(total_detallado),
        "departamentos": [
            {
                "centro": _centro_json(a.centro_costo),
                "asignado": _t(a.monto),
                "porcentaje": _porcentaje(a.monto, presupuesto.monto),
                "detallado": _t(detallado.get(a.pk, CERO)),
                "sin_detallar": _t(a.monto - detallado.get(a.pk, CERO)),
                "modificado_en": a.modificado_en,
            }
            for a in asignaciones
        ],
    }


def detalle_departamento(presupuesto, centro):
    asignacion = presupuesto.asignaciones.filter(centro_costo=centro).first()
    if asignacion is None:
        raise ValidationError({"centro": f"El centro {centro.codigo} no tiene asignación en el presupuesto {presupuesto.anio}."})
    filas = defaultdict(lambda: [CERO] * MESES)
    cuentas = {}
    for d in asignacion.detalle.select_related("cuenta"):
        filas[d.cuenta_id][d.mes - 1] = d.monto
        cuentas[d.cuenta_id] = d.cuenta
    por_mes = [sum((f[i] for f in filas.values()), CERO) for i in range(MESES)]
    detallado = sum(por_mes, CERO)
    return {
        "presupuesto": {"id": presupuesto.pk, "anio": presupuesto.anio, "estado": presupuesto.estado},
        "centro": _centro_json(centro),
        "meses_vigentes": [_vigente_en_mes(centro, presupuesto.anio, m) for m in range(1, MESES + 1)],
        "asignado": _t(asignacion.monto),
        "detallado": _t(detallado),
        "sin_detallar": _t(asignacion.monto - detallado),
        "filas": [
            {
                "cuenta": {"id": c.pk, "codigo": c.codigo, "nombre": c.nombre},
                "meses": [_t(m) for m in filas[c.pk]],
                "total": _t(sum(filas[c.pk], CERO)),
            }
            for c in sorted(cuentas.values(), key=lambda c: c.codigo)
        ],
        "por_mes": [_t(m) for m in por_mes],
    }


def historial_distribucion(presupuesto, centro=None):
    qs = presupuesto.cambios_distribucion.select_related("centro_costo", "cuenta", "registrado_por")
    if centro is not None:
        qs = qs.filter(centro_costo=centro)
    return qs


# =============================================================================
# Cambios
# =============================================================================

@transaction.atomic
def asignar_departamento(presupuesto, *, usuario, centro, monto, motivo="", request=None):
    """Crea, cambia o (monto 0) quita la asignación anual de un departamento."""
    p = _bloquear(presupuesto)
    _exigir_editable(p)
    centro = CentroCosto.objects.get(pk=centro.pk)
    monto = _validar_monto_cero(monto)
    motivo = _texto(motivo)
    asignacion = p.asignaciones.filter(centro_costo=centro).first()  # el presupuesto ya está bloqueado
    anterior = asignacion.monto if asignacion else CERO
    if monto == anterior:
        raise ValidationError({"monto": "El monto es igual al asignado actualmente."})
    if asignacion is None:
        _validar_centro(centro, p.anio)

    detallado = asignacion.detalle.aggregate(t=Sum("monto"))["t"] or CERO if asignacion else CERO
    if monto < detallado:
        raise ValidationError({
            "monto": f"El departamento ya tiene {detallado:,.2f} detallado por cuenta y mes: "
                     f"reduzca primero el detalle o asigne al menos ese monto."
        })
    disponible = p.monto - (total_distribuido(p) - anterior)
    if monto > disponible:
        raise ValidationError({
            "monto": f"Excede el monto institucional: el saldo disponible para {centro.codigo} es {disponible:,.2f}."
        })

    if monto == 0:
        asignacion.delete()
    elif asignacion is None:
        asignacion = AsignacionPresupuesto.objects.create(
            presupuesto=p, centro_costo=centro, monto=monto, creado_por=usuario, modificado_por=usuario
        )
    else:
        asignacion.monto = monto
        asignacion.modificado_por = usuario
        asignacion.save(update_fields=["monto", "modificado_por", "modificado_en"])

    CambioDistribucion.objects.create(
        presupuesto=p, centro_costo=centro, monto_anterior=anterior, monto_nuevo=monto, motivo=motivo, registrado_por=usuario
    )
    accion = Bitacora.Accion.CREAR if anterior == 0 else Bitacora.Accion.ELIMINAR if monto == 0 else Bitacora.Accion.MODIFICAR
    registrar_evento(
        accion, usuario=usuario, entidad=ENTIDAD, objeto_id=f"{p.anio}/{centro.codigo}",
        descripcion=f"Asignación del presupuesto {p.anio} a {centro.codigo} {centro.nombre}: {anterior:,.2f} → {monto:,.2f}"
        + (f" ({motivo})" if motivo else ""),
        valor_anterior={"centro": centro.codigo, "monto": _t(anterior)},
        valor_nuevo={"centro": centro.codigo, "monto": _t(monto), "motivo": motivo},
        request=request,
    )
    return resumen_distribucion(p)


def _normalizar_filas(filas, centro, anio):
    """[{cuenta, meses: [12]}] → {(cuenta_id, mes): monto} con las validaciones de cuenta, mes y monto."""
    errores, celdas, cuentas = [], {}, {}
    ids = [f["cuenta"].pk for f in filas]
    if len(ids) != len(set(ids)):
        raise ValidationError({"filas": "Cada cuenta debe aparecer una sola vez."})
    for f in filas:
        cuenta = Cuenta.objects.get(pk=f["cuenta"].pk)
        cuentas[cuenta.pk] = cuenta
        meses = f["meses"]
        if len(meses) != MESES:
            errores.append(f"Cuenta {cuenta.codigo}: se esperan 12 meses.")
            continue
        if cuenta.tipo != Cuenta.Tipo.GASTO:
            errores.append(f"Cuenta {cuenta.codigo}: solo se presupuestan cuentas de gasto.")
        if not cuenta.acepta_movimientos:
            errores.append(f"Cuenta {cuenta.codigo}: es de agrupación; use sus cuentas de detalle.")
        if not cuenta.activa:
            errores.append(f"Cuenta {cuenta.codigo}: está inactiva.")
        for mes, valor in enumerate(meses, start=1):
            try:
                monto = _validar_monto_cero(valor)
            except ValidationError as e:
                errores.append(f"Cuenta {cuenta.codigo}, mes {mes}: {' '.join(e.messages)}")
                continue
            if monto and not _vigente_en_mes(centro, anio, mes):
                errores.append(f"Cuenta {cuenta.codigo}, mes {mes}: el centro {centro.codigo} no está vigente ese mes.")
            if monto:
                celdas[(cuenta.pk, mes)] = monto
    if errores:
        raise ValidationError({"filas": errores})
    return celdas


@transaction.atomic
def guardar_detalle(presupuesto, *, usuario, centro, filas, motivo="", request=None):
    """Reemplaza el detalle por cuenta y mes de un departamento; registra cada celda que cambia."""
    p = _bloquear(presupuesto)
    _exigir_editable(p)
    centro = CentroCosto.objects.get(pk=centro.pk)
    asignacion = p.asignaciones.filter(centro_costo=centro).first()  # el presupuesto ya está bloqueado
    if asignacion is None:
        raise ValidationError({"centro": f"Primero asigne un monto anual a {centro.codigo}."})
    motivo = _texto(motivo)
    nuevas = _normalizar_filas(filas, centro, p.anio)
    total = sum(nuevas.values(), CERO)
    if total > asignacion.monto:
        raise ValidationError({
            "filas": [f"El detalle suma {total:,.2f} y excede lo asignado a {centro.codigo} ({asignacion.monto:,.2f})."]
        })

    actuales = {(d.cuenta_id, d.mes): d for d in asignacion.detalle.all()}
    cambios = []
    for clave in sorted(set(actuales) | set(nuevas)):
        antes = actuales[clave].monto if clave in actuales else CERO
        despues = nuevas.get(clave, CERO)
        if antes != despues:
            cambios.append((clave, antes, despues))
    if not cambios:
        return detalle_departamento(p, centro)

    # Primero lo que baja y después lo que sube: los topes de Oracle se verifican sentencia a sentencia.
    for (cuenta_id, mes), antes, despues in sorted(cambios, key=lambda c: c[2] - c[1]):
        if despues == 0:
            actuales[(cuenta_id, mes)].delete()
        elif antes == 0:
            DetallePresupuesto.objects.create(asignacion=asignacion, cuenta_id=cuenta_id, mes=mes, monto=despues)
        else:
            DetallePresupuesto.objects.filter(pk=actuales[(cuenta_id, mes)].pk).update(monto=despues)
    CambioDistribucion.objects.bulk_create([
        CambioDistribucion(
            presupuesto=p, centro_costo=centro, cuenta_id=cuenta_id, mes=mes,
            monto_anterior=antes, monto_nuevo=despues, motivo=motivo, registrado_por=usuario,
        )
        for (cuenta_id, mes), antes, despues in cambios
    ])
    asignacion.modificado_por = usuario
    asignacion.save(update_fields=["modificado_por", "modificado_en"])

    def por_cuenta(celdas):
        codigos = dict(Cuenta.objects.filter(pk__in={c for c, _ in celdas}).values_list("pk", "codigo"))
        salida = defaultdict(lambda: CERO)
        for (cuenta_id, _), monto in celdas.items():
            salida[codigos[cuenta_id]] += monto
        return {k: _t(v) for k, v in sorted(salida.items())}

    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad=ENTIDAD, objeto_id=f"{p.anio}/{centro.codigo}",
        descripcion=f"Detalle por cuenta y mes de {centro.codigo} {centro.nombre} ({p.anio}): {len(cambios)} celda(s)"
        + (f" ({motivo})" if motivo else ""),
        valor_anterior={"total": _t(sum((d.monto for d in actuales.values()), CERO)),
                        "por_cuenta": por_cuenta({k: d.monto for k, d in actuales.items()})},
        valor_nuevo={"total": _t(total), "por_cuenta": por_cuenta(nuevas), "motivo": motivo},
        request=request,
    )
    return detalle_departamento(p, centro)
