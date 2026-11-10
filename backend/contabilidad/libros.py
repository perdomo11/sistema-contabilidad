"""Servicios de los libros contables (T1.4): diario, mayor y balanza de comprobación.

Solo lectura y solo sobre asientos CONTABILIZADOS. Se separa de `services.py`
para no mezclar consultas de reporte con las reglas de registro.
"""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, Sum

from .models import Asiento, Cuenta, LineaAsiento

CERO = Decimal("0.00")


def _validar_rango(desde, hasta):
    if desde > hasta:
        raise ValidationError({"hasta": "La fecha final no puede ser anterior a la inicial."})


def _lineas_contabilizadas():
    return LineaAsiento.objects.filter(asiento__estado=Asiento.Estado.CONTABILIZADO)


def _sumas_por_cuenta(lineas):
    """{cuenta_id: (debe, haber)}"""
    return {
        fila["cuenta_id"]: (fila["debe"] or CERO, fila["haber"] or CERO)
        for fila in lineas.values("cuenta_id").annotate(debe=Sum("debe"), haber=Sum("haber"))
    }


def _texto(monto):
    # `+ CERO` normaliza el cero negativo (-0.00) que produce multiplicar por -1.
    return f"{monto + CERO:.2f}"


def _descendientes(cuenta_id):
    """Ids de la cuenta y de todas sus subcuentas (recorriendo el árbol, no por prefijo)."""
    hijos = defaultdict(list)
    for id_, padre_id in Cuenta.objects.values_list("id", "padre_id"):
        if padre_id is not None:
            hijos[padre_id].append(id_)
    resultado, pendientes = [], [cuenta_id]
    while pendientes:
        actual = pendientes.pop()
        resultado.append(actual)
        pendientes.extend(hijos[actual])
    return resultado


# --- Libro diario ------------------------------------------------------------

def libro_diario(*, desde, hasta):
    """Devuelve (queryset de asientos con líneas, totales del rango)."""
    _validar_rango(desde, hasta)
    asientos = (
        Asiento.objects.filter(estado=Asiento.Estado.CONTABILIZADO, fecha__gte=desde, fecha__lte=hasta)
        .select_related("reversion_de")
        .prefetch_related(
            Prefetch(
                "lineas",
                queryset=LineaAsiento.objects.select_related("cuenta", "centro_costo", "linea_origen__asiento").order_by(
                    "numero_linea"
                ),
            )
        )
        .order_by("fecha", "ejercicio", "numero")
    )
    sumas = _lineas_contabilizadas().filter(asiento__fecha__gte=desde, asiento__fecha__lte=hasta).aggregate(
        debe=Sum("debe"), haber=Sum("haber")
    )
    totales = {"debe": _texto(sumas["debe"] or CERO), "haber": _texto(sumas["haber"] or CERO)}
    return asientos, totales


# --- Libro mayor -------------------------------------------------------------

def libro_mayor(*, cuenta, desde, hasta):
    _validar_rango(desde, hasta)
    signo = 1 if cuenta.naturaleza == Cuenta.Naturaleza.DEUDORA else -1
    base = _lineas_contabilizadas().filter(cuenta_id__in=_descendientes(cuenta.pk))

    previo = base.filter(asiento__fecha__lt=desde).aggregate(debe=Sum("debe"), haber=Sum("haber"))
    saldo_inicial = signo * ((previo["debe"] or CERO) - (previo["haber"] or CERO))

    movimientos, saldo = [], saldo_inicial
    total_debe = total_haber = CERO
    lineas = (
        base.filter(asiento__fecha__gte=desde, asiento__fecha__lte=hasta)
        .select_related("asiento", "cuenta", "centro_costo")
        .order_by("asiento__fecha", "asiento__ejercicio", "asiento__numero", "numero_linea")
    )
    for linea in lineas:
        saldo += signo * (linea.debe - linea.haber)
        total_debe += linea.debe
        total_haber += linea.haber
        movimientos.append(
            {
                "fecha": linea.asiento.fecha.isoformat(),
                "asiento_id": linea.asiento_id,
                "asiento_codigo": linea.asiento.codigo,
                "concepto": linea.asiento.concepto,
                "descripcion": linea.descripcion,
                "cuenta_codigo": linea.cuenta.codigo,
                "cuenta_nombre": linea.cuenta.nombre,
                "centro_codigo": linea.centro_costo.codigo if linea.centro_costo_id else None,
                "debe": _texto(linea.debe),
                "haber": _texto(linea.haber),
                "saldo": _texto(saldo),
            }
        )

    return {
        "cuenta": {
            "id": cuenta.pk,
            "codigo": cuenta.codigo,
            "nombre": cuenta.nombre,
            "naturaleza": cuenta.naturaleza,
            "acepta_movimientos": cuenta.acepta_movimientos,
        },
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "saldo_inicial": _texto(saldo_inicial),
        "movimientos": movimientos,
        "totales": {"debe": _texto(total_debe), "haber": _texto(total_haber)},
        "saldo_final": _texto(saldo),
    }


# --- Balanza de comprobación -------------------------------------------------

def _columnas(saldo):
    """Saldo (cargos − abonos) → (deudor, acreedor)."""
    return (saldo, CERO) if saldo >= 0 else (CERO, -saldo)


def balanza_comprobacion(*, desde, hasta, nivel=None, incluir_sin_movimiento=False):
    _validar_rango(desde, hasta)
    cuentas = list(
        Cuenta.objects.order_by("codigo").values(
            "id", "codigo", "nombre", "nivel", "padre_id", "tipo", "naturaleza", "acepta_movimientos", "activa"
        )
    )
    previo = _sumas_por_cuenta(_lineas_contabilizadas().filter(asiento__fecha__lt=desde))
    rango = _sumas_por_cuenta(
        _lineas_contabilizadas().filter(asiento__fecha__gte=desde, asiento__fecha__lte=hasta)
    )

    # Acumulados por cuenta: [saldo inicial (D−H), cargos, abonos]; luego se suben al padre.
    acumulado = {}
    for c in cuentas:
        d0, h0 = previo.get(c["id"], (CERO, CERO))
        d1, h1 = rango.get(c["id"], (CERO, CERO))
        acumulado[c["id"]] = [d0 - h0, d1, h1]
    for c in sorted(cuentas, key=lambda x: x["nivel"], reverse=True):
        if c["padre_id"] is not None:
            padre = acumulado[c["padre_id"]]
            for i, valor in enumerate(acumulado[c["id"]]):
                padre[i] += valor

    filas = []
    totales = dict.fromkeys(
        ("inicial_deudor", "inicial_acreedor", "cargos", "abonos", "final_deudor", "final_acreedor"), CERO
    )
    for c in cuentas:
        inicial, cargos, abonos = acumulado[c["id"]]
        final = inicial + cargos - abonos
        ini_d, ini_a = _columnas(inicial)
        fin_d, fin_a = _columnas(final)
        valores = {
            "inicial_deudor": ini_d,
            "inicial_acreedor": ini_a,
            "cargos": cargos,
            "abonos": abonos,
            "final_deudor": fin_d,
            "final_acreedor": fin_a,
        }
        # Los totales se calculan sobre cuentas de detalle (las de agrupación ya las contienen).
        if c["acepta_movimientos"]:
            for clave, valor in valores.items():
                totales[clave] += valor
        if nivel and c["nivel"] > nivel:
            continue
        if not incluir_sin_movimiento and not (inicial or cargos or abonos):
            continue
        filas.append(
            {
                "id": c["id"],
                "codigo": c["codigo"],
                "nombre": c["nombre"],
                "nivel": c["nivel"],
                "tipo": c["tipo"],
                "acepta_movimientos": c["acepta_movimientos"],
                "activa": c["activa"],
                **{clave: _texto(valor) for clave, valor in valores.items()},
            }
        )

    cuadra = (
        totales["inicial_deudor"] == totales["inicial_acreedor"]
        and totales["cargos"] == totales["abonos"]
        and totales["final_deudor"] == totales["final_acreedor"]
    )
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "nivel": nivel,
        "filas": filas,
        "totales": {clave: _texto(valor) for clave, valor in totales.items()},
        "cuadra": cuadra,
    }
