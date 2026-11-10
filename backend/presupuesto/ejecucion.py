"""Ejecución vs. presupuesto y alertas de desviación (T4.3). Solo lectura.

Presupuesto: detalle por centro, cuenta y mes (T4.2) y asignación anual del departamento.
Ejecución: cargos − abonos de cuentas de gasto en asientos contabilizados del ejercicio, sin prorrateos
(ni sus reversiones): se mide el gasto propio que controla el responsable del departamento.
"""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Q, Sum
from django.utils import timezone

from centros_costo.models import CentroCosto
from contabilidad.models import Asiento, Cuenta, LineaAsiento

from .models import DetallePresupuesto

CERO = Decimal("0.00")
MESES = range(1, 13)
UMBRAL_POR_DEFECTO = Decimal("10")

GRAVEDAD = {"CRITICA": 3, "ADVERTENCIA": 2, "INFORMATIVA": 1}
EN_RANGO = (0, "EN_RANGO")  # estado = tipo de la alerta más grave del departamento


def _t(m):
    return f"{m + CERO:.2f}"


def _pct(parte, base):
    return f"{(parte * 100 / base).quantize(CERO) + CERO:.2f}" if base else None


def corte_por_defecto(anio):
    hoy = timezone.localdate()
    return hoy.month if hoy.year == anio else 12


def _ejecucion(anio):
    """{(centro_id, cuenta_id, mes): monto} y gasto sin centro, del ejercicio."""
    filas = (
        LineaAsiento.objects.filter(
            asiento__estado=Asiento.Estado.CONTABILIZADO,
            asiento__periodo__anio=anio,
            cuenta__tipo=Cuenta.Tipo.GASTO,
        )
        .exclude(Q(asiento__tipo=Asiento.Tipo.PRORRATEO) | Q(asiento__reversion_de__tipo=Asiento.Tipo.PRORRATEO))
        .values("centro_costo_id", "cuenta_id", "asiento__periodo__mes")
        .annotate(debe=Sum("debe"), haber=Sum("haber"))
    )
    celdas, sin_centro = defaultdict(lambda: CERO), defaultdict(lambda: CERO)
    for f in filas:
        monto = (f["debe"] or CERO) - (f["haber"] or CERO)
        mes = f["asiento__periodo__mes"]
        if f["centro_costo_id"] is None:
            sin_centro[mes] += monto
        else:
            celdas[(f["centro_costo_id"], f["cuenta_id"], mes)] += monto
    return celdas, sin_centro


def _presupuesto(presupuesto):
    celdas = defaultdict(lambda: CERO)
    for d in DetallePresupuesto.objects.filter(asignacion__presupuesto=presupuesto).values(
        "asignacion__centro_costo_id", "cuenta_id", "mes", "monto"
    ):
        celdas[(d["asignacion__centro_costo_id"], d["cuenta_id"], d["mes"])] += d["monto"]
    asignado = {a.centro_costo_id: a.monto for a in presupuesto.asignaciones.all()}
    return celdas, asignado


class _Acumulado:
    """Presupuesto y ejecución por mes de una unidad (institución, departamento o cuenta)."""

    def __init__(self):
        self.ppto = defaultdict(lambda: CERO)
        self.ejec = defaultdict(lambda: CERO)

    def al_corte(self, corte):
        return (sum((self.ppto[m] for m in MESES if m <= corte), CERO),
                sum((self.ejec[m] for m in MESES if m <= corte), CERO))

    def anual_presupuestado(self):
        return sum(self.ppto.values(), CERO)

    def con_datos(self):
        return any(self.ppto.values()) or any(self.ejec.values())


def _medidas(ppto_corte, ejec_corte, anual):
    return {
        "presupuesto_anual": _t(anual),
        "presupuesto_al_corte": _t(ppto_corte),
        "ejecutado_al_corte": _t(ejec_corte),
        "variacion": _t(ppto_corte - ejec_corte),
        "porcentaje_ejecucion": _pct(ejec_corte, ppto_corte),
        "porcentaje_anual": _pct(ejec_corte, anual),
        "disponible_anual": _t(anual - ejec_corte),
    }


def _serie_mensual(acc):
    salida, ppto_acum, ejec_acum = [], CERO, CERO
    for m in MESES:
        ppto_acum += acc.ppto[m]
        ejec_acum += acc.ejec[m]
        salida.append({
            "mes": m, "presupuesto": _t(acc.ppto[m]), "ejecutado": _t(acc.ejec[m]),
            "presupuesto_acumulado": _t(ppto_acum), "ejecutado_acumulado": _t(ejec_acum),
            "variacion_acumulada": _t(ppto_acum - ejec_acum),
        })
    return salida


def _mas_grave(actual, nueva):
    """La alerta de mayor gravedad; a igual gravedad se conserva la primera (la del departamento)."""
    return nueva if nueva[0] > actual[0] else actual


def _centro_json(c):
    return {"id": c.pk, "codigo": c.codigo, "nombre": c.nombre}


def ejecucion_presupuesto(presupuesto, *, corte=None, umbral=None, centro=None):
    anio = presupuesto.anio
    corte = corte or corte_por_defecto(anio)
    umbral = UMBRAL_POR_DEFECTO if umbral is None else Decimal(umbral)
    if not 1 <= corte <= 12:
        raise ValidationError({"corte": "El mes de corte debe estar entre 1 y 12."})
    if not 0 <= umbral <= 100:
        raise ValidationError({"umbral": "El umbral debe estar entre 0 y 100 %."})
    tope, piso = 100 + umbral, 100 - umbral

    ppto, asignado = _presupuesto(presupuesto)
    ejec, sin_centro = _ejecucion(anio)

    por_centro = defaultdict(_Acumulado)
    por_cuenta = defaultdict(_Acumulado)  # (centro, cuenta)
    institucion = _Acumulado()
    for (c, cuenta, mes), monto in ppto.items():
        por_centro[c].ppto[mes] += monto
        por_cuenta[(c, cuenta)].ppto[mes] += monto
        institucion.ppto[mes] += monto
    for (c, cuenta, mes), monto in ejec.items():
        por_centro[c].ejec[mes] += monto
        por_cuenta[(c, cuenta)].ejec[mes] += monto
        institucion.ejec[mes] += monto

    ids_centros = set(asignado) | {c for c, acc in por_centro.items() if acc.con_datos()}
    centros = {c.pk: c for c in CentroCosto.objects.filter(pk__in=ids_centros)}
    cuentas = {c.pk: c for c in Cuenta.objects.filter(pk__in={k[1] for k in por_cuenta})}

    alertas, departamentos = [], []

    def alerta(nivel, tipo, c, mensaje, cuenta=None, ppto_corte=CERO, ejec_corte=CERO):
        alertas.append({
            "nivel": nivel, "tipo": tipo, "centro": _centro_json(c),
            "cuenta": cuenta and {"id": cuenta.pk, "codigo": cuenta.codigo, "nombre": cuenta.nombre},
            "mensaje": mensaje, "presupuesto_al_corte": _t(ppto_corte), "ejecutado_al_corte": _t(ejec_corte),
            "porcentaje_ejecucion": _pct(ejec_corte, ppto_corte),
        })
        return (GRAVEDAD[nivel], tipo)

    for cid in sorted(ids_centros, key=lambda i: centros[i].codigo):
        c, acc = centros[cid], por_centro[cid]
        ppto_corte, ejec_corte = acc.al_corte(corte)
        anual = asignado.get(cid, CERO)
        detallado = acc.anual_presupuestado() > 0
        gravedad = EN_RANGO
        if cid not in asignado:
            if ejec_corte > 0:
                gravedad = alerta("ADVERTENCIA", "SIN_PRESUPUESTO", c,
                                  f"{c.codigo} {c.nombre} gastó {ejec_corte:,.2f} sin presupuesto asignado.",
                                  ejec_corte=ejec_corte)
        elif ejec_corte > anual:
            gravedad = alerta("CRITICA", "SOBREGIRO", c,
                              f"{c.codigo} {c.nombre} superó su presupuesto anual ({anual:,.2f}) en {ejec_corte - anual:,.2f}.",
                              ppto_corte=anual, ejec_corte=ejec_corte)
        elif ppto_corte > 0 and ejec_corte * 100 > ppto_corte * tope:
            gravedad = alerta("ADVERTENCIA", "DESVIACION", c,
                              f"{c.codigo} {c.nombre} ejecutó {_pct(ejec_corte, ppto_corte)} % de lo presupuestado al corte.",
                              ppto_corte=ppto_corte, ejec_corte=ejec_corte)
        elif ppto_corte > 0 and ejec_corte * 100 < ppto_corte * piso:
            gravedad = alerta("INFORMATIVA", "SUBEJECUCION", c,
                              f"{c.codigo} {c.nombre} ejecutó solo {_pct(ejec_corte, ppto_corte)} % de lo presupuestado al corte.",
                              ppto_corte=ppto_corte, ejec_corte=ejec_corte)

        # Alertas por cuenta (solo en departamentos con asignación y detalle).
        if cid in asignado and detallado:
            for (cc, cuenta_id), acc_cuenta in sorted(por_cuenta.items(), key=lambda kv: cuentas[kv[0][1]].codigo):
                if cc != cid:
                    continue
                cuenta = cuentas[cuenta_id]
                p_c, e_c = acc_cuenta.al_corte(corte)
                if e_c > 0 and p_c == 0:
                    gravedad = _mas_grave(gravedad, alerta(
                        "ADVERTENCIA", "SIN_PRESUPUESTO", c,
                        f"{c.codigo}: la cuenta {cuenta.codigo} {cuenta.nombre} tiene gasto ({e_c:,.2f}) sin presupuesto al corte.",
                        cuenta=cuenta, ejec_corte=e_c))
                elif p_c > 0 and e_c * 100 > p_c * tope:
                    gravedad = _mas_grave(gravedad, alerta(
                        "ADVERTENCIA", "DESVIACION", c,
                        f"{c.codigo}: la cuenta {cuenta.codigo} {cuenta.nombre} ejecutó {_pct(e_c, p_c)} % de lo presupuestado al corte.",
                        cuenta=cuenta, ppto_corte=p_c, ejec_corte=e_c))

        departamentos.append({
            "centro": _centro_json(c),
            "con_asignacion": cid in asignado,
            **_medidas(ppto_corte, ejec_corte, anual),
            "estado": gravedad[1],
        })

    alertas.sort(key=lambda a: (-GRAVEDAD[a["nivel"]], a["centro"]["codigo"], a["cuenta"]["codigo"] if a["cuenta"] else ""))

    ppto_corte, ejec_corte = institucion.al_corte(corte)
    total_asignado = sum(asignado.values(), CERO)
    salida = {
        "presupuesto": {"id": presupuesto.pk, "anio": anio, "estado": presupuesto.estado,
                        "estado_display": presupuesto.get_estado_display(), "monto_institucional": _t(presupuesto.monto)},
        "corte": corte,
        "umbral": f"{umbral:.2f}",
        "totales": _medidas(ppto_corte, ejec_corte, total_asignado),
        "departamentos": departamentos,
        "alertas": alertas,
        "resumen_alertas": {n: sum(1 for a in alertas if a["nivel"] == n) for n in GRAVEDAD},
        "sin_centro": _t(sum((v for m, v in sin_centro.items() if m <= corte), CERO)),
        "mensual": _serie_mensual(institucion),
        "centro": None,
    }

    if centro is not None:
        acc = por_centro.get(centro.pk, _Acumulado())
        filas = []
        for (cc, cuenta_id), acc_cuenta in por_cuenta.items():
            if cc != centro.pk or not acc_cuenta.con_datos():
                continue
            p_c, e_c = acc_cuenta.al_corte(corte)
            cuenta = cuentas[cuenta_id]
            filas.append({"cuenta": {"id": cuenta.pk, "codigo": cuenta.codigo, "nombre": cuenta.nombre},
                          **_medidas(p_c, e_c, acc_cuenta.anual_presupuestado())})
        salida["centro"] = {
            **_centro_json(centro),
            "cuentas": sorted(filas, key=lambda f: f["cuenta"]["codigo"]),
            "mensual": _serie_mensual(acc),
        }
    return salida
