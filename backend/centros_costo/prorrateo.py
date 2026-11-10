"""Motor de prorrateo (T2.3): bases, medidas, reglas y ejecución.

Distribuye los costos acumulados en un centro de servicio (origen) hacia sus centros receptores
según una base configurable. Método escalonado: las reglas se ejecutan por `orden` y un centro ya
distribuido no vuelve a recibir costos. Cada línea generada conserva `linea_origen` (regla 5).
"""
from collections import defaultdict
from decimal import ROUND_FLOOR, Decimal, InvalidOperation, localcontext

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta, LineaAsiento, PeriodoContable
from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import BaseProrrateo, CentroCosto, EjecucionProrrateo, MedidaBase, ReglaProrrateo

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")
DIEZMILESIMA = Decimal("0.0001")
MEDIDA_MAXIMA = Decimal("1e14")  # NUMBER(18,4)
Ejecutada = EjecucionProrrateo.Estado.EJECUTADA
Anulada = EjecucionProrrateo.Estado.ANULADA


class SinMovimientos(ValidationError):
    """No hay costos que distribuir para la regla en el periodo."""


# =============================================================================
# Bases
# =============================================================================

def instantanea_base(base):
    return {"codigo": base.codigo, "nombre": base.nombre, "unidad": base.unidad, "activa": base.activa}


@transaction.atomic
def crear_base(*, usuario, codigo, nombre, unidad, activa=True, request=None):
    codigo = (codigo or "").strip().upper()
    if BaseProrrateo.objects.filter(codigo=codigo).exists():
        raise ValidationError({"codigo": f"Ya existe una base con el código {codigo}."})
    base = BaseProrrateo(
        codigo=codigo,
        nombre=(nombre or "").strip(),
        unidad=(unidad or "").strip(),
        activa=activa,
        creado_por=usuario,
        modificado_por=usuario,
    )
    base.full_clean()
    base.save()
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="base_prorrateo", objeto_id=base.pk,
        descripcion=f"Alta de la base de prorrateo {base}", valor_nuevo=instantanea_base(base), request=request,
    )
    return base


@transaction.atomic
def actualizar_base(base, *, usuario, datos, request=None):
    if "codigo" in datos:
        raise ValidationError({"codigo": "El código no se puede modificar."})
    desconocidos = set(datos) - {"nombre", "unidad", "activa"}
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})
    base = BaseProrrateo.objects.select_for_update().get(pk=base.pk)
    antes = instantanea_base(base)
    for campo, valor in datos.items():
        setattr(base, campo, valor.strip() if isinstance(valor, str) else valor)
    despues = instantanea_base(base)
    if antes == despues:
        return base
    base.modificado_por = usuario
    base.full_clean()
    base.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="base_prorrateo", objeto_id=base.pk,
        descripcion=f"Modificación de la base de prorrateo {base}", valor_anterior=antes, valor_nuevo=despues,
        request=request,
    )
    return base


@transaction.atomic
def eliminar_base(base, *, usuario, request=None):
    base = BaseProrrateo.objects.select_for_update().get(pk=base.pk)
    if base.reglas.exists() or base.medidas.exists():
        raise ValidationError("La base tiene medidas o reglas: desactívela en lugar de eliminarla.")
    antes = instantanea_base(base)
    pk, descripcion = base.pk, f"Baja de la base de prorrateo {base}"
    base.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR, usuario=usuario, entidad="base_prorrateo", objeto_id=pk,
        descripcion=descripcion, valor_anterior=antes, request=request,
    )


# =============================================================================
# Medidas
# =============================================================================

def _centros_del_periodo(periodo):
    """Centros de detalle vigentes en algún día del periodo."""
    return CentroCosto.objects.filter(
        Q(acepta_movimientos=True),
        Q(vigente_desde__lte=periodo.fecha_fin),
        Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=periodo.fecha_inicio),
    ).order_by("codigo")


def cuadricula_medidas(base, periodo):
    """Centros de detalle del periodo (y los que ya tengan medida) con su valor o None."""
    medidas = {m.centro_costo_id: m.valor for m in MedidaBase.objects.filter(base=base, periodo=periodo)}
    centros = CentroCosto.objects.filter(Q(pk__in=_centros_del_periodo(periodo)) | Q(pk__in=medidas)).order_by("codigo")
    filas = [
        {
            "centro_costo": c.pk,
            "codigo": c.codigo,
            "nombre": c.nombre,
            "valor": f"{medidas[c.pk]:.4f}" if c.pk in medidas else None,
        }
        for c in centros
    ]
    total = sum(medidas.values(), Decimal(0))
    return {
        "base": base.pk,
        "periodo": periodo.pk,
        "editable": periodo.estado == PeriodoContable.Estado.ABIERTO and not _base_en_uso(base, periodo),
        "total": f"{total:.4f}",
        "filas": filas,
    }


def _base_en_uso(base, periodo):
    return EjecucionProrrateo.objects.filter(periodo=periodo, estado=Ejecutada, regla__base=base).exists()


def _validar_medidas_editables(base, periodo):
    if periodo.estado != PeriodoContable.Estado.ABIERTO:
        raise ValidationError(f"El periodo {periodo.nombre} está cerrado: sus medidas no se modifican.")
    if _base_en_uso(base, periodo):
        raise ValidationError(
            f"La base {base.codigo} ya se usó en prorrateos ejecutados de {periodo.nombre}: anúlelos antes de cambiar las medidas."
        )


def _medida(valor, n, errores):
    if valor in (None, ""):
        return None
    try:
        medida = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        errores.append(f"Fila {n}: no es un número válido.")
        return None
    if not medida.is_finite() or medida < 0:
        errores.append(f"Fila {n}: el valor no puede ser negativo.")
    elif medida != medida.quantize(DIEZMILESIMA):
        errores.append(f"Fila {n}: admite como máximo 4 decimales.")
    elif medida >= MEDIDA_MAXIMA:
        errores.append(f"Fila {n}: excede el máximo permitido.")
    return medida


@transaction.atomic
def guardar_medidas(*, usuario, base, periodo, valores, request=None):
    """valores: [{centro_costo, valor}]; valor vacío elimina la medida. Devuelve la cuadrícula."""
    periodo = PeriodoContable.objects.select_for_update().get(pk=periodo.pk)
    _validar_medidas_editables(base, periodo)
    existentes = {m.centro_costo_id: m for m in MedidaBase.objects.select_for_update().filter(base=base, periodo=periodo)}
    antes = {m.centro_costo.codigo: f"{m.valor:.4f}" for m in existentes.values()}
    errores, cambios = [], {}
    for n, fila in enumerate(valores, start=1):
        centro = fila["centro_costo"]
        medida = _medida(fila.get("valor"), n, errores)
        if not centro.acepta_movimientos:
            errores.append(f"Fila {n}: {centro.codigo} es de agrupación; las medidas son de unidades de detalle.")
        cambios[centro.pk] = (centro, medida)
    if errores:
        raise ValidationError({"valores": errores})

    for centro_id, (centro, medida) in cambios.items():
        actual = existentes.get(centro_id)
        if medida is None:
            if actual:
                actual.delete()
        elif actual is None:
            MedidaBase.objects.create(base=base, centro_costo=centro, periodo=periodo, valor=medida, modificado_por=usuario)
        elif actual.valor != medida:
            actual.valor = medida
            actual.modificado_por = usuario
            actual.save()
    despues = {
        m.centro_costo.codigo: f"{m.valor:.4f}"
        for m in MedidaBase.objects.select_related("centro_costo").filter(base=base, periodo=periodo)
    }
    if antes != despues:
        registrar_evento(
            Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="medida_base", objeto_id=f"{base.codigo}/{periodo.nombre}",
            descripcion=f"Medidas de {base.nombre} en {periodo.nombre}", valor_anterior=antes, valor_nuevo=despues,
            request=request,
        )
    return cuadricula_medidas(base, periodo)


def _periodo_anterior(periodo):
    return (
        PeriodoContable.objects.filter(Q(anio__lt=periodo.anio) | Q(anio=periodo.anio, mes__lt=periodo.mes))
        .order_by("-anio", "-mes")
        .first()
    )


@transaction.atomic
def copiar_medidas(*, usuario, base, periodo, request=None):
    """Copia del periodo anterior las medidas que falten en este. Devuelve (copiadas, cuadrícula)."""
    periodo = PeriodoContable.objects.select_for_update().get(pk=periodo.pk)
    _validar_medidas_editables(base, periodo)
    anterior = _periodo_anterior(periodo)
    if anterior is None:
        raise ValidationError(f"No hay un periodo anterior a {periodo.nombre}.")
    ya = set(MedidaBase.objects.filter(base=base, periodo=periodo).values_list("centro_costo_id", flat=True))
    vigentes = set(_centros_del_periodo(periodo).values_list("id", flat=True))
    nuevas = [
        MedidaBase(base=base, centro_costo_id=m.centro_costo_id, periodo=periodo, valor=m.valor, modificado_por=usuario)
        for m in MedidaBase.objects.filter(base=base, periodo=anterior)
        if m.centro_costo_id not in ya and m.centro_costo_id in vigentes
    ]
    if not nuevas:
        raise ValidationError(f"No hay medidas de {base.nombre} en {anterior.nombre} que falten en {periodo.nombre}.")
    MedidaBase.objects.bulk_create(nuevas)
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="medida_base", objeto_id=f"{base.codigo}/{periodo.nombre}",
        descripcion=f"Copia de {len(nuevas)} medida(s) de {base.nombre} de {anterior.nombre} a {periodo.nombre}",
        request=request,
    )
    return len(nuevas), cuadricula_medidas(base, periodo)


# =============================================================================
# Reglas
# =============================================================================

def _arbol_cuentas():
    hijos = defaultdict(list)
    for id_, padre_id in Cuenta.objects.values_list("id", "padre_id"):
        if padre_id is not None:
            hijos[padre_id].append(id_)
    return hijos


def cuentas_expandidas(cuenta_ids, hijos=None):
    """Ids de las cuentas indicadas y de todas sus subcuentas."""
    hijos = hijos if hijos is not None else _arbol_cuentas()
    resultado, pendientes = set(), list(cuenta_ids)
    while pendientes:
        actual = pendientes.pop()
        if actual not in resultado:
            resultado.add(actual)
            pendientes.extend(hijos[actual])
    return resultado


def instantanea_regla(regla, cuentas=None, destinos=None):
    cuentas = cuentas if cuentas is not None else list(regla.cuentas.all())
    destinos = destinos if destinos is not None else list(regla.destinos.all())
    return {
        "nombre": regla.nombre,
        "orden": regla.orden,
        "centro_origen": regla.centro_origen.codigo,
        "base": regla.base.codigo,
        "cuentas": sorted(c.codigo for c in cuentas),
        "destinos": sorted(c.codigo for c in destinos),
        "activa": regla.activa,
    }


def _validar_regla(regla, cuentas, destinos):
    errores = {}
    origen = regla.centro_origen
    if not origen.acepta_movimientos:
        errores["centro_origen"] = f"{origen.codigo} es de agrupación: el origen debe ser una unidad de detalle."
    if not cuentas:
        errores["cuentas"] = "Indique al menos una cuenta."
    elif any(c.exenta_centro_costo for c in cuentas):
        errores["cuentas"] = "Las cuentas exentas de centro de costo no se prorratean."
    if not destinos:
        errores["destinos"] = "Indique al menos un centro destino."
    elif origen in destinos:
        errores["destinos"] = "El centro origen no puede ser destino de su propia regla."
    elif any(not d.acepta_movimientos for d in destinos):
        errores["destinos"] = "Los destinos deben ser unidades de detalle."
    if regla.base_id and not regla.base.activa and regla.activa:
        errores["base"] = f"La base {regla.base.codigo} está inactiva."
    if errores:
        raise ValidationError(errores)
    if not regla.activa:
        return

    otras = ReglaProrrateo.objects.filter(activa=True).exclude(pk=regla.pk).prefetch_related("cuentas", "destinos")
    hijos = _arbol_cuentas()
    mias = cuentas_expandidas([c.pk for c in cuentas], hijos)
    destino_ids = {d.pk for d in destinos}
    for otra in otras:
        if otra.centro_origen_id == origen.pk and mias & cuentas_expandidas([c.pk for c in otra.cuentas.all()], hijos):
            raise ValidationError(
                {"cuentas": f"La regla «{otra.nombre}» ya distribuye cuentas de {origen.codigo}: se distribuirían dos veces."}
            )
        # Escalonado: un centro ya distribuido no recibe costos de reglas posteriores.
        if otra.orden <= regla.orden and otra.centro_origen_id in destino_ids:
            raise ValidationError(
                {"destinos": f"{otra.centro_origen.codigo} es origen de «{otra.nombre}» (orden {otra.orden}), que se ejecuta antes o a la vez: no puede recibir costos de esta regla."}
            )
        if otra.orden >= regla.orden and origen.pk in {d.pk for d in otra.destinos.all()}:
            raise ValidationError(
                {"orden": f"«{otra.nombre}» (orden {otra.orden}) envía costos a {origen.codigo}: esta regla debe tener un orden mayor."}
            )


def _guardar_regla(regla, cuentas, destinos, usuario):
    regla.modificado_por = usuario
    regla.full_clean(exclude=["cuentas", "destinos"])
    regla.save()
    regla.cuentas.set(cuentas)
    regla.destinos.set(destinos)


@transaction.atomic
def crear_regla(*, usuario, nombre, centro_origen, base, cuentas, destinos, orden=1, activa=True, request=None):
    regla = ReglaProrrateo(
        nombre=(nombre or "").strip(), orden=orden, centro_origen=centro_origen, base=base, activa=activa,
        creado_por=usuario,
    )
    cuentas, destinos = list(cuentas), list(destinos)
    _validar_regla(regla, cuentas, destinos)
    _guardar_regla(regla, cuentas, destinos, usuario)
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="regla_prorrateo", objeto_id=regla.pk,
        descripcion=f"Alta de la regla de prorrateo «{regla}»", valor_nuevo=instantanea_regla(regla, cuentas, destinos),
        request=request,
    )
    return regla


@transaction.atomic
def actualizar_regla(regla, *, usuario, datos, request=None):
    desconocidos = set(datos) - {"nombre", "orden", "centro_origen", "base", "cuentas", "destinos", "activa"}
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})
    regla = ReglaProrrateo.objects.select_for_update().select_related("centro_origen", "base").get(pk=regla.pk)
    antes = instantanea_regla(regla)
    cuentas = list(datos.pop("cuentas", regla.cuentas.all()))
    destinos = list(datos.pop("destinos", regla.destinos.all()))
    for campo, valor in datos.items():
        setattr(regla, campo, valor.strip() if campo == "nombre" else valor)
    despues = instantanea_regla(regla, cuentas, destinos)
    if antes == despues:
        return regla
    _validar_regla(regla, cuentas, destinos)
    _guardar_regla(regla, cuentas, destinos, usuario)
    registrar_evento(
        Bitacora.Accion.MODIFICAR, usuario=usuario, entidad="regla_prorrateo", objeto_id=regla.pk,
        descripcion=f"Modificación de la regla de prorrateo «{regla}»", valor_anterior=antes, valor_nuevo=despues,
        request=request,
    )
    return regla


@transaction.atomic
def eliminar_regla(regla, *, usuario, request=None):
    regla = ReglaProrrateo.objects.select_for_update().select_related("centro_origen", "base").get(pk=regla.pk)
    if regla.ejecuciones.exists():
        raise ValidationError("La regla ya se ejecutó: desactívela en lugar de eliminarla.")
    antes = instantanea_regla(regla)
    pk, descripcion = regla.pk, f"Baja de la regla de prorrateo «{regla}»"
    regla.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR, usuario=usuario, entidad="regla_prorrateo", objeto_id=pk,
        descripcion=descripcion, valor_anterior=antes, request=request,
    )


# =============================================================================
# Cálculo
# =============================================================================

def _asientos_excluidos(regla):
    """Asientos que no son costo a distribuir: los de esta regla, los de ejecuciones anuladas y sus reversiones."""
    generados = set(
        EjecucionProrrateo.objects.filter(Q(regla=regla) | Q(estado=Anulada)).values_list("asiento_id", flat=True)
    )
    reversiones = set(Asiento.objects.filter(reversion_de__in=generados).values_list("id", flat=True))
    return generados | reversiones


def lineas_origen(regla, periodo):
    cuentas = cuentas_expandidas(regla.cuentas.values_list("id", flat=True))
    return (
        LineaAsiento.objects.filter(
            asiento__estado=Asiento.Estado.CONTABILIZADO,
            asiento__fecha__gte=periodo.fecha_inicio,
            asiento__fecha__lte=periodo.fecha_fin,
            centro_costo=regla.centro_origen,
            cuenta_id__in=cuentas,
        )
        .exclude(asiento_id__in=_asientos_excluidos(regla))
        .select_related("asiento", "cuenta")
        .order_by("asiento__fecha", "asiento__ejercicio", "asiento__numero", "numero_linea")
    )


def _pesos(regla, periodo):
    """[(centro, valor)] de los destinos, en orden de código. Valida que la base sea utilizable."""
    destinos = list(regla.destinos.order_by("codigo"))
    medidas = {
        m.centro_costo_id: m.valor for m in MedidaBase.objects.filter(base=regla.base, periodo=periodo, centro_costo__in=destinos)
    }
    faltan = [d.codigo for d in destinos if d.pk not in medidas]
    if faltan:
        raise ValidationError(
            f"Faltan medidas de {regla.base.nombre} en {periodo.nombre} para: {', '.join(faltan)}."
        )
    pesos = [(d, medidas[d.pk]) for d in destinos]
    if sum(v for _, v in pesos) <= 0:
        raise ValidationError(f"La suma de las medidas de {regla.base.nombre} en {periodo.nombre} es cero.")
    no_vigentes = [d.codigo for d, v in pesos if v > 0 and not d.vigente_en(periodo.fecha_fin)]
    if no_vigentes:
        raise ValidationError(
            f"Centros destino no vigentes al {periodo.fecha_fin:%d/%m/%Y} con medida mayor que cero: {', '.join(no_vigentes)}."
        )
    return pesos


def repartir(monto, pesos):
    """Reparte `monto` (Decimal con 2 decimales) según `pesos` por residuo mayor. La suma es exacta."""
    centavos = int(monto / CENTAVO)
    total = sum(pesos, Decimal(0))
    with localcontext() as ctx:
        ctx.prec = 60
        exactos = [Decimal(centavos) * p / total for p in pesos]
        enteros = [int(e.to_integral_value(rounding=ROUND_FLOOR)) for e in exactos]
        sobrante = centavos - sum(enteros)
        # Los centavos que faltan van a los mayores residuos (empate: el primero).
        orden = sorted(range(len(pesos)), key=lambda i: (-(exactos[i] - enteros[i]), i))
        for i in orden[:sobrante]:
            enteros[i] += 1
    return [Decimal(e) * CENTAVO for e in enteros]


def calcular(regla, periodo):
    """Calcula la distribución sin registrar nada. Devuelve un diccionario con origen, pesos y líneas."""
    pesos = _pesos(regla, periodo)
    total_pesos = sum(v for _, v in pesos)
    origen = list(lineas_origen(regla, periodo))
    lineas, total = [], CERO
    for o in origen:
        es_cargo = o.debe > 0
        monto = o.debe if es_cargo else o.haber
        total += monto if es_cargo else -monto
        etiqueta = f"Prorrateo {o.asiento.codigo}/{o.numero_linea}"
        # Descarga del centro origen (sentido contrario al de la línea original).
        lineas.append({
            "linea_origen": o, "cuenta": o.cuenta, "centro_costo": regla.centro_origen,
            "debe": CERO if es_cargo else monto, "haber": monto if es_cargo else CERO, "descripcion": etiqueta,
        })
        for (centro, _), parte in zip(pesos, repartir(monto, [v for _, v in pesos])):
            if parte > 0:
                lineas.append({
                    "linea_origen": o, "cuenta": o.cuenta, "centro_costo": centro,
                    "debe": parte if es_cargo else CERO, "haber": CERO if es_cargo else parte, "descripcion": etiqueta,
                })
    with localcontext() as ctx:
        ctx.prec = 60
        detalle_pesos = [
            {
                "centro_costo": c.pk, "codigo": c.codigo, "nombre": c.nombre, "valor": f"{v:.4f}",
                "porcentaje": f"{(v * 100 / total_pesos).quantize(DIEZMILESIMA):.4f}",
            }
            for c, v in pesos
        ]
    return {"origen": origen, "pesos": detalle_pesos, "total_pesos": total_pesos, "lineas": lineas, "total": total}


def _texto(monto):
    return f"{monto + CERO:.2f}"


def _resumen(regla, periodo, calculo):
    """Versión serializable del cálculo (vista previa y detalle guardado en la ejecución)."""
    por_destino = defaultdict(lambda: CERO)
    for l in calculo["lineas"]:
        if l["centro_costo"].pk != regla.centro_origen_id:
            por_destino[l["centro_costo"].pk] += l["debe"] - l["haber"]
    return {
        "regla": {"id": regla.pk, "nombre": regla.nombre, "orden": regla.orden},
        "periodo": {"id": periodo.pk, "nombre": periodo.nombre},
        "centro_origen": {"id": regla.centro_origen_id, "codigo": regla.centro_origen.codigo, "nombre": regla.centro_origen.nombre},
        "base": {"codigo": regla.base.codigo, "nombre": regla.base.nombre, "unidad": regla.base.unidad},
        "total_pesos": f"{calculo['total_pesos']:.4f}",
        "total": _texto(calculo["total"]),
        "origen": [
            {
                "linea": o.pk, "asiento_id": o.asiento_id, "asiento_codigo": o.asiento.codigo, "fecha": o.asiento.fecha.isoformat(),
                "concepto": o.asiento.concepto, "cuenta_codigo": o.cuenta.codigo, "cuenta_nombre": o.cuenta.nombre,
                "debe": _texto(o.debe), "haber": _texto(o.haber),
            }
            for o in calculo["origen"]
        ],
        "destinos": [{**p, "monto": _texto(por_destino[p["centro_costo"]])} for p in calculo["pesos"]],
        "lineas_generadas": len(calculo["lineas"]),
    }


def previsualizar(regla, periodo):
    return _resumen(regla, periodo, calcular(regla, periodo))


# =============================================================================
# Ejecución y anulación
# =============================================================================

def _vigente(regla, periodo):
    return EjecucionProrrateo.objects.filter(regla=regla, periodo=periodo, estado=Ejecutada).first()


def _validar_dependencias(regla, periodo):
    """Escalonado: deben estar ejecutadas las reglas anteriores que envían costos al origen de esta."""
    previas = ReglaProrrateo.objects.filter(activa=True, orden__lt=regla.orden, destinos=regla.centro_origen).distinct()
    pendientes = [p for p in previas if not _vigente(p, periodo)]
    if pendientes:
        nombres = ", ".join(f"«{p.nombre}» (orden {p.orden})" for p in pendientes)
        raise ValidationError(
            f"Ejecute antes {nombres}: envía(n) costos a {regla.centro_origen.codigo} y deben distribuirse primero."
        )


@transaction.atomic
def ejecutar(*, usuario, regla, periodo, request=None):
    regla = ReglaProrrateo.objects.select_for_update().select_related("centro_origen", "base").get(pk=regla.pk)
    periodo = PeriodoContable.objects.get(pk=periodo.pk)
    if not regla.activa:
        raise ValidationError(f"La regla «{regla.nombre}» está inactiva.")
    contabilidad.validar_fecha_registrable(periodo.fecha_fin)
    vigente = _vigente(regla, periodo)
    if vigente:
        raise ValidationError(
            f"«{regla.nombre}» ya se ejecutó en {periodo.nombre} (asiento {vigente.asiento.codigo}). Anúlela para volver a calcular."
        )
    _validar_dependencias(regla, periodo)
    calculo = calcular(regla, periodo)
    if not calculo["origen"]:
        raise SinMovimientos(
            f"No hay costos de {regla.centro_origen.codigo} en {periodo.nombre} para las cuentas de «{regla.nombre}»."
        )

    asiento = Asiento(
        fecha=periodo.fecha_fin,
        periodo=periodo,
        concepto=f"Prorrateo: {regla.nombre} – {periodo.nombre}"[:300],
        referencia=f"PRORRATEO-{regla.pk}",
        tipo=Asiento.Tipo.PRORRATEO,
        estado=Asiento.Estado.BORRADOR,
        creado_por=usuario,
        modificado_por=usuario,
    )
    asiento.full_clean()
    asiento.save()
    LineaAsiento.objects.bulk_create(
        LineaAsiento(
            asiento=asiento,
            numero_linea=n,
            cuenta=l["cuenta"],
            centro_costo=l["centro_costo"],
            descripcion=l["descripcion"][:200],
            debe=l["debe"],
            haber=l["haber"],
            linea_origen=l["linea_origen"],
        )
        for n, l in enumerate(calculo["lineas"], start=1)
    )
    asiento = contabilidad.contabilizar_asiento(asiento, usuario=usuario, request=request)
    resumen = _resumen(regla, periodo, calculo)
    ejecucion = EjecucionProrrateo.objects.create(
        regla=regla, periodo=periodo, asiento=asiento, total_distribuido=calculo["total"], detalle=resumen,
        ejecutado_por=usuario,
    )
    registrar_evento(
        Bitacora.Accion.PRORRATEAR, usuario=usuario, entidad="prorrateo", objeto_id=ejecucion.pk,
        descripcion=f"Prorrateo «{regla.nombre}» de {periodo.nombre}: {_texto(calculo['total'])} mediante {asiento.codigo}",
        valor_nuevo={
            "asiento": asiento.codigo, "total": resumen["total"], "base": resumen["base"]["codigo"],
            "destinos": {d["codigo"]: d["monto"] for d in resumen["destinos"]},
        },
        request=request,
    )
    return ejecucion


@transaction.atomic
def ejecutar_pendientes(*, usuario, periodo, request=None):
    """Ejecuta en orden las reglas activas sin ejecución vigente. Todo o nada (salvo las sin movimientos)."""
    resultados = []
    for regla in ReglaProrrateo.objects.filter(activa=True).order_by("orden", "id"):
        if _vigente(regla, periodo):
            continue
        try:
            with transaction.atomic():
                ejecucion = ejecutar(usuario=usuario, regla=regla, periodo=periodo, request=request)
            resultados.append({"regla": regla.nombre, "resultado": "EJECUTADA", "asiento": ejecucion.asiento.codigo,
                               "total": _texto(ejecucion.total_distribuido)})
        except SinMovimientos as exc:
            resultados.append({"regla": regla.nombre, "resultado": "SIN_MOVIMIENTOS", "mensaje": exc.messages[0]})
        except ValidationError as exc:
            raise ValidationError(f"«{regla.nombre}»: {' '.join(exc.messages)} No se registró ningún prorrateo.")
    if not resultados:
        raise ValidationError(f"No hay reglas pendientes de ejecutar en {periodo.nombre}.")
    return resultados


@transaction.atomic
def anular(ejecucion, *, usuario, motivo, request=None):
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la anulación."})
    ejecucion = (
        EjecucionProrrateo.objects.select_for_update()
        .select_related("regla", "periodo", "asiento")
        .get(pk=ejecucion.pk)
    )
    if ejecucion.estado != Ejecutada:
        raise ValidationError("La ejecución ya está anulada.")
    regla, periodo = ejecucion.regla, ejecucion.periodo
    dependientes = EjecucionProrrateo.objects.filter(
        periodo=periodo, estado=Ejecutada, regla__orden__gt=regla.orden,
        regla__centro_origen__in=regla.destinos.all(),
    ).select_related("regla")
    if dependientes:
        nombres = ", ".join(f"«{d.regla.nombre}»" for d in dependientes)
        raise ValidationError(f"Anule primero {nombres}: ya distribuyó costos que recibió de esta regla.")
    reversion = contabilidad.revertir_asiento(
        ejecucion.asiento, usuario=usuario, motivo=f"Anulación de prorrateo: {motivo}", fecha=periodo.fecha_fin,
        request=request, permitir_prorrateo=True,
    )
    ejecucion.estado = Anulada
    ejecucion.anulado_por = usuario
    ejecucion.anulado_en = timezone.now()
    ejecucion.motivo_anulacion = motivo[:250]
    ejecucion.full_clean()
    ejecucion.save()
    registrar_evento(
        Bitacora.Accion.ANULAR, usuario=usuario, entidad="prorrateo", objeto_id=ejecucion.pk,
        descripcion=f"Anulación del prorrateo «{regla.nombre}» de {periodo.nombre} mediante {reversion.codigo}. Motivo: {motivo}",
        valor_anterior={"asiento": ejecucion.asiento.codigo, "estado": Ejecutada},
        valor_nuevo={"reversion": reversion.codigo, "estado": Anulada},
        request=request,
    )
    return ejecucion


def estado_periodo(periodo):
    """Reglas activas (y las inactivas con ejecuciones en el periodo) con su última ejecución."""
    ejecuciones = defaultdict(list)
    for e in EjecucionProrrateo.objects.filter(periodo=periodo).select_related(
        "asiento", "asiento__reversion", "ejecutado_por", "anulado_por"
    ).order_by("-ejecutado_en", "-id"):
        ejecuciones[e.regla_id].append(e)
    reglas = ReglaProrrateo.objects.filter(Q(activa=True) | Q(pk__in=list(ejecuciones))).select_related(
        "centro_origen", "base"
    ).order_by("orden", "id")
    return [(r, ejecuciones.get(r.pk, [])) for r in reglas]
