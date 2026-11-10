"""Reglas de negocio del catálogo de cuentas."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import Cuenta

NATURALEZA_POR_TIPO = {
    Cuenta.Tipo.ACTIVO: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.GASTO: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.ORDEN: Cuenta.Naturaleza.DEUDORA,
    Cuenta.Tipo.PASIVO: Cuenta.Naturaleza.ACREEDORA,
    Cuenta.Tipo.PATRIMONIO: Cuenta.Naturaleza.ACREEDORA,
    Cuenta.Tipo.INGRESO: Cuenta.Naturaleza.ACREEDORA,
}

# Campos que se pueden modificar después de crear la cuenta.
CAMPOS_EDITABLES = {"nombre", "naturaleza", "acepta_movimientos", "exenta_centro_costo", "activa"}
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
    }


def _validar_exencion(tipo, exenta):
    if exenta and tipo not in Cuenta.TIPOS_BALANCE:
        raise ValidationError(
            {"exenta_centro_costo": "Solo las cuentas de balance pueden quedar exentas de centro de costo."}
        )


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

    cuenta = Cuenta(
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

    cuenta = Cuenta.objects.select_for_update().select_related("padre").get(pk=cuenta.pk)
    antes = instantanea(cuenta)

    for campo, valor in datos.items():
        setattr(cuenta, campo, valor.strip() if campo == "nombre" else valor)

    if cuenta.acepta_movimientos and cuenta.hijos.exists():
        raise ValidationError(
            {"acepta_movimientos": "Una cuenta con subcuentas no puede aceptar movimientos."}
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
    cuenta = Cuenta.objects.select_for_update().select_related("padre").get(pk=cuenta.pk)
    if cuenta.hijos.exists():
        raise ValidationError("No se puede eliminar una cuenta que tiene subcuentas.")
    # T1.3 agregará: no se puede eliminar una cuenta con movimientos (se desactiva).
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
)


def arbol_cuentas():
    """Catálogo completo como lista de raíces, cada nodo con su lista `hijos`."""
    nodos = {}
    raices = []
    for fila in Cuenta.objects.order_by("codigo").values(*CAMPOS_ARBOL):
        nodo = {**fila, "padre": fila.pop("padre_id"), "hijos": []}
        nodos[nodo["id"]] = nodo
    for nodo in nodos.values():
        if nodo["padre"] is None:
            raices.append(nodo)
        else:
            nodos[nodo["padre"]]["hijos"].append(nodo)
    return raices
