"""Dashboard de tesorería (T5.4): compone los servicios de T5.1, T5.2 y T5.3 (no recalcula nada propio)."""
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from . import flujo
from .cuentas_por_pagar import resumen_cuentas_por_pagar
from .proyeccion import proyeccion_egresos

MESES_HISTORIA = 6
DIAS_PROXIMOS_PAGOS = 7


def _restar_meses(fecha, meses):
    """Primer día del mes que está `meses` antes de `fecha` (negativo = después)."""
    anio, mes = divmod(fecha.year * 12 + fecha.month - 1 - meses, 12)
    return date(anio, mes + 1, 1)


def _mensual_completo(desde, mensual):
    """Serie de MESES_HISTORIA meses desde `desde`, con ceros en los meses sin movimientos."""
    por_mes = {(m["anio"], m["mes"]): m for m in mensual}
    salida, actual = [], desde
    for _ in range(MESES_HISTORIA):
        m = por_mes.get((actual.year, actual.month))
        salida.append({"anio": actual.year, "mes": actual.month,
                       "entradas": m["entradas"] if m else "0.00", "salidas": m["salidas"] if m else "0.00",
                       "neto": m["neto"] if m else "0.00"})
        actual = _restar_meses(actual, -1)
    return salida


def dashboard_tesoreria(*, fecha):
    egresos = proyeccion_egresos(fecha=fecha)
    limite = fecha + timedelta(days=DIAS_PROXIMOS_PAGOS)
    proximos = [d for d in egresos["detalle"] if d["tramo"] == "VENCIDO" or d["fecha"] <= limite.isoformat()]

    salida = {
        "fecha": fecha.isoformat(),
        "cuentas_por_pagar": resumen_cuentas_por_pagar(fecha=fecha),
        "egresos": {k: egresos[k] for k in ("tramos", "acumulado", "total", "por_categoria")},
        "proximos_pagos": proximos[:12],
        "proximos_pagos_total": len(proximos),
        "flujo": None,
        "flujo_mensual": None,
        "aviso_flujo": None,
    }
    try:
        proyectado = flujo.flujo_proyectado(fecha=fecha)
        desde = _restar_meses(fecha, MESES_HISTORIA - 1)
        real = flujo.flujo_efectivo(desde=desde, hasta=fecha)
    except ValidationError as e:
        salida["aviso_flujo"] = " ".join(e.messages)
        return salida
    salida["flujo"] = {
        k: proyectado[k]
        for k in ("saldo_actual", "saldo_minimo", "saldo_proyectado", "saldo_minimo_proyectado", "entradas_diarias", "alertas", "semanas")
    }
    salida["flujo_mensual"] = _mensual_completo(desde, real["mensual"])
    return salida
