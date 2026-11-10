"""Flujo de efectivo real (método directo) y proyectado con alertas de déficit (T5.3).

Real: en cada asiento contabilizado que mueve efectivo, cada línea de contrapartida aporta abono − cargo
(por partida doble suman el movimiento de efectivo del asiento) y se clasifica por la actividad de su cuenta.
Proyectado: saldo actual + entradas estimadas (promedio histórico de operación) − salidas comprometidas (T5.2).
"""
from collections import defaultdict
from datetime import timedelta
from decimal import ROUND_DOWN, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import ClasificacionFlujo, ConfiguracionTesoreria
from .proyeccion import egresos_proyectados

CERO = Decimal("0.00")
A = ClasificacionFlujo.Actividad
ACTIVIDADES = (A.OPERACION, A.INVERSION, A.FINANCIAMIENTO)
SEMANAS = 13


def _t(m):
    return f"{m + CERO:.2f}"


def _contabilidad():
    from contabilidad.models import Asiento, Cuenta, LineaAsiento

    return Asiento, Cuenta, LineaAsiento


# =============================================================================
# Configuración
# =============================================================================

def configuracion():
    config, _ = ConfiguracionTesoreria.objects.get_or_create(pk=1)
    return config


@transaction.atomic
def actualizar_configuracion(*, usuario, datos, request=None):
    config = ConfiguracionTesoreria.objects.select_for_update().get(pk=configuracion().pk)
    antes = {"saldo_minimo": f"{config.saldo_minimo:.2f}", "dias_historia": config.dias_historia}
    if "saldo_minimo" in datos:
        if datos["saldo_minimo"] < 0:
            raise ValidationError({"saldo_minimo": "El saldo mínimo no puede ser negativo."})
        config.saldo_minimo = datos["saldo_minimo"]
    if "dias_historia" in datos:
        if not 7 <= datos["dias_historia"] <= 730:
            raise ValidationError({"dias_historia": "Use entre 7 y 730 días."})
        config.dias_historia = datos["dias_historia"]
    despues = {"saldo_minimo": f"{config.saldo_minimo:.2f}", "dias_historia": config.dias_historia}
    if antes != despues:
        config.modificado_por = usuario
        config.save()
        registrar_evento(
            Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="configuracion_tesoreria", objeto_id=1,
            descripcion="Política de liquidez", valor_anterior=antes, valor_nuevo=despues, request=request,
        )
    return config


def _actividad_por_tipo(tipo):
    _, Cuenta, _ = _contabilidad()
    if tipo == Cuenta.Tipo.ACTIVO:
        return A.INVERSION
    if tipo == Cuenta.Tipo.PATRIMONIO:
        return A.FINANCIAMIENTO
    return A.OPERACION


def actividades_por_cuenta():
    """{id_cuenta: (actividad, heredada_de_id | None)} con herencia: gana el ancestro asignado más cercano."""
    _, Cuenta, _ = _contabilidad()
    filas = {c["id"]: c for c in Cuenta.objects.values("id", "padre_id", "nivel", "tipo")}
    asignadas = dict(ClasificacionFlujo.objects.values_list("cuenta_id", "actividad"))
    resultado = {}

    def resolver(id_):
        if id_ not in resultado:
            f = filas[id_]
            if id_ in asignadas:
                resultado[id_] = (asignadas[id_], id_)
            elif f["padre_id"]:
                resultado[id_] = resolver(f["padre_id"])
            else:
                resultado[id_] = (_actividad_por_tipo(f["tipo"]), None)
        return resultado[id_]

    for id_ in sorted(filas, key=lambda i: filas[i]["nivel"]):
        resolver(id_)
    return resultado


def cuentas_efectivo():
    return {id_ for id_, (actividad, _) in actividades_por_cuenta().items() if actividad == A.EFECTIVO}


def _exigir_efectivo(efectivo):
    if not efectivo:
        raise ValidationError(
            "No hay cuentas de efectivo configuradas: asigne la actividad «Efectivo» a caja y bancos "
            "(Tesorería → Flujo de efectivo → Configuración) o ejecute cargar_flujo_base."
        )


@transaction.atomic
def asignar_actividad(*, usuario, cuenta, actividad, request=None):
    _, Cuenta, _ = _contabilidad()
    cuenta = Cuenta.objects.get(pk=cuenta.pk)
    if cuenta.tipo == Cuenta.Tipo.ORDEN:
        raise ValidationError({"cuenta": "Las cuentas de orden no mueven efectivo."})
    if actividad == A.EFECTIVO and cuenta.tipo != Cuenta.Tipo.ACTIVO:
        raise ValidationError({"actividad": "Solo cuentas de activo pueden ser efectivo."})
    existente = ClasificacionFlujo.objects.filter(cuenta=cuenta).first()
    anterior = existente.actividad if existente else None
    if anterior == actividad:
        return existente
    obj, _ = ClasificacionFlujo.objects.update_or_create(cuenta=cuenta, defaults={"actividad": actividad, "modificado_por": usuario})
    registrar_evento(
        Bitacora.Accion.MODIFICAR if existente else Bitacora.Accion.CREAR, usuario=usuario, entidad="clasificacion_flujo",
        objeto_id=cuenta.codigo, descripcion=f"Actividad de flujo de {cuenta.codigo} {cuenta.nombre}: {A(actividad).label}",
        valor_anterior={"actividad": anterior}, valor_nuevo={"actividad": actividad}, request=request,
    )
    return obj


@transaction.atomic
def quitar_actividad(clasificacion, *, usuario, request=None):
    cuenta, anterior = clasificacion.cuenta, clasificacion.actividad
    clasificacion.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR, usuario=usuario, entidad="clasificacion_flujo", objeto_id=cuenta.codigo,
        descripcion=f"{cuenta.codigo} {cuenta.nombre} vuelve a heredar su actividad de flujo",
        valor_anterior={"actividad": anterior}, request=request,
    )


# =============================================================================
# Saldos y movimientos
# =============================================================================

def saldo_efectivo(fecha, efectivo=None, *, antes=False):
    """Saldo de las cuentas de efectivo al cierre de `fecha` (o antes de ella si `antes`)."""
    Asiento, _, LineaAsiento = _contabilidad()
    efectivo = cuentas_efectivo() if efectivo is None else efectivo
    filtro = {"asiento__fecha__lt": fecha} if antes else {"asiento__fecha__lte": fecha}
    s = LineaAsiento.objects.filter(
        asiento__estado=Asiento.Estado.CONTABILIZADO, cuenta_id__in=efectivo, **filtro
    ).aggregate(d=Sum("debe"), h=Sum("haber"))
    return (s["d"] or CERO) - (s["h"] or CERO)


def _contrapartidas(desde, hasta, efectivo):
    """Líneas no efectivo de asientos contabilizados del rango que mueven efectivo: (fecha, cuenta_id, abono − cargo)."""
    Asiento, _, LineaAsiento = _contabilidad()
    asientos = (
        LineaAsiento.objects.filter(
            asiento__estado=Asiento.Estado.CONTABILIZADO, asiento__fecha__gte=desde, asiento__fecha__lte=hasta,
            cuenta_id__in=efectivo,
        ).values_list("asiento_id", flat=True).distinct()
    )
    return (
        LineaAsiento.objects.filter(asiento_id__in=asientos)
        .exclude(cuenta_id__in=efectivo)
        .values_list("asiento__fecha", "cuenta_id", "debe", "haber")
    )


def _grupo_nivel_2():
    _, Cuenta, _ = _contabilidad()
    cuentas = {c["id"]: c for c in Cuenta.objects.values("id", "codigo", "nombre", "nivel", "padre_id")}
    cache = {}

    def grupo(id_):
        if id_ not in cache:
            actual = cuentas[id_]
            while actual["nivel"] > 2 and actual["padre_id"]:
                actual = cuentas[actual["padre_id"]]
            cache[id_] = actual
        return cache[id_]

    return grupo


# =============================================================================
# 1. Flujo real del periodo (método directo)
# =============================================================================

def flujo_efectivo(*, desde, hasta):
    if desde > hasta:
        raise ValidationError({"hasta": "La fecha final no puede ser anterior a la inicial."})
    efectivo = cuentas_efectivo()
    _exigir_efectivo(efectivo)
    actividad = actividades_por_cuenta()
    grupo = _grupo_nivel_2()

    entradas = defaultdict(lambda: CERO)
    salidas = defaultdict(lambda: CERO)
    por_grupo = defaultdict(lambda: {"entradas": CERO, "salidas": CERO})
    mensual = defaultdict(lambda: {"entradas": CERO, "salidas": CERO})
    for fecha, cuenta_id, debe, haber in _contrapartidas(desde, hasta, efectivo):
        monto = (haber or CERO) - (debe or CERO)
        if monto == 0:
            continue
        act = actividad[cuenta_id][0]
        g = grupo(cuenta_id)
        lado = "entradas" if monto > 0 else "salidas"
        (entradas if monto > 0 else salidas)[act] += abs(monto)
        por_grupo[(act, g["id"])][lado] += abs(monto)
        por_grupo[(act, g["id"])]["cuenta"] = {"id": g["id"], "codigo": g["codigo"], "nombre": g["nombre"]}
        mensual[(fecha.year, fecha.month)][lado] += abs(monto)

    inicial = saldo_efectivo(desde, efectivo, antes=True)
    neto = sum(entradas.values(), CERO) - sum(salidas.values(), CERO)
    final_contable = saldo_efectivo(hasta, efectivo)
    actividades = []
    for act in ACTIVIDADES:
        filas = sorted(
            ({"cuenta": v["cuenta"], "entradas": _t(v["entradas"]), "salidas": _t(v["salidas"]),
              "neto": _t(v["entradas"] - v["salidas"])} for (a, _), v in por_grupo.items() if a == act),
            key=lambda f: f["cuenta"]["codigo"],
        )
        actividades.append({
            "actividad": act, "nombre": A(act).label, "entradas": _t(entradas[act]), "salidas": _t(salidas[act]),
            "neto": _t(entradas[act] - salidas[act]), "filas": filas,
        })
    return {
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "saldo_inicial": _t(inicial),
        "actividades": actividades,
        "entradas": _t(sum(entradas.values(), CERO)),
        "salidas": _t(sum(salidas.values(), CERO)),
        "neto": _t(neto),
        "saldo_final": _t(inicial + neto),
        "saldo_final_contable": _t(final_contable),
        "cuadra": inicial + neto == final_contable,
        "mensual": [
            {"anio": y, "mes": m, "entradas": _t(v["entradas"]), "salidas": _t(v["salidas"]), "neto": _t(v["entradas"] - v["salidas"])}
            for (y, m), v in sorted(mensual.items())
        ],
    }


# =============================================================================
# 2. Flujo proyectado y alertas de déficit
# =============================================================================

def entradas_operacion_promedio(fecha, dias, efectivo):
    """Promedio diario de entradas de efectivo de operación en los `dias` anteriores a `fecha` (inclusive)."""
    actividad = actividades_por_cuenta()
    total = CERO
    for _, cuenta_id, debe, haber in _contrapartidas(fecha - timedelta(days=dias - 1), fecha, efectivo):
        monto = (haber or CERO) - (debe or CERO)
        if monto > 0 and actividad[cuenta_id][0] == A.OPERACION:
            total += monto
    return total, (total / dias).quantize(Decimal("0.01"), rounding=ROUND_DOWN)


def flujo_proyectado(*, fecha, entradas="historico"):
    if entradas not in ("historico", "ninguna"):
        raise ValidationError({"entradas": "Use «historico» o «ninguna»."})
    efectivo = cuentas_efectivo()
    _exigir_efectivo(efectivo)
    config = configuracion()
    minimo = config.saldo_minimo

    saldo = saldo_efectivo(fecha, efectivo)
    base_historica, diario = entradas_operacion_promedio(fecha, config.dias_historia, efectivo)
    if entradas == "ninguna":
        diario = CERO

    # El saldo es al cierre de `fecha`; la proyección empieza el día siguiente. Lo que vence hasta `fecha`
    # (incluida) y no se ha pagado es exigible: sale el día 1.
    salidas_semana = [CERO] * SEMANAS
    salidas_por_dia = defaultdict(lambda: CERO)
    vencido = CERO
    for e in egresos_proyectados(fecha + timedelta(days=1)):
        dia = max(1, (e["fecha"] - fecha).days)
        if e["tramo"] == "VENCIDO":
            vencido += e["monto"]
        if dia <= SEMANAS * 7:
            salidas_semana[(dia - 1) // 7] += e["monto"]
            salidas_por_dia[dia] += e["monto"]

    semanas, alertas = [], []
    deficit = bajo_minimo = None
    peor = saldo
    for n in range(SEMANAS):
        inicio = fecha + timedelta(days=7 * n + 1)
        fin = inicio + timedelta(days=6)
        entrada = diario * 7
        final = saldo + entrada - salidas_semana[n]
        estado = "DEFICIT" if final < 0 else "BAJO_MINIMO" if final < minimo else "OK"
        semanas.append({
            "semana": n + 1, "desde": inicio.isoformat(), "hasta": fin.isoformat(), "saldo_inicial": _t(saldo),
            "entradas": _t(entrada), "salidas": _t(salidas_semana[n]), "saldo_final": _t(final), "estado": estado,
        })
        if estado == "DEFICIT" and deficit is None:
            deficit = semanas[-1]
        if estado == "BAJO_MINIMO" and bajo_minimo is None:
            bajo_minimo = semanas[-1]
        peor = min(peor, final)
        saldo = final

    if deficit:
        alertas.append({
            "nivel": "CRITICA", "tipo": "DEFICIT", "semana": deficit["semana"],
            "mensaje": f"Déficit de efectivo proyectado en la semana del {deficit['desde']} al {deficit['hasta']} "
                       f"(saldo {Decimal(deficit['saldo_final']):,.2f}). Financiamiento necesario: {-peor:,.2f}.",
            "monto": _t(-peor),
        })
    if bajo_minimo and (not deficit or bajo_minimo["semana"] < deficit["semana"]):
        alertas.append({
            "nivel": "ADVERTENCIA", "tipo": "BAJO_MINIMO", "semana": bajo_minimo["semana"],
            "mensaje": f"El saldo cae por debajo del mínimo ({minimo:,.2f}) en la semana del {bajo_minimo['desde']} "
                       f"(saldo {Decimal(bajo_minimo['saldo_final']):,.2f}).",
            "monto": _t(minimo - Decimal(bajo_minimo["saldo_final"])),
        })
    if vencido:
        alertas.append({
            "nivel": "INFORMATIVA", "tipo": "VENCIDOS", "semana": 1,
            "mensaje": f"Hay {vencido:,.2f} en cuentas por pagar vencidas, exigibles de inmediato (incluidas en la semana 1).",
            "monto": _t(vencido),
        })

    saldo_actual = saldo_efectivo(fecha, efectivo)

    def saldo_al_dia(dias):
        salidas = sum((m for d, m in salidas_por_dia.items() if d <= dias), CERO)
        return _t(saldo_actual + diario * dias - salidas)

    return {
        "fecha": fecha.isoformat(),
        "saldo_actual": _t(saldo_actual),
        "saldo_minimo": _t(minimo),
        "entradas": entradas,
        "entradas_diarias": _t(diario),
        "base_historica": {"dias": config.dias_historia, "entradas_operacion": _t(base_historica)},
        "total_entradas": _t(sum((Decimal(s["entradas"]) for s in semanas), CERO)),
        "total_salidas": _t(sum(salidas_semana, CERO)),
        "saldo_proyectado": {"30": saldo_al_dia(30), "60": saldo_al_dia(60), "90": saldo_al_dia(90)},
        "saldo_minimo_proyectado": _t(peor),
        "semanas": semanas,
        "alertas": alertas,
    }


# =============================================================================
# Datos de ejemplo
# =============================================================================

EJEMPLO = {
    "11": A.EFECTIVO,
    "12": A.INVERSION,
    "13": A.OPERACION,
    "14": A.OPERACION,
    "15": A.INVERSION,
    "21": A.OPERACION,
    "22": A.FINANCIAMIENTO,
    "23": A.OPERACION,
    "24": A.OPERACION,
    "3": A.FINANCIAMIENTO,
}
