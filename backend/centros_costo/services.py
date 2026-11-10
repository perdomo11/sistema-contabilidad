"""Reglas de negocio de los centros de costo (unidades de responsabilidad)."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from contabilidad.models import LineaAsiento
from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import CentroCosto

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
