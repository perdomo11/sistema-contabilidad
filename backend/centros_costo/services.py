"""Reglas de negocio de los centros de costo (unidades de responsabilidad)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from contabilidad.models import Cuenta, LineaAsiento
from tesoreria.models import Proveedor
from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import CentroCosto, ReglaAsignacion

ENTIDAD = "centro_costo"
CAMPOS_EDITABLES = {"nombre", "tipo", "clase", "responsable", "acepta_movimientos", "vigente_desde", "vigente_hasta"}
CAMPOS_INMUTABLES = {"codigo", "padre", "nivel"}


def _fecha(f):
    return f.strftime("%d/%m/%Y") if f else "indefinida"


def instantanea(centro):
    return {
        "codigo": centro.codigo,
        "nombre": centro.nombre,
        "padre": centro.padre.codigo if centro.padre_id else None,
        "tipo": centro.tipo,
        "clase": centro.clase,
        "responsable": centro.responsable.username if centro.responsable_id else None,
        "acepta_movimientos": centro.acepta_movimientos,
        "vigente_desde": centro.vigente_desde.isoformat(),
        "vigente_hasta": centro.vigente_hasta.isoformat() if centro.vigente_hasta else None,
    }


def _validar_vigencia(desde, hasta, padre):
    if hasta and hasta < desde:
        raise ValidationError({"vigente_hasta": "La vigencia no puede terminar antes de comenzar."})
    if padre is None:
        return
    if desde < padre.vigente_desde:
        raise ValidationError(
            {"vigente_desde": f"Debe iniciar en o después del inicio de {padre.codigo} ({_fecha(padre.vigente_desde)})."}
        )
    if padre.vigente_hasta and (hasta is None or hasta > padre.vigente_hasta):
        raise ValidationError(
            {"vigente_hasta": f"Debe terminar en o antes del cierre de {padre.codigo} ({_fecha(padre.vigente_hasta)})."}
        )


def _validar_responsable(responsable):
    if responsable is not None and not responsable.is_active:
        raise ValidationError({"responsable": "El responsable debe ser un usuario activo."})


@transaction.atomic
def crear_centro(
    *,
    usuario,
    codigo,
    nombre,
    tipo,
    clase,
    vigente_desde,
    padre=None,
    responsable=None,
    acepta_movimientos=True,
    vigente_hasta=None,
    request=None,
):
    codigo = (codigo or "").strip().upper()
    nombre = (nombre or "").strip()
    if padre is not None:
        padre = CentroCosto.objects.select_for_update().get(pk=padre.pk)
        if padre.acepta_movimientos:
            raise ValidationError(
                {"padre": f"{padre.codigo} es una unidad de detalle. Márquela como de agrupación antes de agregarle subunidades."}
            )
        if not codigo.startswith(padre.codigo) or len(codigo) <= len(padre.codigo):
            raise ValidationError({"codigo": f"El código debe empezar con {padre.codigo} y ser más largo."})
    if codigo and CentroCosto.objects.filter(codigo=codigo).exists():
        raise ValidationError({"codigo": f"Ya existe una unidad con el código {codigo}."})
    _validar_vigencia(vigente_desde, vigente_hasta, padre)
    _validar_responsable(responsable)

    centro = CentroCosto(
        codigo=codigo,
        nombre=nombre,
        padre=padre,
        nivel=padre.nivel + 1 if padre else 1,
        tipo=tipo,
        clase=clase,
        responsable=responsable,
        acepta_movimientos=acepta_movimientos,
        vigente_desde=vigente_desde,
        vigente_hasta=vigente_hasta,
        creado_por=usuario,
        modificado_por=usuario,
    )
    centro.full_clean()
    centro.save()
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=centro.pk,
        descripcion=f"Alta del centro de costo {centro}",
        valor_nuevo=instantanea(centro),
        request=request,
    )
    return centro


@transaction.atomic
def actualizar_centro(centro, *, usuario, datos, request=None):
    inmutables = CAMPOS_INMUTABLES & set(datos)
    if inmutables:
        raise ValidationError({c: "No se puede modificar; cierre la vigencia y cree una unidad nueva." for c in sorted(inmutables)})
    desconocidos = set(datos) - CAMPOS_EDITABLES
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})

    centro = CentroCosto.objects.select_for_update().select_related("padre", "responsable").get(pk=centro.pk)
    antes = instantanea(centro)
    for campo, valor in datos.items():
        setattr(centro, campo, valor.strip() if campo == "nombre" else valor)

    if centro.acepta_movimientos and centro.hijos.exists():
        raise ValidationError({"acepta_movimientos": "Una unidad con subunidades no puede recibir movimientos."})
    movimientos = LineaAsiento.objects.filter(centro_costo=centro)
    if antes["acepta_movimientos"] and not centro.acepta_movimientos and movimientos.exists():
        raise ValidationError({"acepta_movimientos": "La unidad ya tiene movimientos: no puede pasar a agrupación."})

    _validar_vigencia(centro.vigente_desde, centro.vigente_hasta, centro.padre)
    hijos = centro.hijos.all()
    if hijos.filter(vigente_desde__lt=centro.vigente_desde).exists():
        raise ValidationError({"vigente_desde": "Hay subunidades que inician antes de esa fecha."})
    if centro.vigente_hasta and hijos.filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gt=centro.vigente_hasta)).exists():
        raise ValidationError({"vigente_hasta": "Cierre primero la vigencia de las subunidades."})
    fuera = Q(asiento__fecha__lt=centro.vigente_desde)
    if centro.vigente_hasta:
        fuera |= Q(asiento__fecha__gt=centro.vigente_hasta)
    if movimientos.filter(fuera).exists():
        raise ValidationError({"vigente_hasta": "Hay movimientos registrados fuera de la nueva vigencia."})
    # Reglas de asignación (T2.2): su vigencia debe quedar dentro de la del centro.
    reglas = ReglaAsignacion.objects.filter(centro_costo=centro)
    if antes["acepta_movimientos"] and not centro.acepta_movimientos and reglas.exists():
        raise ValidationError({"acepta_movimientos": "La unidad es destino de reglas de asignación: no puede pasar a agrupación."})
    reglas_fuera = Q(vigente_desde__lt=centro.vigente_desde)
    if centro.vigente_hasta:
        reglas_fuera |= Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gt=centro.vigente_hasta)
    if reglas.filter(reglas_fuera).exists():
        raise ValidationError({"vigente_hasta": "Hay reglas de asignación hacia esta unidad fuera de la nueva vigencia: ciérrelas primero."})
    _validar_responsable(centro.responsable)

    despues = instantanea(centro)
    if antes == despues:
        return centro
    centro.modificado_por = usuario
    centro.full_clean()
    centro.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=centro.pk,
        descripcion=f"Modificación del centro de costo {centro}",
        valor_anterior=antes,
        valor_nuevo=despues,
        request=request,
    )
    return centro


@transaction.atomic
def eliminar_centro(centro, *, usuario, request=None):
    centro = CentroCosto.objects.select_for_update().select_related("padre", "responsable").get(pk=centro.pk)
    if centro.hijos.exists():
        raise ValidationError("No se puede eliminar una unidad con subunidades.")
    if LineaAsiento.objects.filter(centro_costo=centro).exists():
        raise ValidationError("La unidad tiene movimientos: no se puede eliminar, cierre su vigencia.")
    if ReglaAsignacion.objects.filter(centro_costo=centro).exists():
        raise ValidationError("La unidad es destino de reglas de asignación: elimine primero esas reglas o cierre la vigencia de la unidad.")
    antes = instantanea(centro)
    pk, descripcion = centro.pk, f"Baja del centro de costo {centro}"
    centro.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR,
        usuario=usuario,
        entidad=ENTIDAD,
        objeto_id=pk,
        descripcion=descripcion,
        valor_anterior=antes,
        request=request,
    )


def _vigentes_en(qs, fecha):
    return qs.filter(vigente_desde__lte=fecha).filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=fecha))


def consultar_centros(*, q=None, tipo=None, clase=None, acepta_movimientos=None, vigente_en=None):
    qs = CentroCosto.objects.select_related("padre", "responsable").order_by("codigo")
    if q:
        q = q.strip()
        qs = qs.filter(Q(codigo__istartswith=q) | Q(nombre__icontains=q))
    if tipo:
        qs = qs.filter(tipo=tipo)
    if clase:
        qs = qs.filter(clase=clase)
    if acepta_movimientos is not None:
        qs = qs.filter(acepta_movimientos=acepta_movimientos)
    if vigente_en:
        qs = _vigentes_en(qs, vigente_en)
    return qs


def arbol_centros():
    nodos, raices = {}, []
    filas = CentroCosto.objects.order_by("codigo").values(
        "id", "codigo", "nombre", "padre_id", "nivel", "tipo", "clase", "acepta_movimientos",
        "vigente_desde", "vigente_hasta", "responsable_id", "responsable__username",
        "responsable__first_name", "responsable__last_name",
    )
    for f in filas:
        nombre_resp = f"{f.pop('responsable__first_name')} {f.pop('responsable__last_name')}".strip()
        usuario_resp = f.pop("responsable__username")
        nodo = {
            **f,
            "padre": f.pop("padre_id"),
            "responsable": f.pop("responsable_id"),
            "responsable_nombre": nombre_resp or usuario_resp,
            "vigente_desde": f["vigente_desde"].isoformat(),
            "vigente_hasta": f["vigente_hasta"].isoformat() if f["vigente_hasta"] else None,
            "hijos": [],
        }
        nodos[nodo["id"]] = nodo
    for nodo in nodos.values():
        (nodos[nodo["padre"]]["hijos"] if nodo["padre"] else raices).append(nodo)
    return raices


# =============================================================================
# Reglas de asignación (T2.2)
# =============================================================================

ENTIDAD_REGLA = "regla_asignacion"
CAMPOS_REGLA_EDITABLES = {"descripcion", "vigente_desde", "vigente_hasta"}
CAMPOS_REGLA_INMUTABLES = {"cuenta", "proveedor", "centro_costo"}


def instantanea_regla(regla):
    return {
        "cuenta": regla.cuenta.codigo if regla.cuenta_id else None,
        "proveedor": regla.proveedor.nit if regla.proveedor_id else None,
        "centro_costo": regla.centro_costo.codigo,
        "descripcion": regla.descripcion,
        "vigente_desde": regla.vigente_desde.isoformat(),
        "vigente_hasta": regla.vigente_hasta.isoformat() if regla.vigente_hasta else None,
    }


def _traslapa(qs, desde, hasta):
    """Filtra las reglas de `qs` cuya vigencia se cruza con [desde, hasta]."""
    qs = qs.filter(Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=desde))
    return qs.filter(vigente_desde__lte=hasta) if hasta else qs


def _validar_regla(regla):
    errores = {}
    if regla.vigente_hasta and regla.vigente_hasta < regla.vigente_desde:
        raise ValidationError({"vigente_hasta": "La vigencia no puede terminar antes de comenzar."})
    cuenta, proveedor, centro = regla.cuenta, regla.proveedor, regla.centro_costo
    if cuenta is None and proveedor is None:
        errores["cuenta"] = "Indique la cuenta, el proveedor o ambos."
    if cuenta is not None:
        if not cuenta.activa:
            errores["cuenta"] = f"La cuenta {cuenta.codigo} está inactiva."
        elif cuenta.exenta_centro_costo:
            errores["cuenta"] = f"La cuenta {cuenta.codigo} está exenta de centro de costo."
    if proveedor is not None and not proveedor.activo:
        errores["proveedor"] = f"El proveedor {proveedor.nombre} está inactivo."
    if not centro.acepta_movimientos:
        errores["centro_costo"] = f"El centro {centro.codigo} es de agrupación: elija una unidad de detalle."
    elif centro.vigente_desde > regla.vigente_desde or (
        centro.vigente_hasta and (regla.vigente_hasta is None or regla.vigente_hasta > centro.vigente_hasta)
    ):
        campo = "vigente_desde" if centro.vigente_desde > regla.vigente_desde else "vigente_hasta"
        errores[campo] = (
            f"La vigencia de la regla debe estar dentro de la del centro {centro.codigo} "
            f"({_fecha(centro.vigente_desde)} a {_fecha(centro.vigente_hasta)})."
        )
    if errores:
        raise ValidationError(errores)

    iguales = ReglaAsignacion.objects.filter(cuenta=cuenta, proveedor=proveedor).exclude(pk=regla.pk)
    otra = _traslapa(iguales, regla.vigente_desde, regla.vigente_hasta).select_related("centro_costo").first()
    if otra:
        raise ValidationError(
            {
                "vigente_desde": f"Ya existe una regla para {regla.criterio} con vigencia que se traslapa "
                f"({_fecha(otra.vigente_desde)} a {_fecha(otra.vigente_hasta)}, centro {otra.centro_costo.codigo}). "
                "Cierre su vigencia primero."
            }
        )


@transaction.atomic
def crear_regla(
    *, usuario, centro_costo, vigente_desde, cuenta=None, proveedor=None, vigente_hasta=None, descripcion="", request=None
):
    regla = ReglaAsignacion(
        cuenta=Cuenta.objects.get(pk=cuenta.pk) if cuenta is not None else None,
        proveedor=Proveedor.objects.get(pk=proveedor.pk) if proveedor is not None else None,
        centro_costo=CentroCosto.objects.select_for_update().get(pk=centro_costo.pk),
        descripcion=(descripcion or "").strip(),
        vigente_desde=vigente_desde,
        vigente_hasta=vigente_hasta,
        creado_por=usuario,
        modificado_por=usuario,
    )
    _validar_regla(regla)
    regla.full_clean()
    regla.save()
    registrar_evento(
        Bitacora.Accion.CREAR,
        usuario=usuario,
        entidad=ENTIDAD_REGLA,
        objeto_id=regla.pk,
        descripcion=f"Alta de la regla de asignación {regla}",
        valor_nuevo=instantanea_regla(regla),
        request=request,
    )
    return regla


def _bloquear_regla(regla):
    return (
        ReglaAsignacion.objects.select_for_update()
        .select_related("cuenta", "proveedor", "centro_costo")
        .get(pk=regla.pk)
    )


@transaction.atomic
def actualizar_regla(regla, *, usuario, datos, request=None):
    inmutables = CAMPOS_REGLA_INMUTABLES & set(datos)
    if inmutables:
        raise ValidationError({c: "No se puede modificar; cierre la vigencia y cree otra regla." for c in sorted(inmutables)})
    desconocidos = set(datos) - CAMPOS_REGLA_EDITABLES
    if desconocidos:
        raise ValidationError({c: "Campo no reconocido." for c in sorted(desconocidos)})

    regla = _bloquear_regla(regla)
    antes = instantanea_regla(regla)
    for campo, valor in datos.items():
        setattr(regla, campo, valor.strip() if campo == "descripcion" else valor)
    despues = instantanea_regla(regla)
    if antes == despues:
        return regla

    if (antes["vigente_desde"], antes["vigente_hasta"]) != (despues["vigente_desde"], despues["vigente_hasta"]):
        # Una regla cerrada o un centro cerrado no impiden ajustar la vigencia hacia atrás;
        # se revalida todo salvo el estado actual de cuenta y proveedor, que no cambian aquí.
        _validar_regla(regla)
        fuera = Q(asiento__fecha__lt=regla.vigente_desde)
        if regla.vigente_hasta:
            fuera |= Q(asiento__fecha__gt=regla.vigente_hasta)
        if LineaAsiento.objects.filter(regla_asignacion=regla).filter(fuera).exists():
            raise ValidationError(
                {"vigente_hasta": "La regla ya se aplicó a asientos que quedarían fuera de la nueva vigencia."}
            )

    regla.modificado_por = usuario
    regla.full_clean()
    regla.save()
    registrar_evento(
        Bitacora.Accion.MODIFICAR,
        usuario=usuario,
        entidad=ENTIDAD_REGLA,
        objeto_id=regla.pk,
        descripcion=f"Modificación de la regla de asignación {regla}",
        valor_anterior=antes,
        valor_nuevo=despues,
        request=request,
    )
    return regla


@transaction.atomic
def eliminar_regla(regla, *, usuario, request=None):
    regla = _bloquear_regla(regla)
    if LineaAsiento.objects.filter(regla_asignacion=regla).exists():
        raise ValidationError("La regla ya se aplicó a asientos: no se puede eliminar, cierre su vigencia.")
    antes = instantanea_regla(regla)
    pk, descripcion = regla.pk, f"Baja de la regla de asignación {regla}"
    regla.delete()
    registrar_evento(
        Bitacora.Accion.ELIMINAR,
        usuario=usuario,
        entidad=ENTIDAD_REGLA,
        objeto_id=pk,
        descripcion=descripcion,
        valor_anterior=antes,
        request=request,
    )


def consultar_reglas(*, q=None, cuenta=None, proveedor=None, centro_costo=None, vigente_en=None):
    qs = ReglaAsignacion.objects.select_related("cuenta", "proveedor", "centro_costo").order_by(
        "centro_costo__codigo", "-vigente_desde", "-id"
    )
    if q:
        q = q.strip()
        qs = qs.filter(
            Q(descripcion__icontains=q)
            | Q(cuenta__codigo__istartswith=q)
            | Q(cuenta__nombre__icontains=q)
            | Q(proveedor__nombre__icontains=q)
            | Q(centro_costo__codigo__istartswith=q)
            | Q(centro_costo__nombre__icontains=q)
        )
    if cuenta is not None:
        qs = qs.filter(cuenta=cuenta)
    if proveedor is not None:
        qs = qs.filter(proveedor=proveedor)
    if centro_costo is not None:
        qs = qs.filter(centro_costo=centro_costo)
    if vigente_en:
        qs = _vigentes_en(qs, vigente_en)
    return qs


def _cadena_cuenta(cuenta):
    """Ids de la cuenta y de sus ancestros, del más cercano al más lejano."""
    cadena, actual = [], cuenta.pk
    while actual is not None and actual not in cadena:
        cadena.append(actual)
        actual = Cuenta.objects.filter(pk=actual).values_list("padre_id", flat=True).first()
    return cadena


def resolver_regla(cuenta, proveedor, fecha):
    """Regla aplicable a una línea sin centro, o None. De la más específica a la más general:

    1. proveedor + cuenta (o su ancestro más cercano); 2. solo proveedor; 3. cuenta (o su ancestro más cercano).
    Solo cuentan las reglas vigentes en la fecha cuyo centro sea de detalle y esté vigente. Las cuentas
    exentas de centro de costo no reciben centro por regla.
    """
    if cuenta is None or cuenta.exenta_centro_costo:
        return None
    cadena = _cadena_cuenta(cuenta)
    condicion = Q(proveedor__isnull=True, cuenta_id__in=cadena)
    if proveedor is not None:
        condicion |= Q(proveedor_id=proveedor.pk) & (Q(cuenta__isnull=True) | Q(cuenta_id__in=cadena))
    reglas = _vigentes_en(ReglaAsignacion.objects.select_related("centro_costo", "cuenta", "proveedor"), fecha)
    candidatas = [
        r for r in reglas.filter(condicion, centro_costo__acepta_movimientos=True) if r.centro_costo.vigente_en(fecha)
    ]
    if not candidatas:
        return None

    def especificidad(r):
        grupo = 0 if r.proveedor_id and r.cuenta_id else 1 if r.proveedor_id else 2
        return grupo, cadena.index(r.cuenta_id) if r.cuenta_id else 0

    return min(candidatas, key=especificidad)
