"""Proyección de egresos a 30/60/90 días (T5.2): compromisos ciertos.

Fuentes: saldos de cuentas por pagar (en la fecha de pago programada o, si no hay, en el vencimiento) y
egresos programados (planilla, impuestos, alquileres…). Los vencidos se informan aparte: son exigibles ya.
"""
from calendar import monthrange
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .cuentas_por_pagar import _bloquear, _monto, _texto
from .models import CuentaPorPagar, EgresoProgramado, Proveedor

CERO = Decimal("0.00")
HORIZONTE = 90
TRAMOS = (("VENCIDO", None, None), ("D30", 0, 30), ("D60", 31, 60), ("D90", 61, 90))
SEMANAS = 13
PROVEEDORES = "PROVEEDORES"  # categoría de las cuentas por pagar


def _t(m):
    return f"{m + CERO:.2f}"


# =============================================================================
# Programación de pagos (cuentas por pagar)
# =============================================================================

def fecha_de_pago(cxp):
    return cxp.fecha_pago_programada or cxp.fecha_vencimiento


@transaction.atomic
def programar_pago(cxp, *, usuario, fecha_pago_programada, request=None):
    cxp = _bloquear(cxp)
    if cxp.estado not in (CuentaPorPagar.Estado.PENDIENTE, CuentaPorPagar.Estado.PARCIAL):
        raise ValidationError(f"El documento está {cxp.get_estado_display().lower()}: no se programa su pago.")
    if fecha_pago_programada is not None and fecha_pago_programada < cxp.fecha_emision:
        raise ValidationError({"fecha_pago_programada": "La fecha programada no puede ser anterior a la emisión."})
    anterior = cxp.fecha_pago_programada
    if anterior == fecha_pago_programada:
        return cxp
    cxp.fecha_pago_programada = fecha_pago_programada
    cxp.modificado_por = usuario
    cxp.save(update_fields=["fecha_pago_programada", "modificado_por", "modificado_en"])
    texto = lambda f: f.isoformat() if f else None  # noqa: E731
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="cuenta_por_pagar", objeto_id=cxp.pk,
        descripcion=f"Programación de pago de {cxp.numero_documento} ({cxp.proveedor.nombre}): "
        + (f"{fecha_pago_programada:%d/%m/%Y}" if fecha_pago_programada else "según vencimiento"),
        valor_anterior={"fecha_pago_programada": texto(anterior)},
        valor_nuevo={"fecha_pago_programada": texto(fecha_pago_programada)},
        request=request,
    )
    return cxp


# =============================================================================
# Egresos programados
# =============================================================================

CAMPOS_EGRESO = ("concepto", "categoria", "monto", "frecuencia", "fecha_inicio", "fecha_fin", "dia_mes", "proveedor", "activo")


def instantanea_egreso(e):
    return {
        "concepto": e.concepto, "categoria": e.categoria, "monto": f"{e.monto:.2f}", "frecuencia": e.frecuencia,
        "fecha_inicio": e.fecha_inicio.isoformat(), "fecha_fin": e.fecha_fin.isoformat() if e.fecha_fin else None,
        "dia_mes": e.dia_mes, "proveedor": e.proveedor_id, "activo": e.activo,
    }


def _validar_egreso(e):
    e.concepto = _texto(e.concepto)
    if not e.concepto:
        raise ValidationError({"concepto": "Indique el concepto."})
    e.monto = _monto(e.monto)
    if e.frecuencia == EgresoProgramado.Frecuencia.UNICA:
        e.dia_mes, e.fecha_fin = None, None
    elif not e.dia_mes or not 1 <= e.dia_mes <= 31:
        raise ValidationError({"dia_mes": "Indique el día del mes (1 a 31)."})
    if e.fecha_fin and e.fecha_fin < e.fecha_inicio:
        raise ValidationError({"fecha_fin": "La fecha final no puede ser anterior a la inicial."})
    if e.proveedor_id and not Proveedor.objects.filter(pk=e.proveedor_id, activo=True).exists():
        raise ValidationError({"proveedor": "El proveedor está inactivo."})
    e.full_clean(exclude=["creado_por", "modificado_por"])


@transaction.atomic
def crear_egreso_programado(*, usuario, request=None, **datos):
    e = EgresoProgramado(**{c: v for c, v in datos.items() if c in CAMPOS_EGRESO}, creado_por=usuario, modificado_por=usuario)
    _validar_egreso(e)
    e.save()
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="egreso_programado", objeto_id=e.pk,
        descripcion=f"Egreso programado: {e.concepto} ({e.get_frecuencia_display().lower()}, {e.monto:,.2f})",
        valor_nuevo=instantanea_egreso(e), request=request,
    )
    return e


@transaction.atomic
def actualizar_egreso_programado(egreso, *, usuario, datos, request=None):
    desconocidos = set(datos) - set(CAMPOS_EGRESO)
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})
    e = EgresoProgramado.objects.select_for_update().get(pk=egreso.pk)
    antes = instantanea_egreso(e)
    for campo, valor in datos.items():
        setattr(e, campo, valor)
    _validar_egreso(e)
    if instantanea_egreso(e) == antes:
        return e
    e.modificado_por = usuario
    e.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="egreso_programado", objeto_id=e.pk,
        descripcion=f"Modificación del egreso programado {e.concepto}",
        valor_anterior=antes, valor_nuevo=instantanea_egreso(e), request=request,
    )
    return e


@transaction.atomic
def eliminar_egreso_programado(egreso, *, usuario, request=None):
    e = EgresoProgramado.objects.select_for_update().get(pk=egreso.pk)
    antes, pk = instantanea_egreso(e), e.pk
    e.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR, usuario=usuario, entidad="egreso_programado", objeto_id=pk,
        descripcion=f"Baja del egreso programado {antes['concepto']}", valor_anterior=antes, request=request,
    )


def _fecha_mensual(anio, mes, dia):
    return date(anio, mes, min(dia, monthrange(anio, mes)[1]))


def ocurrencias(egreso, desde, hasta):
    """Fechas del egreso entre `desde` y `hasta` (inclusive), dentro de su vigencia."""
    inicio = max(desde, egreso.fecha_inicio)
    fin = min(hasta, egreso.fecha_fin) if egreso.fecha_fin else hasta
    if inicio > fin:
        return []
    if egreso.frecuencia == EgresoProgramado.Frecuencia.UNICA:
        return [egreso.fecha_inicio] if inicio <= egreso.fecha_inicio <= fin else []
    fechas, anio, mes = [], inicio.year, inicio.month
    while date(anio, mes, 1) <= fin:
        f = _fecha_mensual(anio, mes, egreso.dia_mes)
        if inicio <= f <= fin:
            fechas.append(f)
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
    return fechas


def proxima_fecha(egreso, desde):
    if not egreso.activo:
        return None
    fechas = ocurrencias(egreso, desde, desde + timedelta(days=400))
    return fechas[0] if fechas else None


# =============================================================================
# Proyección
# =============================================================================

def tramo_de(fecha_pago, referencia):
    dias = (fecha_pago - referencia).days
    if dias < 0:
        return "VENCIDO"
    for nombre, desde, hasta in TRAMOS[1:]:
        if desde <= dias <= hasta:
            return nombre
    return None  # fuera del horizonte


def egresos_proyectados(fecha, horizonte=HORIZONTE):
    """Lista de egresos (dict) con fecha ≤ fecha + horizonte; incluye los vencidos de cuentas por pagar."""
    limite = fecha + timedelta(days=horizonte)
    items = []
    pendientes = CuentaPorPagar.objects.filter(
        estado__in=[CuentaPorPagar.Estado.PENDIENTE, CuentaPorPagar.Estado.PARCIAL]
    ).filter(
        Q(fecha_pago_programada__lte=limite) | Q(fecha_pago_programada__isnull=True, fecha_vencimiento__lte=limite)
    ).select_related("proveedor")
    for c in pendientes:
        f = fecha_de_pago(c)
        items.append({
            "fecha": f, "origen": "CUENTA_POR_PAGAR", "id": c.pk, "categoria": PROVEEDORES,
            "concepto": f"{c.get_tipo_documento_display()} {c.numero_documento} · {c.concepto}",
            "proveedor": {"id": c.proveedor_id, "nombre": c.proveedor.nombre},
            "monto": c.saldo, "programado": c.fecha_pago_programada is not None,
            "vencimiento": c.fecha_vencimiento,
        })
    for e in EgresoProgramado.objects.filter(activo=True).select_related("proveedor"):
        for f in ocurrencias(e, fecha, limite):
            items.append({
                "fecha": f, "origen": "EGRESO_PROGRAMADO", "id": e.pk, "categoria": e.categoria, "concepto": e.concepto,
                "proveedor": e.proveedor and {"id": e.proveedor_id, "nombre": e.proveedor.nombre},
                "monto": e.monto, "programado": True, "vencimiento": None,
            })
    for i in items:
        i["tramo"] = tramo_de(i["fecha"], fecha)
    items.sort(key=lambda i: (i["fecha"], i["origen"], i["concepto"]))
    return items


def proyeccion_egresos(*, fecha):
    items = egresos_proyectados(fecha)
    nombres_tramo = [t[0] for t in TRAMOS]
    por_tramo = {t: CERO for t in nombres_tramo}
    por_categoria = defaultdict(lambda: {t: CERO for t in nombres_tramo})
    por_proveedor = defaultdict(lambda: CERO)
    semanas = [CERO] * SEMANAS
    nombres_proveedor = {}
    for i in items:
        por_tramo[i["tramo"]] += i["monto"]
        por_categoria[i["categoria"]][i["tramo"]] += i["monto"]
        if i["proveedor"]:
            por_proveedor[i["proveedor"]["id"]] += i["monto"]
            nombres_proveedor[i["proveedor"]["id"]] = i["proveedor"]["nombre"]
        if i["tramo"] != "VENCIDO":
            semana = (i["fecha"] - fecha).days // 7
            if semana < SEMANAS:
                semanas[semana] += i["monto"]

    acumulado, acumulados = por_tramo["VENCIDO"], {}
    for nombre, dias in (("D30", 30), ("D60", 60), ("D90", 90)):
        acumulado += por_tramo[nombre]
        acumulados[str(dias)] = _t(acumulado)

    etiquetas = dict(EgresoProgramado.Categoria.choices) | {PROVEEDORES: "Proveedores (cuentas por pagar)"}
    orden_categorias = [PROVEEDORES, *EgresoProgramado.Categoria.values]
    return {
        "fecha": fecha.isoformat(),
        "horizonte": HORIZONTE,
        "tramos": [
            {"tramo": n, "desde": None if d is None else (fecha + timedelta(days=d)).isoformat(),
             "hasta": None if h is None else (fecha + timedelta(days=h)).isoformat(), "monto": _t(por_tramo[n])}
            for n, d, h in TRAMOS
        ],
        "acumulado": acumulados,
        "total": _t(sum(por_tramo.values(), CERO)),
        "por_categoria": [
            {"categoria": c, "nombre": etiquetas[c], "tramos": {t: _t(v) for t, v in por_categoria[c].items()},
             "total": _t(sum(por_categoria[c].values(), CERO))}
            for c in orden_categorias if c in por_categoria
        ],
        "semanas": [
            {"semana": n + 1, "desde": (fecha + timedelta(days=7 * n)).isoformat(),
             "hasta": (fecha + timedelta(days=7 * n + 6)).isoformat(), "monto": _t(m)}
            for n, m in enumerate(semanas)
        ],
        "proveedores": [
            {"id": pid, "nombre": nombres_proveedor[pid], "monto": _t(m)}
            for pid, m in sorted(por_proveedor.items(), key=lambda kv: (-kv[1], nombres_proveedor[kv[0]]))[:10]
        ],
        "detalle": [
            {**i, "fecha": i["fecha"].isoformat(), "monto": _t(i["monto"]),
             "vencimiento": i["vencimiento"] and i["vencimiento"].isoformat(), "categoria_nombre": etiquetas[i["categoria"]]}
            for i in items
        ],
    }
