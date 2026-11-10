"""Verificación de integridad de la base (T6.1). Solo lectura.

Revisa sobre los datos reales las reglas contables no negociables de CLAUDE.md y la coherencia entre
módulos. Lo usa el comando `verificar_integridad` (antes de un cierre o después de restaurar un respaldo).
Cada verificación devuelve OK, ADVERTENCIA o FALLA con el detalle de los casos encontrados.
"""
from datetime import date
from decimal import Decimal

from django.db import connection
from django.db.models import Count, Max, Sum

from centros_costo.models import EjecucionProrrateo
from contabilidad.models import Asiento, Cuenta, LineaAsiento
from presupuesto.models import AsignacionPresupuesto, DetallePresupuesto, PresupuestoInstitucional, VersionPresupuesto
from tesoreria.models import CuentaPorPagar, PagoCuentaPorPagar

from . import services as reportes

CERO = Decimal("0.00")
OK, ADVERTENCIA, FALLA = "OK", "ADVERTENCIA", "FALLA"
MAX_DETALLE = 10

TRIGGERS = (
    "TRG_BITACORA_INMUTABLE", "TRG_ASIENTO_REGLAS", "TRG_LINEA_ASIENTO_INMUTABLE",
    "TRG_PRESUPUESTO_REGLAS", "TRG_VERSION_PPTO_INMUTABLE", "TRG_ASIG_PPTO_TOPE", "TRG_DET_PPTO_TOPE",
    "TRG_PPTO_TOPE_DISTRIBUIDO", "TRG_ASIG_PPTO_REGLAS", "TRG_DET_PPTO_REGLAS", "TRG_CAMBIO_DIST_INMUTABLE",
    "TRG_CXP_REGLAS", "TRG_PAGO_CXP_REGLAS",
)


def _resultado(codigo, descripcion, problemas, *, estado_si_hay=FALLA, revisados=None):
    return {
        "codigo": codigo,
        "descripcion": descripcion,
        "estado": estado_si_hay if problemas else OK,
        "revisados": revisados,
        "problemas": len(problemas),
        "detalle": problemas[:MAX_DETALLE],
    }


def partida_doble():
    totales = (
        LineaAsiento.objects.filter(asiento__estado=Asiento.Estado.CONTABILIZADO)
        .values("asiento_id", "asiento__ejercicio", "asiento__numero", "asiento__total_debe", "asiento__total_haber")
        .annotate(debe=Sum("debe"), haber=Sum("haber"), lineas=Count("id"))
    )
    problemas, revisados = [], 0
    for t in totales:
        revisados += 1
        if t["debe"] != t["haber"] or t["debe"] != t["asiento__total_debe"] or t["haber"] != t["asiento__total_haber"] or t["lineas"] < 2:
            problemas.append(f"Asiento {t['asiento__ejercicio']}-{t['asiento__numero']:06d}: cargos {t['debe']}, abonos {t['haber']}")
    sin_lineas = Asiento.objects.filter(estado=Asiento.Estado.CONTABILIZADO, lineas__isnull=True).count()
    if sin_lineas:
        problemas.append(f"{sin_lineas} asiento(s) contabilizado(s) sin líneas")
    return _resultado("PARTIDA_DOBLE", "Partida doble en todo asiento contabilizado", problemas, revisados=revisados)


def centro_obligatorio():
    lineas = LineaAsiento.objects.filter(
        asiento__estado=Asiento.Estado.CONTABILIZADO, centro_costo__isnull=True, cuenta__exenta_centro_costo=False,
    ).values("asiento__ejercicio", "asiento__numero").distinct()
    problemas = [f"Asiento {x['asiento__ejercicio']}-{x['asiento__numero']:06d} tiene líneas sin centro de costo" for x in lineas]
    # Solo se admiten en asientos anteriores a T2.1: es advertencia, no falla.
    return _resultado("CENTRO_COSTO", "Líneas que exigen centro de costo y no lo tienen", problemas, estado_si_hay=ADVERTENCIA)


def trazabilidad_prorrateo():
    problemas, revisados = [], 0
    for e in EjecucionProrrateo.objects.exclude(estado=EjecucionProrrateo.Estado.ANULADA).select_related("asiento"):
        revisados += 1
        if e.asiento.estado != Asiento.Estado.CONTABILIZADO:
            problemas.append(f"Prorrateo {e.pk}: su asiento no está contabilizado")
        elif e.asiento.lineas.filter(linea_origen__isnull=True).exists():
            problemas.append(f"Prorrateo {e.pk} (asiento {e.asiento.codigo}): líneas sin referencia al origen")
    return _resultado("PRORRATEO", "Prorrateos vigentes contabilizados y con trazabilidad al origen", problemas, revisados=revisados)


def cuentas_por_pagar():
    pagado = dict(
        PagoCuentaPorPagar.objects.filter(estado=PagoCuentaPorPagar.Estado.VIGENTE)
        .values_list("cuenta_por_pagar_id").annotate(s=Sum("monto"))
    )
    E = CuentaPorPagar.Estado
    problemas, revisados = [], 0
    for c in CuentaPorPagar.objects.select_related("proveedor"):
        revisados += 1
        nombre = f"{c.numero_documento} ({c.proveedor.nombre})"
        if c.estado == E.ANULADA:
            if c.asiento_anulacion_id is None:
                problemas.append(f"{nombre}: anulada sin asiento de reversión")
            continue
        esperado = c.monto_total - pagado.get(c.pk, CERO)
        if c.saldo != esperado:
            problemas.append(f"{nombre}: saldo {c.saldo} ≠ total − pagos ({esperado})")
        estado = E.PAGADA if c.saldo == 0 else E.PENDIENTE if c.saldo == c.monto_total else E.PARCIAL
        if c.estado != estado:
            problemas.append(f"{nombre}: estado {c.estado} y saldo {c.saldo}")
    return _resultado("CUENTAS_POR_PAGAR", "Saldos y estados de cuentas por pagar coherentes con sus pagos", problemas, revisados=revisados)


def presupuesto():
    ultima = dict(VersionPresupuesto.objects.values_list("presupuesto_id").annotate(n=Max("numero")))
    distribuido = dict(AsignacionPresupuesto.objects.values_list("presupuesto_id").annotate(s=Sum("monto")))
    problemas, revisados = [], 0
    for p in PresupuestoInstitucional.objects.all():
        revisados += 1
        version = VersionPresupuesto.objects.filter(presupuesto=p, numero=ultima.get(p.pk)).first()
        if version is None or version.numero != p.version or version.monto != p.monto:
            problemas.append(f"Presupuesto {p.anio}: el monto o la versión no coinciden con la última versión registrada")
        if distribuido.get(p.pk, CERO) > p.monto:
            problemas.append(f"Presupuesto {p.anio}: lo distribuido ({distribuido[p.pk]}) excede el monto institucional ({p.monto})")
    detallado = dict(DetallePresupuesto.objects.values_list("asignacion_id").annotate(s=Sum("monto")))
    for a in AsignacionPresupuesto.objects.select_related("presupuesto", "centro_costo"):
        if detallado.get(a.pk, CERO) > a.monto:
            problemas.append(f"Presupuesto {a.presupuesto.anio}, {a.centro_costo.codigo}: detalle ({detallado[a.pk]}) mayor que lo asignado ({a.monto})")
    return _resultado("PRESUPUESTO", "Presupuesto versionado y topes de distribución", problemas, revisados=revisados)


def resultados_vs_balanza(anio):
    desde, hasta = date(anio, 1, 1), date(anio, 12, 31)
    s = LineaAsiento.objects.filter(
        asiento__estado=Asiento.Estado.CONTABILIZADO, asiento__fecha__gte=desde, asiento__fecha__lte=hasta,
        cuenta__tipo__in=[Cuenta.Tipo.INGRESO, Cuenta.Tipo.GASTO],
    ).aggregate(d=Sum("debe"), h=Sum("haber"))
    balanza = (s["h"] or CERO) - (s["d"] or CERO)
    estado = Decimal(reportes.estado_resultados(desde=desde, hasta=hasta)["resultado"]["total"])
    contribucion = Decimal(reportes.enfoque_contribucion(desde=desde, hasta=hasta)["resultado"])
    problemas = []
    if estado != balanza:
        problemas.append(f"Estado de resultados {anio} ({estado}) ≠ ingresos − gastos de la balanza ({balanza})")
    if contribucion != estado:
        problemas.append(f"Enfoque de contribución {anio} ({contribucion}) ≠ costeo absorbente ({estado})")
    return _resultado(
        "RESULTADOS", f"Reportes segmentados {anio} cuadran con la balanza (resultado {balanza:,.2f})", problemas
    )


def triggers():
    if connection.vendor != "oracle":
        return _resultado("TRIGGERS", "Triggers de reglas en Oracle (no aplica fuera de Oracle)", [])
    with connection.cursor() as cursor:
        cursor.execute("select trigger_name, status from user_triggers")
        existentes = dict(cursor.fetchall())
    problemas = [
        f"{t}: {'no existe' if t not in existentes else 'deshabilitado'}"
        for t in TRIGGERS if existentes.get(t) != "ENABLED"
    ]
    return _resultado("TRIGGERS", f"Triggers de reglas en Oracle ({len(TRIGGERS)} esperados, habilitados)", problemas,
                      revisados=len(TRIGGERS))


def verificar(anio=None):
    anio = anio or date.today().year
    return [
        partida_doble(),
        centro_obligatorio(),
        trazabilidad_prorrateo(),
        cuentas_por_pagar(),
        presupuesto(),
        resultados_vs_balanza(anio),
        triggers(),
    ]


def hay_fallas(resultados):
    return any(r["estado"] == FALLA for r in resultados)
