"""Reportes segmentados (Bloque 3). Servicios de solo lectura sobre asientos contabilizados."""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from centros_costo.models import CentroCosto, EjecucionProrrateo
from contabilidad.models import Asiento, Cuenta, LineaAsiento

CERO = Decimal("0.00")
SIN_CENTRO = "sin_centro"
TIPOS_RESULTADO = (Cuenta.Tipo.INGRESO, Cuenta.Tipo.GASTO)


def _texto(monto):
    # `+ CERO` normaliza el cero negativo (-0.00).
    return f"{monto + CERO:.2f}"


def _asientos_anulados():
    """Asientos de prorrateos anulados y sus reversiones: se compensan entre sí y no se reportan."""
    anulados = set(
        EjecucionProrrateo.objects.filter(estado=EjecucionProrrateo.Estado.ANULADA).values_list("asiento_id", flat=True)
    )
    return anulados | set(Asiento.objects.filter(reversion_de__in=anulados).values_list("id", flat=True))


def _columnas(centro, desde, hasta):
    """Unidades que forman las columnas y función que ubica cada centro en su columna (o None)."""
    centros = {c.pk: c for c in CentroCosto.objects.all()}
    hijos = defaultdict(list)
    for c in centros.values():
        hijos[c.padre_id].append(c)
    if centro is None:
        columnas = hijos[None]
    elif hijos[centro.pk]:
        columnas = hijos[centro.pk]
    else:
        columnas = [centro]
    columnas = sorted(columnas, key=lambda c: c.codigo)
    ids = {c.pk for c in columnas}
    cache = {}

    def columna_de(centro_id):
        if centro_id not in cache:
            actual = centro_id
            while actual is not None and actual not in ids:
                actual = centros[actual].padre_id
            cache[centro_id] = actual
        return cache[centro_id]

    def vigente_en_rango(c):
        return c.vigente_desde <= hasta and (c.vigente_hasta is None or c.vigente_hasta >= desde)

    ruta = []
    actual = centro
    while actual is not None:
        ruta.insert(0, actual)
        actual = centros.get(actual.padre_id)
    return columnas, columna_de, vigente_en_rango, ruta, hijos


def _agrupador_cuentas(nivel):
    """Ubica cada cuenta en su ancestro del nivel indicado (o en sí misma si es menos profunda)."""
    cuentas = {c["id"]: c for c in Cuenta.objects.values("id", "codigo", "nombre", "nivel", "padre_id")}
    cache = {}

    def grupo_de(cuenta_id):
        if cuenta_id not in cache:
            actual = cuentas[cuenta_id]
            while actual["nivel"] > nivel and actual["padre_id"] is not None:
                actual = cuentas[actual["padre_id"]]
            cache[cuenta_id] = actual
        return cache[cuenta_id]

    return grupo_de


def estado_resultados(*, desde, hasta, centro=None, nivel_cuentas=2):
    """Estado de resultados por centro bajo costeo absorbente (T3.1).

    Columnas: unidades raíz (sin `centro`), subunidades directas de `centro`, o el propio centro si es de detalle.
    Secciones: ingresos, costos directos (asientos de diario y sus reversiones) y costos indirectos
    (asientos de prorrateo vigentes). Resultado neto = ingresos − directos − indirectos.
    """
    if desde > hasta:
        raise ValidationError({"hasta": "La fecha final no puede ser anterior a la inicial."})
    columnas, columna_de, vigente_en_rango, ruta, hijos = _columnas(centro, desde, hasta)
    grupo_de = _agrupador_cuentas(nivel_cuentas)

    filas = (
        LineaAsiento.objects.filter(
            asiento__estado=Asiento.Estado.CONTABILIZADO,
            asiento__fecha__gte=desde,
            asiento__fecha__lte=hasta,
            cuenta__tipo__in=TIPOS_RESULTADO,
        )
        .exclude(asiento_id__in=_asientos_anulados())
        .values("centro_costo_id", "cuenta_id", "cuenta__tipo", "asiento__tipo")
        .annotate(debe=Sum("debe"), haber=Sum("haber"))
    )

    # secciones[clave][id_grupo][columna] = monto
    secciones = {clave: defaultdict(lambda: defaultdict(lambda: CERO)) for clave in ("ingresos", "directos", "indirectos")}
    recibidos = defaultdict(lambda: CERO)
    distribuidos = defaultdict(lambda: CERO)
    grupos = {}
    con_datos = set()
    for f in filas:
        if f["centro_costo_id"] is None:
            if centro is not None:
                continue
            col = SIN_CENTRO
        else:
            col = columna_de(f["centro_costo_id"])
            if col is None:
                continue
        debe, haber = f["debe"] or CERO, f["haber"] or CERO
        grupo = grupo_de(f["cuenta_id"])
        grupos[grupo["id"]] = grupo
        con_datos.add(col)
        if f["cuenta__tipo"] == Cuenta.Tipo.INGRESO:
            secciones["ingresos"][grupo["id"]][col] += haber - debe
        elif f["asiento__tipo"] == Asiento.Tipo.PRORRATEO:
            secciones["indirectos"][grupo["id"]][col] += debe - haber
            recibidos[col] += debe
            distribuidos[col] += haber
        else:
            secciones["directos"][grupo["id"]][col] += debe - haber

    # Columnas: se omiten las unidades no vigentes en el rango que no tienen datos.
    visibles = [c for c in columnas if vigente_en_rango(c) or c.pk in con_datos]
    claves = [c.pk for c in visibles] + ([SIN_CENTRO] if SIN_CENTRO in con_datos else [])

    def vector(valores):
        montos = [valores.get(k, CERO) for k in claves]
        return {"valores": [_texto(m) for m in montos], "total": _texto(sum(montos, CERO))}

    def suma(*por_columna, signos=None):
        signos = signos or [1] * len(por_columna)
        return {k: sum((s * d.get(k, CERO) for s, d in zip(signos, por_columna)), CERO) for k in claves}

    totales, salida = {}, []
    titulos = {"ingresos": "Ingresos", "directos": "Costos y gastos directos", "indirectos": "Costos indirectos asignados"}
    for clave, titulo in titulos.items():
        datos = secciones[clave]
        totales[clave] = suma(*datos.values()) if datos else {k: CERO for k in claves}
        salida.append({
            "clave": clave,
            "titulo": titulo,
            "filas": [
                {"cuenta": {"id": g, "codigo": grupos[g]["codigo"], "nombre": grupos[g]["nombre"]}, **vector(datos[g])}
                for g in sorted(datos, key=lambda g: grupos[g]["codigo"])
            ],
            **vector(totales[clave]),
        })

    resultado_directo = suma(totales["ingresos"], totales["directos"], signos=[1, -1])
    resultado = suma(resultado_directo, totales["indirectos"], signos=[1, -1])
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "nivel_cuentas": nivel_cuentas,
        "centro": {"id": centro.pk, "codigo": centro.codigo, "nombre": centro.nombre} if centro else None,
        "ruta": [{"id": c.pk, "codigo": c.codigo, "nombre": c.nombre} for c in ruta],
        "columnas": [
            {
                "id": c.pk, "codigo": c.codigo, "nombre": c.nombre, "tipo": c.tipo, "tipo_display": c.get_tipo_display(),
                "tiene_subunidades": bool(hijos[c.pk]), "vigente": vigente_en_rango(c),
            }
            for c in visibles
        ]
        + ([{"id": None, "codigo": "", "nombre": "Sin centro", "tipo": None, "tipo_display": "", "tiene_subunidades": False, "vigente": True}]
           if SIN_CENTRO in claves else []),
        "secciones": salida,
        "resultado_directo": vector(resultado_directo),
        "indirectos": {"recibidos": vector(recibidos), "distribuidos": vector(distribuidos)},
        "resultado": vector(resultado),
    }
