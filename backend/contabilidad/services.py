"""Reglas de negocio de contabilidad: catálogo de cuentas, periodos y asientos."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Exists, Max, OuterRef, Q
from django.utils import timezone

from centros_costo.models import CentroCosto
from centros_costo.services import resolver_regla
from tesoreria.services import validar_proveedor_activo
from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import RUBROS_GASTO, RUBROS_INGRESO, Asiento, Cuenta, LineaAsiento, PeriodoContable

# =============================================================================
# Catálogo de cuentas
# =============================================================================

NATURALEZA_POR_TIPO = {
    Cuenta.Tipo.ACTIVO: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.GASTO: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.ORDEN: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.PASIVO: Cuenta.Naturaleza.ACREEDORA,
    Cuenta.Tipo.PATRIMONIO: Cuenta.Naturaleza.ACREEDORA,
    Cuenta.Tipo.INGRESO: Cuenta.Naturaleza.ACREEDORA,
}

# Campos que se pueden modificar después de crear la cuenta.
CAMPOS_EDITABLES = {
    "nombre", "naturaleza", "acepta_movimientos", "exenta_centro_costo", "activa",
    "rubro_resultado", "comportamiento_costo", "controlable",
}
CAMPOS_INMUTABLES = {"codigo", "padre", "tipo", "nivel"}

ENTIDAD = "cuenta"


def instantanea(cuenta):
    """Estado auditable de la cuenta para la bitácora."""
    return {
        "codigo": cuenta.codigo,
        "nombre": cuenta.nombre,
        "padre": cuenta.padre.codigo if cuenta.padre_id else None,
        "nivel": cuenta.nivel,
        "tipo": cuenta.tipo,
        "naturaleza": cuenta.naturaleza,
        "acepta_movimientos": cuenta.acepta_movimientos,
        "exenta_centro_costo": cuenta.exenta_centro_costo,
        "activa": cuenta.activa,
        "rubro_resultado": cuenta.rubro_resultado or None,
        "comportamiento_costo": cuenta.comportamiento_costo or None,
        "controlable": cuenta.controlable,
    }


def _validar_exencion(tipo, exenta):
    if exenta and tipo not in Cuenta.TIPOS_BALANCE:
        raise ValidationError(
            {"exenta_centro_costo": "Solo las cuentas de balance pueden quedar exentas de centro de costo."}
        )


def _validar_clasificacion(tipo, rubro, comportamiento, controlable):
    """Clasificación para reportes (T3.2/T3.3): solo en cuentas de resultado y coherente con su tipo."""
    errores = {}
    if rubro:
        validos = RUBROS_INGRESO if tipo == Cuenta.Tipo.INGRESO else RUBROS_GASTO if tipo == Cuenta.Tipo.GASTO else ()
        if rubro not in validos:
            errores["rubro_resultado"] = "El rubro no corresponde al tipo de la cuenta (solo ingresos y gastos se clasifican)."
    if tipo != Cuenta.Tipo.GASTO:
        if comportamiento:
            errores["comportamiento_costo"] = "Solo las cuentas de gasto son variables o fijas."
        if controlable is not None:
            errores["controlable"] = "Solo las cuentas de gasto se clasifican como controlables."
    if errores:
        raise ValidationError(errores)


@transaction.atomic
def crear_cuenta(
    *,
    usuario,
    codigo,
    nombre,
    padre=None,
    tipo=None,
    naturaleza=None,
    acepta_movimientos=True,
    exenta_centro_costo=False,
    rubro_resultado=None,
    comportamiento_costo=None,
    controlable=None,
    request=None,
):
    codigo = (codigo or "").strip()
    nombre = (nombre or "").strip()

    if padre is not None:
        # Bloquea al padre para que no cambie a "de detalle" mientras se crea el hijo.
        padre = Cuenta.objects.select_for_update().get(pk=padre.pk)
        if not padre.activa:
            raise ValidationError({"padre": f"La cuenta padre {padre.codigo} está inactiva."})
        if padre.acepta_movimientos:
            raise ValidationError(
                {
                    "padre": f"La cuenta {padre.codigo} acepta movimientos (es de detalle). "
                    "Márquela como cuenta de agrupación antes de agregarle subcuentas."
                }
            )
        if not codigo.startswith(padre.codigo) or len(codigo) <= len(padre.codigo):
            raise ValidationError(
                {"codigo": f"El código debe empezar con {padre.codigo} (código del padre) y ser más largo."}
            )
        if tipo and tipo != padre.tipo:
            raise ValidationError({"tipo": f"La subcuenta debe ser del mismo tipo que su padre ({padre.get_tipo_display()})."})
        tipo = padre.tipo
        nivel = padre.nivel + 1
    else:
        if not tipo:
            raise ValidationError({"tipo": "Las cuentas raíz deben indicar su tipo."})
        nivel = 1

    if codigo and Cuenta.objects.filter(codigo=codigo).exists():
        raise ValidationError({"codigo": f"Ya existe una cuenta con el código {codigo}."})

    _validar_exencion(tipo, exenta_centro_costo)
    _validar_clasificacion(tipo, rubro_resultado, comportamiento_costo, controlable)

    cuenta = Cuenta(
        rubro_resultado=rubro_resultado or None,
        comportamiento_costo=comportamiento_costo or None,
        controlable=controlable,
        codigo=codigo,
        nombre=nombre,
        padre=padre,
        nivel=nivel,
        tipo=tipo,
        naturaleza=naturaleza or NATURALEZA_POR_TIPO[tipo],
        acepta_movimientos=acepta_movimientos,
        exenta_centro_costo=exenta_centro_costo,
        activa=True,
        creado_por=usuario,
        modificado_por=usuario,
    )
    cuenta.full_clean()
    cuenta.save()
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=cuenta.pk,
        descripcion=f"Alta de la cuenta {cuenta}",
        valor_nuevo=instantanea(cuenta),
        request=request,
    )
    return cuenta


@transaction.atomic
def actualizar_cuenta(cuenta, *, usuario, datos, request=None):
    """Modifica los campos editables. `datos` es un dict parcial."""
    inmutables = CAMPOS_INMUTABLES & set(datos)
    if inmutables:
        raise ValidationError(
            {campo: "No se puede modificar después de crear la cuenta." for campo in sorted(inmutables)}
        )
    desconocidos = set(datos) - CAMPOS_EDITABLES
    if desconocidos:
        raise ValidationError({campo: "Campo no reconocido." for campo in sorted(desconocidos)})

    cuenta = Cuenta.objects.select_for_update(of=("self",)).select_related("padre").get(pk=cuenta.pk)
    antes = instantanea(cuenta)

    for campo, valor in datos.items():
        if campo in ("rubro_resultado", "comportamiento_costo") and not valor:
            valor = None  # vacío = heredar
        setattr(cuenta, campo, valor.strip() if campo == "nombre" else valor)
    _validar_clasificacion(cuenta.tipo, cuenta.rubro_resultado, cuenta.comportamiento_costo, cuenta.controlable)

    if cuenta.acepta_movimientos and cuenta.hijos.exists():
        raise ValidationError(
            {"acepta_movimientos": "Una cuenta con subcuentas no puede aceptar movimientos."}
        )
    if antes["acepta_movimientos"] and not cuenta.acepta_movimientos and cuenta.lineas.exists():
        raise ValidationError(
            {"acepta_movimientos": "La cuenta ya tiene movimientos: no puede convertirse en cuenta de agrupación."}
        )
    _validar_exencion(cuenta.tipo, cuenta.exenta_centro_costo)
    if antes["activa"] and not cuenta.activa and cuenta.hijos.filter(activa=True).exists():
        raise ValidationError({"activa": "Desactive primero las subcuentas activas."})
    if not antes["activa"] and cuenta.activa and cuenta.padre_id and not cuenta.padre.activa:
        raise ValidationError({"activa": f"La cuenta padre {cuenta.padre.codigo} está inactiva."})

    despues = instantanea(cuenta)
    if antes == despues:
        return cuenta

    cuenta.modificado_por = usuario
    cuenta.full_clean()
    cuenta.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=cuenta.pk,
        descripcion=f"Modificación de la cuenta {cuenta}",
        valor_anterior=antes,
        valor_nuevo=despues,
        request=request,
    )
    return cuenta


@transaction.atomic
def eliminar_cuenta(cuenta, *, usuario, request=None):
    cuenta = Cuenta.objects.select_for_update(of=("self",)).select_related("padre").get(pk=cuenta.pk)
    if cuenta.hijos.exists():
        raise ValidationError("No se puede eliminar una cuenta que tiene subcuentas.")
    if cuenta.lineas.exists():
        raise ValidationError("La cuenta tiene movimientos registrados: no se puede eliminar, desactívela.")
    antes = instantanea(cuenta)
    pk = cuenta.pk
    descripcion = f"Baja de la cuenta {cuenta}"
    cuenta.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=pk,
        descripcion=descripcion,
        valor_anterior=antes,
        request=request,
    )


def consultar_cuentas(*, tipo=None, activa=None, acepta_movimientos=None, q=None):
    qs = Cuenta.objects.select_related("padre", "creado_por", "modificado_por").order_by("codigo")
    if tipo:
        qs = qs.filter(tipo=tipo)
    if activa is not None:
        qs = qs.filter(activa=activa)
    if acepta_movimientos is not None:
        qs = qs.filter(acepta_movimientos=acepta_movimientos)
    if q:
        qs = qs.filter(Q(codigo__startswith=q.strip()) | Q(nombre__icontains=q.strip()))
    return qs


CAMPOS_ARBOL = (
    "id",
    "codigo",
    "nombre",
    "padre_id",
    "nivel",
    "tipo",
    "naturaleza",
    "acepta_movimientos",
    "exenta_centro_costo",
    "activa",
    "rubro_resultado",
    "comportamiento_costo",
    "controlable",
)

CAMPOS_CLASIFICACION = ("rubro_resultado", "comportamiento_costo", "controlable")


def _clasificacion_por_defecto(tipo):
    """Valores de una cuenta raíz sin clasificación propia."""
    if tipo == Cuenta.Tipo.INGRESO:
        return {"rubro_resultado": Cuenta.Rubro.INGRESO_OPERACION, "comportamiento_costo": None, "controlable": None}
    if tipo == Cuenta.Tipo.GASTO:
        return {"rubro_resultado": Cuenta.Rubro.GASTO_OPERACION, "comportamiento_costo": Cuenta.Comportamiento.FIJO, "controlable": True}
    return {"rubro_resultado": None, "comportamiento_costo": None, "controlable": None}


def _resolver_clasificacion(filas):
    """{id: (heredada, efectiva)}: lo que la cuenta recibe de su padre y lo que finalmente aplica."""
    por_id = {f["id"]: f for f in filas}
    resultado = {}

    def resolver(id_):
        if id_ not in resultado:
            f = por_id[id_]
            heredada = resolver(f["padre_id"])[1] if f["padre_id"] else _clasificacion_por_defecto(f["tipo"])
            # En Oracle un texto nulo llega como "": ambos significan "heredar".
            efectiva = {c: f[c] if f[c] not in (None, "") else heredada[c] for c in CAMPOS_CLASIFICACION}
            resultado[id_] = (heredada, efectiva)
        return resultado[id_]

    for f in sorted(filas, key=lambda x: x["nivel"]):
        resolver(f["id"])
    return resultado


def clasificacion_resultados():
    """{id_cuenta: {rubro_resultado, comportamiento_costo, controlable}} efectivos (con herencia)."""
    filas = list(Cuenta.objects.values("id", "padre_id", "nivel", "tipo", *CAMPOS_CLASIFICACION))
    return {id_: efectiva for id_, (_, efectiva) in _resolver_clasificacion(filas).items()}


def arbol_cuentas():
    """Catálogo completo como lista de raíces, cada nodo con su lista `hijos`.

    Cada nodo incluye `clasificacion_heredada` (lo que recibe del padre) y `clasificacion_efectiva`.
    """
    nodos = {}
    raices = []
    filas = list(Cuenta.objects.order_by("codigo").values(*CAMPOS_ARBOL))
    clasificacion = _resolver_clasificacion(filas)
    for fila in filas:
        heredada, efectiva = clasificacion[fila["id"]]
        nodo = {
            **fila,
            "padre": fila.pop("padre_id"),
            "rubro_resultado": fila["rubro_resultado"] or None,
            "comportamiento_costo": fila["comportamiento_costo"] or None,
            "clasificacion_heredada": heredada,
            "clasificacion_efectiva": efectiva,
            "hijos": [],
        }
        nodos[nodo["id"]] = nodo
    for nodo in nodos.values():
        if nodo["padre"] is None:
            raices.append(nodo)
        else:
            nodos[nodo["padre"]]["hijos"].append(nodo)
    return raices


# =============================================================================
# Periodos contables
# =============================================================================

ANIO_MINIMO, ANIO_MAXIMO = 2000, 2100
Estado = PeriodoContable.Estado


def instantanea_periodo(periodo):
    return {
        "periodo": periodo.nombre,
        "estado": periodo.estado,
        "cerrado_por": periodo.cerrado_por.username if periodo.cerrado_por_id else None,
        "cerrado_en": periodo.cerrado_en.isoformat() if periodo.cerrado_en else None,
    }


def _bloquear_periodos():
    """Bloquea todos los periodos (tabla pequeña) para que cierres y reaperturas
    concurrentes no rompan la secuencia."""
    list(PeriodoContable.objects.select_for_update().values_list("id", flat=True))


def _anteriores(periodo):
    return Q(anio__lt=periodo.anio) | Q(anio=periodo.anio, mes__lt=periodo.mes)


def _posteriores(periodo):
    return Q(anio__gt=periodo.anio) | Q(anio=periodo.anio, mes__gt=periodo.mes)


@transaction.atomic
def crear_ejercicio(*, usuario, anio, request=None):
    """Crea los 12 periodos mensuales del ejercicio, todos abiertos."""
    if not ANIO_MINIMO <= anio <= ANIO_MAXIMO:
        raise ValidationError({"anio": f"El año debe estar entre {ANIO_MINIMO} y {ANIO_MAXIMO}."})
    if PeriodoContable.objects.filter(anio=anio).exists():
        raise ValidationError({"anio": f"El ejercicio {anio} ya existe."})

    PeriodoContable.objects.bulk_create(
        PeriodoContable(
            anio=anio,
            mes=mes,
            fecha_inicio=date(anio, mes, 1),
            fecha_fin=date(anio, mes, monthrange(anio, mes)[1]),
            estado=Estado.ABIERTO,
            creado_por=usuario,
            modificado_por=usuario,
        )
        for mes in range(1, 13)
    )
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad="ejercicio",
        objeto_id=anio,
        descripcion=f"Creación del ejercicio {anio} con 12 periodos abiertos",
        valor_nuevo={"anio": anio, "periodos": 12, "estado": Estado.ABIERTO},
        request=request,
    )
    return list(PeriodoContable.objects.filter(anio=anio).order_by("mes"))


@transaction.atomic
def cerrar_periodo(periodo, *, usuario, request=None):
    """Cierra el periodo si todos los anteriores están cerrados."""
    _bloquear_periodos()
    periodo = PeriodoContable.objects.select_related("cerrado_por").get(pk=periodo.pk)
    if periodo.estado == Estado.CERRADO:
        raise ValidationError(f"El periodo {periodo.nombre} ya está cerrado.")
    pendiente = PeriodoContable.objects.filter(_anteriores(periodo), estado=Estado.ABIERTO).order_by("anio", "mes").first()
    if pendiente:
        raise ValidationError(
            f"No se puede cerrar {periodo.nombre}: primero debe cerrarse {pendiente.nombre}. "
            "Los periodos se cierran en orden."
        )
    borradores = periodo.asientos.filter(estado=Asiento.Estado.BORRADOR).count()
    if borradores:
        raise ValidationError(
            f"No se puede cerrar {periodo.nombre}: tiene {borradores} asiento(s) en borrador. "
            "Contabilícelos o elimínelos antes del cierre."
        )

    antes = instantanea_periodo(periodo)
    periodo.estado = Estado.CERRADO
    periodo.cerrado_por = usuario
    periodo.cerrado_en = timezone.now()
    periodo.modificado_por = usuario
    periodo.full_clean()
    periodo.save()
    registrar_evento(
        Bitacora.Accion.CERRAR,
        usuario=usuario,
        entidad="periodo",
        objeto_id=periodo.pk,
        descripcion=f"Cierre del periodo {periodo.nombre}",
        valor_anterior=antes,
        valor_nuevo=instantanea_periodo(periodo),
        request=request,
    )
    return periodo


@transaction.atomic
def reabrir_periodo(periodo, *, usuario, motivo, request=None):
    """Reabre el último periodo cerrado. Solo superusuario y con motivo."""
    if not (usuario and usuario.is_superuser):
        raise PermissionDenied("Solo el administrador (superusuario) puede reabrir periodos.")
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la reapertura."})

    _bloquear_periodos()
    periodo = PeriodoContable.objects.select_related("cerrado_por").get(pk=periodo.pk)
    if periodo.estado == Estado.ABIERTO:
        raise ValidationError(f"El periodo {periodo.nombre} ya está abierto.")
    ultimo = PeriodoContable.objects.filter(_posteriores(periodo), estado=Estado.CERRADO).order_by("-anio", "-mes").first()
    if ultimo:
        raise ValidationError(
            f"Solo se puede reabrir el último periodo cerrado ({ultimo.nombre}). "
            "Reabra primero los periodos posteriores."
        )

    antes = instantanea_periodo(periodo)
    periodo.estado = Estado.ABIERTO
    periodo.modificado_por = usuario
    periodo.full_clean()
    periodo.save()
    registrar_evento(
        Bitacora.Accion.REABRIR,
        usuario=usuario,
        entidad="periodo",
        objeto_id=periodo.pk,
        descripcion=f"Reapertura del periodo {periodo.nombre}. Motivo: {motivo}",
        valor_anterior=antes,
        valor_nuevo={**instantanea_periodo(periodo), "motivo": motivo},
        request=request,
    )
    return periodo


def periodo_de_fecha(fecha):
    return PeriodoContable.objects.filter(fecha_inicio__lte=fecha, fecha_fin__gte=fecha).first()


def validar_fecha_registrable(fecha):
    """Regla 6: solo se registra en periodos existentes y abiertos. Devuelve el periodo."""
    periodo = periodo_de_fecha(fecha)
    if periodo is None:
        raise ValidationError(
            f"No existe periodo contable para el {fecha:%d/%m/%Y}. Cree primero el ejercicio {fecha.year}."
        )
    if periodo.estado == Estado.CERRADO:
        raise ValidationError(f"El periodo {periodo.nombre} está cerrado: no se puede registrar el {fecha:%d/%m/%Y}.")
    return periodo


def consultar_periodos(*, anio=None):
    qs = PeriodoContable.objects.select_related("cerrado_por", "modificado_por").order_by("anio", "mes")
    if anio:
        qs = qs.filter(anio=anio)
    return qs


def resumen_ejercicios():
    return list(
        PeriodoContable.objects.values("anio")
        .annotate(
            abiertos=Count("id", filter=Q(estado=Estado.ABIERTO)),
            cerrados=Count("id", filter=Q(estado=Estado.CERRADO)),
        )
        .order_by("-anio")
    )


# =============================================================================
# Asientos contables (T1.3)
# =============================================================================

CERO = Decimal("0.00")
CENTAVO = Decimal("0.01")
MONTO_MAXIMO = Decimal("1e16")  # NUMBER(18,2)
EstadoAsiento = Asiento.Estado
TipoAsiento = Asiento.Tipo


def _monto(valor):
    """Convierte a Decimal con 2 decimales. Devuelve (monto, error)."""
    if valor in (None, ""):
        return CERO, None
    try:
        monto = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return CERO, "no es un monto válido"
    if not monto.is_finite():
        return CERO, "no es un monto válido"
    if monto < 0:
        return CERO, "no puede ser negativo"
    if monto != monto.quantize(CENTAVO):
        return CERO, "admite como máximo 2 decimales"
    if monto >= MONTO_MAXIMO:
        return CERO, "excede el máximo permitido"
    return monto.quantize(CENTAVO), None


def _validar_cuenta_imputable(cuenta, n, errores, permitir_inactivas=False):
    if cuenta is None:
        errores.append(f"Línea {n}: indique la cuenta.")
    elif not cuenta.acepta_movimientos:
        errores.append(f"Línea {n}: la cuenta {cuenta.codigo} es de agrupación y no acepta movimientos.")
    elif not cuenta.activa and not permitir_inactivas:
        errores.append(f"Línea {n}: la cuenta {cuenta.codigo} está inactiva.")


def _validar_centro(cuenta, centro, fecha, n, errores, mensaje_sin_centro="exige centro de costo"):
    """Regla 3: centro obligatorio salvo cuenta exenta; si se indica, de detalle y vigente en la fecha."""
    if centro is None:
        if cuenta is not None and not cuenta.exenta_centro_costo:
            errores.append(f"Línea {n}: la cuenta {cuenta.codigo} {mensaje_sin_centro}.")
        return
    if not centro.acepta_movimientos:
        errores.append(f"Línea {n}: el centro {centro.codigo} es de agrupación y no recibe movimientos.")
    elif not centro.vigente_en(fecha):
        errores.append(f"Línea {n}: el centro {centro.codigo} no está vigente el {fecha:%d/%m/%Y}.")


def _normalizar_lineas(lineas, fecha, proveedor=None):
    """Valida las líneas de un borrador ({cuenta, centro_costo, descripcion, debe, haber}).

    Asignación (T2.2): el centro indicado en la línea prevalece (directa); si falta y la cuenta lo exige,
    se aplica la regla vigente por proveedor y/o cuenta (`centros_costo.services.resolver_regla`).
    Un borrador puede estar descuadrado; la partida doble se exige al contabilizar.
    """
    if not lineas:
        raise ValidationError({"lineas": "El asiento debe tener al menos una línea."})
    errores, normalizadas = [], []
    # Se releen cuentas y centros para validar su estado actual (no el de un objeto en memoria).
    cuentas = Cuenta.objects.in_bulk([l["cuenta"].pk for l in lineas if l.get("cuenta") is not None])
    centros = CentroCosto.objects.in_bulk([l["centro_costo"].pk for l in lineas if l.get("centro_costo") is not None])
    for n, linea in enumerate(lineas, start=1):
        cuenta = linea.get("cuenta")
        cuenta = cuentas.get(cuenta.pk) if cuenta is not None else None
        centro = linea.get("centro_costo")
        centro = centros.get(centro.pk) if centro is not None else None
        regla = None
        if centro is None and cuenta is not None and cuenta.acepta_movimientos:
            regla = resolver_regla(cuenta, proveedor, fecha)
            centro = regla.centro_costo if regla else None
        linea = {**linea, "cuenta": cuenta, "centro_costo": centro, "regla_asignacion": regla}
        _validar_cuenta_imputable(cuenta, n, errores)
        _validar_centro(cuenta, centro, fecha, n, errores, "exige centro de costo y no hay regla de asignación aplicable")
        debe, error_debe = _monto(linea.get("debe"))
        haber, error_haber = _monto(linea.get("haber"))
        if error_debe:
            errores.append(f"Línea {n}: el cargo {error_debe}.")
        if error_haber:
            errores.append(f"Línea {n}: el abono {error_haber}.")
        if not (error_debe or error_haber) and (debe > 0) == (haber > 0):
            errores.append(f"Línea {n}: registre un cargo o un abono (solo uno de los dos y mayor que cero).")
        normalizadas.append(
            {
                "cuenta": linea.get("cuenta"),
                "centro_costo": linea.get("centro_costo"),
                "regla_asignacion": linea.get("regla_asignacion"),
                "descripcion": (linea.get("descripcion") or "").strip()[:200],
                "debe": debe,
                "haber": haber,
            }
        )
    if errores:
        raise ValidationError({"lineas": errores})
    total_debe = sum((l["debe"] for l in normalizadas), CERO)
    total_haber = sum((l["haber"] for l in normalizadas), CERO)
    return normalizadas, total_debe, total_haber


def _guardar_lineas(asiento, normalizadas):
    asiento.lineas.all().delete()
    LineaAsiento.objects.bulk_create(
        LineaAsiento(asiento=asiento, numero_linea=n, **linea) for n, linea in enumerate(normalizadas, start=1)
    )


def instantanea_asiento(asiento):
    return {
        "codigo": asiento.codigo,
        "fecha": asiento.fecha.isoformat(),
        "concepto": asiento.concepto,
        "referencia": asiento.referencia,
        "proveedor": asiento.proveedor.nit if asiento.proveedor_id else None,
        "tipo": asiento.tipo,
        "estado": asiento.estado,
        "total_debe": str(asiento.total_debe),
        "total_haber": str(asiento.total_haber),
        "lineas": [
            {
                "cuenta": l.cuenta.codigo,
                "centro_costo": l.centro_costo.codigo if l.centro_costo_id else None,
                "regla_asignacion": l.regla_asignacion_id,
                "descripcion": l.descripcion,
                "debe": str(l.debe),
                "haber": str(l.haber),
            }
            for l in asiento.lineas.select_related("cuenta", "centro_costo").order_by("numero_linea")
        ],
    }


def _validar_encabezado(concepto, referencia):
    concepto = (concepto or "").strip()
    if not concepto:
        raise ValidationError({"concepto": "Indique el concepto del asiento."})
    return concepto, (referencia or "").strip()


@transaction.atomic
def crear_asiento(*, usuario, fecha, concepto, lineas, referencia="", proveedor=None, request=None):
    """Crea un asiento en borrador."""
    concepto, referencia = _validar_encabezado(concepto, referencia)
    periodo = validar_fecha_registrable(fecha)
    proveedor = validar_proveedor_activo(proveedor)
    normalizadas, total_debe, total_haber = _normalizar_lineas(lineas, fecha, proveedor)
    asiento = Asiento(
        fecha=fecha,
        periodo=periodo,
        concepto=concepto,
        referencia=referencia,
        proveedor=proveedor,
        tipo=TipoAsiento.DIARIO,
        estado=EstadoAsiento.BORRADOR,
        total_debe=total_debe,
        total_haber=total_haber,
        creado_por=usuario,
        modificado_por=usuario,
    )
    asiento.full_clean()
    asiento.save()
    _guardar_lineas(asiento, normalizadas)
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad="asiento",
        objeto_id=asiento.pk,
        descripcion=f"Borrador de asiento: {concepto}",
        valor_nuevo=instantanea_asiento(asiento),
        request=request,
    )
    return asiento


def _bloquear_borrador(asiento):
    asiento = Asiento.objects.select_for_update().get(pk=asiento.pk)
    if asiento.estado != EstadoAsiento.BORRADOR:
        raise ValidationError(
            f"El asiento {asiento.codigo} está contabilizado: es inmutable. Para corregirlo registre una reversión."
        )
    return asiento


@transaction.atomic
def actualizar_asiento(asiento, *, usuario, fecha, concepto, lineas, referencia="", proveedor=None, request=None):
    """Reemplaza encabezado y líneas de un borrador (las reglas de asignación se vuelven a resolver)."""
    asiento = _bloquear_borrador(asiento)
    antes = instantanea_asiento(asiento)
    concepto, referencia = _validar_encabezado(concepto, referencia)
    asiento.periodo = validar_fecha_registrable(fecha)
    proveedor = validar_proveedor_activo(proveedor)
    normalizadas, asiento.total_debe, asiento.total_haber = _normalizar_lineas(lineas, fecha, proveedor)
    asiento.fecha = fecha
    asiento.concepto = concepto
    asiento.referencia = referencia
    asiento.proveedor = proveedor
    asiento.modificado_por = usuario
    asiento.full_clean()
    asiento.save()
    _guardar_lineas(asiento, normalizadas)
    registrar_evento(
        Bitacora.Accion.MODIFICAR,
        usuario=usuario,
        entidad="asiento",
        objeto_id=asiento.pk,
        descripcion=f"Modificación del borrador: {concepto}",
        valor_anterior=antes,
        valor_nuevo=instantanea_asiento(asiento),
        request=request,
    )
    return asiento


@transaction.atomic
def eliminar_asiento(asiento, *, usuario, request=None):
    asiento = _bloquear_borrador(asiento)
    antes = instantanea_asiento(asiento)
    pk = asiento.pk
    asiento.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR,
        usuario=usuario,
        entidad="asiento",
        objeto_id=pk,
        descripcion=f"Eliminación del borrador: {antes['concepto']}",
        valor_anterior=antes,
        request=request,
    )


def _contabilizar(asiento, usuario, *, es_reversion=False):
    """Valida partida doble, periodo, cuentas y centros; asigna número. Debe ejecutarse en una transacción.

    Las reversiones reflejan un hecho ya válido: no revalidan cuentas inactivas ni vigencia de centros.
    """
    # Bloquea los periodos del ejercicio: serializa la numeración y evita cierres simultáneos.
    list(PeriodoContable.objects.select_for_update().filter(anio=asiento.fecha.year).values_list("id", flat=True))
    asiento = _bloquear_borrador(asiento)
    asiento.periodo = validar_fecha_registrable(asiento.fecha)

    lineas = list(asiento.lineas.select_related("cuenta", "centro_costo").order_by("numero_linea"))
    errores = []
    if len(lineas) < 2:
        errores.append("El asiento debe tener al menos dos líneas.")
    for linea in lineas:
        _validar_cuenta_imputable(linea.cuenta, linea.numero_linea, errores, permitir_inactivas=es_reversion)
        if not es_reversion:
            _validar_centro(linea.cuenta, linea.centro_costo, asiento.fecha, linea.numero_linea, errores)
    total_debe = sum((l.debe for l in lineas), CERO)
    total_haber = sum((l.haber for l in lineas), CERO)
    if total_debe != total_haber:
        errores.append(
            f"Partida doble: el total de cargos ({total_debe:,.2f}) no es igual al total de abonos "
            f"({total_haber:,.2f}). Diferencia: {abs(total_debe - total_haber):,.2f}."
        )
    elif total_debe == 0:
        errores.append("El asiento no tiene montos.")
    if errores:
        raise ValidationError(errores)

    ultimo = Asiento.objects.filter(ejercicio=asiento.fecha.year).aggregate(m=Max("numero"))["m"] or 0
    asiento.ejercicio = asiento.fecha.year
    asiento.numero = ultimo + 1
    asiento.total_debe = total_debe
    asiento.total_haber = total_haber
    asiento.estado = EstadoAsiento.CONTABILIZADO
    asiento.contabilizado_por = usuario
    asiento.contabilizado_en = timezone.now()
    asiento.modificado_por = usuario
    asiento.full_clean()
    asiento.save()  # TRG_ASIENTO_REGLAS vuelve a verificar partida doble y periodo en Oracle.
    return asiento


@transaction.atomic
def contabilizar_asiento(asiento, *, usuario, request=None):
    asiento = _contabilizar(asiento, usuario)
    registrar_evento(
        Bitacora.Accion.CONTABILIZAR,
        usuario=usuario,
        entidad="asiento",
        objeto_id=asiento.pk,
        descripcion=f"Contabilización del asiento {asiento.codigo}: {asiento.concepto}",
        valor_nuevo=instantanea_asiento(asiento),
        request=request,
    )
    return asiento


def _es_asiento_de_tesoreria(asiento):
    # Importación local: tesoreria depende de contabilidad en sus modelos.
    from tesoreria.models import CuentaPorPagar, PagoCuentaPorPagar

    return (
        CuentaPorPagar.objects.filter(asiento=asiento).exists()
        or PagoCuentaPorPagar.objects.filter(asiento=asiento).exists()
    )


def _es_asiento_de_ventas(asiento):
    # Importación local: ventas depende de contabilidad en sus modelos (T7.3).
    from ventas.models import DocumentoVenta

    return DocumentoVenta.objects.filter(asiento=asiento).exists()


@transaction.atomic
def revertir_asiento(
    asiento, *, usuario, motivo, fecha=None, request=None, permitir_prorrateo=False, permitir_tesoreria=False,
    permitir_ventas=False,
):
    """Registra y contabiliza el asiento de reversión del asiento indicado. Devuelve la reversión.

    Los asientos de prorrateo (T2.3), de cuentas por pagar (T5.1) y de ventas (T7.3) solo se revierten desde
    su módulo, que pasa `permitir_prorrateo`, `permitir_tesoreria` o `permitir_ventas` para que su estado no
    se separe de la contabilidad.
    """
    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la reversión."})
    fecha = fecha or timezone.localdate()

    original = Asiento.objects.select_for_update().get(pk=asiento.pk)
    if original.estado != EstadoAsiento.CONTABILIZADO:
        raise ValidationError("Solo se revierten asientos contabilizados; un borrador se edita o se elimina.")
    if original.tipo == TipoAsiento.REVERSION:
        raise ValidationError("Un asiento de reversión no se revierte. Si es necesario, registre un asiento nuevo.")
    if original.tipo == TipoAsiento.PRORRATEO and not permitir_prorrateo:
        raise ValidationError("Es un asiento de prorrateo: anúlelo desde Centros de costo → Prorrateo.")
    if not permitir_tesoreria and _es_asiento_de_tesoreria(original):
        raise ValidationError("Es un asiento de cuentas por pagar: anule el documento o el pago desde Tesorería → Cuentas por pagar.")
    if not permitir_ventas and _es_asiento_de_ventas(original):
        raise ValidationError("Es un asiento de ventas: anule el documento desde Ventas → Documentos de venta.")
    existente = Asiento.objects.filter(reversion_de=original).first()
    if existente:
        raise ValidationError(f"El asiento {original.codigo} ya fue revertido por {existente.codigo}.")
    if fecha < original.fecha:
        raise ValidationError({"fecha": f"La fecha de reversión no puede ser anterior al {original.fecha:%d/%m/%Y}."})

    reversion = Asiento(
        fecha=fecha,
        periodo=validar_fecha_registrable(fecha),
        concepto=f"Reversión de {original.codigo}: {motivo}"[:300],
        referencia=original.referencia,
        proveedor_id=original.proveedor_id,
        tipo=TipoAsiento.REVERSION,
        estado=EstadoAsiento.BORRADOR,
        total_debe=original.total_haber,
        total_haber=original.total_debe,
        reversion_de=original,
        creado_por=usuario,
        modificado_por=usuario,
    )
    reversion.full_clean()
    reversion.save()
    LineaAsiento.objects.bulk_create(
        LineaAsiento(
            asiento=reversion,
            numero_linea=linea.numero_linea,
            cuenta_id=linea.cuenta_id,
            centro_costo_id=linea.centro_costo_id,
            regla_asignacion_id=linea.regla_asignacion_id,
            descripcion=linea.descripcion,
            debe=linea.haber,
            haber=linea.debe,
            linea_origen=linea,
        )
        for linea in original.lineas.order_by("numero_linea")
    )
    # La reversión se permite aunque alguna cuenta se haya desactivado o un centro haya cerrado su vigencia.
    reversion = _contabilizar(reversion, usuario, es_reversion=True)
    registrar_evento(
        Bitacora.Accion.REVERTIR,
        usuario=usuario,
        entidad="asiento",
        objeto_id=original.pk,
        descripcion=f"Reversión del asiento {original.codigo} mediante {reversion.codigo}. Motivo: {motivo}",
        valor_anterior={"codigo": original.codigo, "estado": original.estado},
        valor_nuevo={"asiento_reversion": reversion.codigo, "fecha": fecha.isoformat(), "motivo": motivo},
        request=request,
    )
    return reversion


def consultar_asientos(*, estado=None, tipo=None, desde=None, hasta=None, cuenta=None, proveedor=None, q=None):
    qs = Asiento.objects.select_related(
        "periodo", "proveedor", "creado_por", "contabilizado_por", "reversion_de", "reversion"
    ).order_by("-fecha", "-id")
    if estado:
        qs = qs.filter(estado=estado)
    if tipo:
        qs = qs.filter(tipo=tipo)
    if desde:
        qs = qs.filter(fecha__gte=desde)
    if hasta:
        qs = qs.filter(fecha__lte=hasta)
    if cuenta:
        qs = qs.filter(Exists(LineaAsiento.objects.filter(asiento=OuterRef("pk"), cuenta=cuenta)))
    if proveedor:
        qs = qs.filter(proveedor=proveedor)
    if q:
        q = q.strip()
        qs = qs.filter(Q(concepto__icontains=q) | Q(referencia__icontains=q))
    return qs
