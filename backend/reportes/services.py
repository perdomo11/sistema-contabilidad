"""Reportes segmentados (Bloque 3). Servicios de solo lectura sobre asientos contabilizados.

Los tres reportes parten del mismo conjunto de datos (`_movimientos`), como pide la sección 2.6 del
documento base: estado de resultados absorbente (T3.1), enfoque de contribución (T3.2) e indicadores (T3.3).
"""
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum

from centros_costo.models import CentroCosto, EjecucionProrrateo
from contabilidad.models import Asiento, Cuenta, LineaAsiento
from contabilidad.services import clasificacion_resultados

CERO = Decimal("0.00")
SIN_CENTRO = "sin_centro"
TIPOS_RESULTADO = (Cuenta.Tipo.INGRESO, Cuenta.Tipo.GASTO)
R = Cuenta.Rubro


def _texto(monto):
    # `+ CERO` normaliza el cero negativo (-0.00).
    return f"{monto + CERO:.2f}"


def _porcentaje(parte, base):
    return f"{(parte * 100 / base).quantize(CERO) + CERO:.2f}" if base else None


# =============================================================================
# Base común: columnas (unidades) y movimientos agregados
# =============================================================================

def _asientos_anulados():
    """Asientos de prorrateos anulados y sus reversiones: se compensan entre sí y no se reportan."""
    anulados = set(
        EjecucionProrrateo.objects.filter(estado=EjecucionProrrateo.Estado.ANULADA).values_list("asiento_id", flat=True)
    )
    return anulados | set(Asiento.objects.filter(reversion_de__in=anulados).values_list("id", flat=True))


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


class _Segmentos:
    """Columnas del reporte y movimientos de resultado del rango, ya ubicados en su columna.

    Columnas: unidades raíz (sin `centro`), subunidades directas de `centro`, o el propio centro si es de
    detalle. Cada columna consolida a todas sus subunidades (sección 2.5). Las líneas sin centro van a
    `SIN_CENTRO` solo en la vista general.
    """

    def __init__(self, *, desde, hasta, centro=None, nivel_cuentas=2):
        if desde > hasta:
            raise ValidationError({"hasta": "La fecha final no puede ser anterior a la inicial."})
        self.desde, self.hasta, self.centro, self.nivel_cuentas = desde, hasta, centro, nivel_cuentas
        centros = {c.pk: c for c in CentroCosto.objects.all()}
        self.hijos = defaultdict(list)
        for c in centros.values():
            self.hijos[c.padre_id].append(c)
        if centro is None:
            columnas = self.hijos[None]
        elif self.hijos[centro.pk]:
            columnas = self.hijos[centro.pk]
        else:
            columnas = [centro]
        columnas = sorted(columnas, key=lambda c: c.codigo)
        ids = {c.pk for c in columnas}

        ubicacion = {}

        def columna_de(centro_id):
            if centro_id not in ubicacion:
                actual = centro_id
                while actual is not None and actual not in ids:
                    actual = centros[actual].padre_id
                ubicacion[centro_id] = actual
            return ubicacion[centro_id]

        self.ruta = []
        actual = centro
        while actual is not None:
            self.ruta.insert(0, actual)
            actual = centros.get(actual.padre_id)

        grupo_de = _agrupador_cuentas(nivel_cuentas)
        clasificacion = clasificacion_resultados()
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
        self.movimientos, con_datos = [], set()
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
            es_ingreso = f["cuenta__tipo"] == Cuenta.Tipo.INGRESO
            con_datos.add(col)
            self.movimientos.append({
                "columna": col,
                "grupo": grupo_de(f["cuenta_id"]),
                "es_ingreso": es_ingreso,
                "indirecto": f["asiento__tipo"] == Asiento.Tipo.PRORRATEO,
                "debe": debe,
                "haber": haber,
                # Monto con el signo natural: ingresos = abonos − cargos; gastos = cargos − abonos.
                "monto": haber - debe if es_ingreso else debe - haber,
                **clasificacion[f["cuenta_id"]],
            })

        def vigente(c):
            return c.vigente_desde <= hasta and (c.vigente_hasta is None or c.vigente_hasta >= desde)

        # Se omiten las unidades no vigentes en el rango que no tienen datos.
        self.columnas = [c for c in columnas if vigente(c) or c.pk in con_datos]
        self._vigente = vigente
        self.hay_sin_centro = SIN_CENTRO in con_datos

    def claves(self, con_sin_centro=True):
        return [c.pk for c in self.columnas] + ([SIN_CENTRO] if con_sin_centro and self.hay_sin_centro else [])

    def describir_columnas(self, con_sin_centro=True):
        salida = [
            {
                "id": c.pk, "codigo": c.codigo, "nombre": c.nombre, "tipo": c.tipo, "tipo_display": c.get_tipo_display(),
                "tiene_subunidades": bool(self.hijos[c.pk]), "vigente": self._vigente(c),
            }
            for c in self.columnas
        ]
        if con_sin_centro and self.hay_sin_centro:
            salida.append({"id": None, "codigo": "", "nombre": "Sin centro", "tipo": None, "tipo_display": "",
                           "tiene_subunidades": False, "vigente": True})
        return salida

    def encabezado(self):
        c = self.centro
        return {
            "desde": self.desde.isoformat(),
            "hasta": self.hasta.isoformat(),
            "nivel_cuentas": self.nivel_cuentas,
            "centro": {"id": c.pk, "codigo": c.codigo, "nombre": c.nombre} if c else None,
            "ruta": [{"id": n.pk, "codigo": n.codigo, "nombre": n.nombre} for n in self.ruta],
        }


class _Acumulador:
    """Sumas por fila (clave) y columna, con salida como vectores alineados a las columnas."""

    def __init__(self, claves):
        self.claves = claves
        self.datos = defaultdict(lambda: defaultdict(lambda: CERO))
        self.etiquetas = {}

    def sumar(self, fila, columna, monto, etiqueta=None):
        self.datos[fila][columna] += monto
        if etiqueta is not None:
            self.etiquetas[fila] = etiqueta

    def total(self):
        return {k: sum((d.get(k, CERO) for d in self.datos.values()), CERO) for k in self.claves}

    def vector(self, valores):
        montos = [valores.get(k, CERO) for k in self.claves]
        return {"valores": [_texto(m) for m in montos], "total": _texto(sum(montos, CERO))}

    def filas(self, orden):
        return [{**self.etiquetas[f], **self.vector(self.datos[f])} for f in sorted(self.datos, key=orden)]


def _combinar(claves, *pares):
    """Suma de vectores por columna: pares = (signo, {columna: monto})."""
    return {k: sum((s * d.get(k, CERO) for s, d in pares), CERO) for k in claves}


def _vector(claves, valores):
    montos = [valores.get(k, CERO) for k in claves]
    return {"valores": [_texto(m) for m in montos], "total": _texto(sum(montos, CERO))}


def _etiqueta_cuenta(grupo, **extra):
    return {"cuenta": {"id": grupo["id"], "codigo": grupo["codigo"], "nombre": grupo["nombre"]}, **extra}


# =============================================================================
# T3.1: estado de resultados por centro (costeo absorbente)
# =============================================================================

def estado_resultados(*, desde, hasta, centro=None, nivel_cuentas=2):
    """Ingresos, costos directos (asientos de diario y sus reversiones) y costos indirectos (prorrateos
    vigentes). Resultado neto = ingresos − directos − indirectos."""
    seg = _Segmentos(desde=desde, hasta=hasta, centro=centro, nivel_cuentas=nivel_cuentas)
    claves = seg.claves()
    secciones = {clave: _Acumulador(claves) for clave in ("ingresos", "directos", "indirectos")}
    recibidos, distribuidos = defaultdict(lambda: CERO), defaultdict(lambda: CERO)
    for m in seg.movimientos:
        g, col = m["grupo"], m["columna"]
        if m["es_ingreso"]:
            secciones["ingresos"].sumar(g["id"], col, m["monto"], _etiqueta_cuenta(g))
        elif m["indirecto"]:
            secciones["indirectos"].sumar(g["id"], col, m["monto"], _etiqueta_cuenta(g))
            recibidos[col] += m["debe"]
            distribuidos[col] += m["haber"]
        else:
            secciones["directos"].sumar(g["id"], col, m["monto"], _etiqueta_cuenta(g))

    titulos = {"ingresos": "Ingresos", "directos": "Costos y gastos directos", "indirectos": "Costos indirectos asignados"}
    totales = {clave: acc.total() for clave, acc in secciones.items()}
    salida = []
    for clave, titulo in titulos.items():
        acc = secciones[clave]
        filas = acc.filas(lambda f, acc=acc: acc.etiquetas[f]["cuenta"]["codigo"])
        salida.append({"clave": clave, "titulo": titulo, "filas": filas, **_vector(claves, totales[clave])})

    resultado_directo = _combinar(claves, (1, totales["ingresos"]), (-1, totales["directos"]))
    resultado = _combinar(claves, (1, resultado_directo), (-1, totales["indirectos"]))
    return {
        **seg.encabezado(),
        "columnas": seg.describir_columnas(),
        "secciones": salida,
        "resultado_directo": _vector(claves, resultado_directo),
        "indirectos": {"recibidos": _vector(claves, recibidos), "distribuidos": _vector(claves, distribuidos)},
        "resultado": _vector(claves, resultado),
    }


# =============================================================================
# T3.2: enfoque de contribución (Tabla 1 del documento base)
# =============================================================================

def _categoria_contribucion(m):
    """Ubica un gasto en la estructura de la Tabla 1."""
    if m["indirecto"]:
        return "no_controlables"  # asignado por prorrateo: el responsable no lo controla
    if m["comportamiento_costo"] == Cuenta.Comportamiento.VARIABLE:
        return "variables"
    return "fijos_controlables" if m["controlable"] else "no_controlables"


def enfoque_contribucion(*, desde, hasta, centro=None, nivel_cuentas=2):
    """Estado de resultados segmentado bajo enfoque de contribución.

    Ingresos − costos variables directos = margen de contribución; − costos fijos controlables = margen
    controlable; − costos fijos asignados no controlables (directos no controlables y prorrateos) =
    resultado del segmento. Los costos comunes no asignados (movimientos sin centro) solo restan en el total.
    """
    seg = _Segmentos(desde=desde, hasta=hasta, centro=centro, nivel_cuentas=nivel_cuentas)
    claves = seg.claves(con_sin_centro=False)
    secciones = {c: _Acumulador(claves) for c in ("ingresos", "variables", "fijos_controlables", "no_controlables")}
    comunes = CERO
    for m in seg.movimientos:
        if m["columna"] == SIN_CENTRO:
            comunes += -m["monto"] if m["es_ingreso"] else m["monto"]
            continue
        g = m["grupo"]
        if m["es_ingreso"]:
            secciones["ingresos"].sumar(g["id"], m["columna"], m["monto"], _etiqueta_cuenta(g, prorrateo=False))
            continue
        categoria = _categoria_contribucion(m)
        fila = (g["id"], m["indirecto"])
        secciones[categoria].sumar(fila, m["columna"], m["monto"], _etiqueta_cuenta(g, prorrateo=m["indirecto"]))

    titulos = {
        "ingresos": "Ingresos atribuibles",
        "variables": "(−) Costos variables directos",
        "fijos_controlables": "(−) Costos fijos controlables",
        "no_controlables": "(−) Costos fijos asignados no controlables",
    }
    totales = {c: acc.total() for c, acc in secciones.items()}
    salida = {}
    for clave, titulo in titulos.items():
        acc = secciones[clave]
        orden = lambda f, acc=acc: (acc.etiquetas[f]["prorrateo"], acc.etiquetas[f]["cuenta"]["codigo"])  # noqa: E731
        salida[clave] = {"clave": clave, "titulo": titulo, "filas": acc.filas(orden), **_vector(claves, totales[clave])}

    margen_contribucion = _combinar(claves, (1, totales["ingresos"]), (-1, totales["variables"]))
    margen_controlable = _combinar(claves, (1, margen_contribucion), (-1, totales["fijos_controlables"]))
    resultado_segmento = _combinar(claves, (1, margen_controlable), (-1, totales["no_controlables"]))
    total_segmentos = sum(resultado_segmento.values(), CERO)

    def razon(margen):
        return [_porcentaje(margen[k], totales["ingresos"][k]) for k in claves] + [
            _porcentaje(sum(margen.values(), CERO), sum(totales["ingresos"].values(), CERO))
        ]

    return {
        **seg.encabezado(),
        "columnas": seg.describir_columnas(con_sin_centro=False),
        "ingresos": salida["ingresos"],
        "variables": salida["variables"],
        "margen_contribucion": {**_vector(claves, margen_contribucion), "razon": razon(margen_contribucion)},
        "fijos_controlables": salida["fijos_controlables"],
        "margen_controlable": {**_vector(claves, margen_controlable), "razon": razon(margen_controlable)},
        "no_controlables": salida["no_controlables"],
        "resultado_segmento": {**_vector(claves, resultado_segmento), "razon": razon(resultado_segmento)},
        "costos_comunes": _texto(comunes),
        "resultado": _texto(total_segmentos - comunes),
    }


# =============================================================================
# T3.3: indicadores de rentabilidad por área
# =============================================================================

def indicadores_rentabilidad(*, desde, hasta, centro=None):
    """Margen bruto, operativo, neto y de contribución por unidad, y su participación en el resultado.

    Usa el rubro de cada cuenta (T3.2): margen bruto = ingresos de operación − costo de intermediación;
    resultado operativo = margen bruto − gastos de operación (incluidos los prorrateados); resultado neto =
    operativo + ingresos no operacionales − gastos no operacionales (igual al resultado absorbente de T3.1).
    El margen de contribución es el de T3.2 (ingresos − costos variables directos) y no se calcula para la
    columna "Sin centro". La participación se mide sobre el total de la vista y solo aplica si es positivo.
    """
    seg = _Segmentos(desde=desde, hasta=hasta, centro=centro)
    claves = seg.claves()
    rubros = {
        R.INGRESO_OPERACION: "ingresos_operacion",
        R.COSTO_INTERMEDIACION: "costo_intermediacion",
        R.GASTO_OPERACION: "gastos_operacion",
        R.INGRESO_NO_OPERACION: "ingresos_no_operacion",
        R.GASTO_NO_OPERACION: "gastos_no_operacion",
    }
    sumas = {c: defaultdict(lambda: CERO) for c in (*rubros.values(), "variables")}
    for m in seg.movimientos:
        col = m["columna"]
        rubro = m["rubro_resultado"] or (R.INGRESO_OPERACION if m["es_ingreso"] else R.GASTO_OPERACION)
        sumas[rubros[rubro]][col] += m["monto"]
        if not m["es_ingreso"] and col != SIN_CENTRO and _categoria_contribucion(m) == "variables":
            sumas["variables"][col] += m["monto"]

    margen_bruto = _combinar(claves, (1, sumas["ingresos_operacion"]), (-1, sumas["costo_intermediacion"]))
    resultado_operativo = _combinar(claves, (1, margen_bruto), (-1, sumas["gastos_operacion"]))
    resultado_neto = _combinar(
        claves, (1, resultado_operativo), (1, sumas["ingresos_no_operacion"]), (-1, sumas["gastos_no_operacion"])
    )
    ingresos = _combinar(claves, (1, sumas["ingresos_operacion"]), (1, sumas["ingresos_no_operacion"]))
    segmentos = [k for k in claves if k != SIN_CENTRO]
    margen_contribucion = _combinar(segmentos, (1, ingresos), (-1, sumas["variables"]))

    def total(valores, sobre=claves):
        return sum((valores.get(k, CERO) for k in sobre), CERO)

    def montos(clave, titulo, valores, sobre=claves):
        return {
            "clave": clave, "titulo": titulo,
            "valores": [_texto(valores[k]) if k in sobre else None for k in claves],
            "total": _texto(total(valores, sobre)),
        }

    def razon(clave, titulo, base_texto, parte, base, sobre=claves):
        return {
            "clave": clave, "titulo": titulo, "base": base_texto,
            "valores": [_porcentaje(parte[k], base[k]) if k in sobre else None for k in claves],
            "total": _porcentaje(total(parte, sobre), total(base, sobre)),
        }

    def participacion(clave, titulo, valores):
        base = total(valores)
        aplica = base > 0
        return {
            "clave": clave, "titulo": titulo, "aplica": aplica,
            "valores": [_porcentaje(valores[k], base) if aplica else None for k in claves],
            "total": "100.00" if aplica else None,
        }

    ingresos_operacion = sumas["ingresos_operacion"]
    return {
        **seg.encabezado(),
        "columnas": seg.describir_columnas(),
        "montos": [
            montos("ingresos_operacion", "Ingresos de operación", ingresos_operacion),
            montos("costo_intermediacion", "(−) Costo de intermediación", sumas["costo_intermediacion"]),
            montos("margen_bruto", "= Margen bruto", margen_bruto),
            montos("gastos_operacion", "(−) Gastos de operación (directos y asignados)", sumas["gastos_operacion"]),
            montos("resultado_operativo", "= Resultado operativo", resultado_operativo),
            montos("ingresos_no_operacion", "(+) Ingresos no operacionales", sumas["ingresos_no_operacion"]),
            montos("gastos_no_operacion", "(−) Gastos no operacionales", sumas["gastos_no_operacion"]),
            montos("resultado_neto", "= Resultado neto", resultado_neto),
            montos("margen_contribucion", "Margen de contribución (ingresos − costos variables directos)",
                   margen_contribucion, segmentos),
        ],
        "indicadores": [
            razon("margen_bruto", "Margen bruto", "ingresos de operación", margen_bruto, ingresos_operacion),
            razon("margen_operativo", "Margen operativo", "ingresos de operación", resultado_operativo, ingresos_operacion),
            razon("margen_contribucion", "Margen de contribución", "ingresos totales", margen_contribucion, ingresos, segmentos),
            razon("margen_neto", "Margen neto", "ingresos totales", resultado_neto, ingresos),
        ],
        "participacion": [
            participacion("resultado", "Participación en el resultado", resultado_neto),
            participacion("ingresos", "Participación en los ingresos", ingresos),
        ],
    }
