"""Documentos de venta: CCF y factura de consumidor final (T7.3).

Registrar un documento crea y contabiliza su asiento:
    cargo  cuenta de cobro (banco, caja o cuenta por cobrar) ........ total
    abono  ingresos, cada línea con su centro de costo ............. gravadas + exentas
    abono  2406 IVA débito fiscal .................................. 13 % de las gravadas

Las líneas de ingreso van sin IVA; cada una indica si es exenta (p. ej. intereses de préstamos) o gravada
(p. ej. comisiones por servicios). En la factura de consumidor final el precio al cliente incluye el IVA,
pero contablemente se separa igual. Anular revierte el asiento (`revertir_asiento(..., permitir_ventas=True)`);
desde Asientos está bloqueado. Un documento no se edita ni se elimina (también lo impide Oracle) y su
número no se reutiliza aunque se anule.
"""
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import Cliente, DocumentoVenta

CERO = Decimal("0.00")
TASA_IVA = Decimal("0.13")
CODIGO_IVA_DEBITO = "2406"  # IVA débito fiscal (catálogo base)
CODIGO_CUENTA_COBRO = "1103"  # Depósitos en bancos locales (catálogo base)
Estado, Tipo = DocumentoVenta.Estado, DocumentoVenta.TipoDocumento


def _contabilidad():
    from contabilidad import services
    from contabilidad.models import Cuenta

    return services, Cuenta


def _texto(v):
    return (v or "").strip()


def _monto(valor):
    try:
        monto = Decimal(str(valor))
    except Exception:  # noqa: BLE001
        raise ValidationError({"lineas": "Monto inválido."}) from None
    if not monto.is_finite() or monto != monto.quantize(Decimal("0.01")):
        raise ValidationError({"lineas": "El monto admite como máximo 2 decimales."})
    if monto <= 0:
        raise ValidationError({"lineas": "El monto de cada línea debe ser mayor que cero."})
    return monto.quantize(Decimal("0.01"))


def calcular_iva(gravadas):
    return (gravadas * TASA_IVA).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def instantanea(doc):
    return {
        "cliente": doc.cliente.nit or doc.cliente.nombre,
        "documento": f"{doc.tipo_documento} {doc.numero_documento}",
        "fecha_emision": doc.fecha_emision.isoformat(),
        "ventas_gravadas": f"{doc.ventas_gravadas:.2f}",
        "ventas_exentas": f"{doc.ventas_exentas:.2f}",
        "iva_debito_fiscal": f"{doc.iva_debito_fiscal:.2f}",
        "total": f"{doc.total:.2f}",
        "estado": doc.estado,
        "asiento": doc.asiento.codigo,
    }


def _cuenta_balance(cuenta, tipo, campo, nombre):
    """Cuenta de balance de detalle, activa y exenta de centro de costo (cobro o IVA)."""
    _, Cuenta = _contabilidad()
    cuenta = Cuenta.objects.get(pk=cuenta.pk)
    if cuenta.tipo != tipo:
        raise ValidationError({campo: f"La {nombre} debe ser de {Cuenta.Tipo(tipo).label.lower()} (la {cuenta.codigo} no lo es)."})
    if not cuenta.acepta_movimientos or not cuenta.activa:
        raise ValidationError({campo: f"La cuenta {cuenta.codigo} debe ser de detalle y estar activa."})
    if not cuenta.exenta_centro_costo:
        raise ValidationError({campo: f"La cuenta {cuenta.codigo} debe estar exenta de centro de costo (cuenta de balance)."})
    return cuenta


def cuenta_cobro_por_defecto():
    _, Cuenta = _contabilidad()
    return Cuenta.objects.filter(codigo=CODIGO_CUENTA_COBRO).first()


@transaction.atomic
def registrar_documento_venta(
    *, usuario, cliente, tipo_documento, numero_documento, fecha_emision, concepto, lineas, cuenta_cobro=None, request=None,
):
    """lineas: [{cuenta (ingreso), centro_costo, descripcion, monto (sin IVA), exenta}]."""
    contabilidad, Cuenta = _contabilidad()
    cliente = Cliente.objects.get(pk=cliente.pk)
    numero, concepto = _texto(numero_documento), _texto(concepto)
    errores = {}
    if not cliente.activo:
        errores["cliente"] = f"El cliente {cliente.nombre} está inactivo."
    elif tipo_documento == Tipo.CCF and cliente.tipo != Cliente.Tipo.CONTRIBUYENTE:
        errores["cliente"] = "El comprobante de crédito fiscal solo se emite a contribuyentes (con NIT y NRC); al consumidor final, factura."
    if tipo_documento not in Tipo.values:
        errores["tipo_documento"] = "Tipo de documento inválido."
    if not numero:
        errores["numero_documento"] = "Indique el número del documento."
    if not concepto:
        errores["concepto"] = "Indique el concepto."
    if not lineas:
        errores["lineas"] = "Indique al menos una línea de ingreso."
    if errores:
        raise ValidationError(errores)
    existente = DocumentoVenta.objects.filter(tipo_documento=tipo_documento, numero_documento__iexact=numero).first()
    if existente:
        estado = " (anulado: el número no se reutiliza)" if existente.estado == Estado.ANULADO else ""
        raise ValidationError({"numero_documento": f"El {tipo_documento} {numero} ya fue emitido{estado}."})

    cuenta_cobro = cuenta_cobro or cuenta_cobro_por_defecto()
    if cuenta_cobro is None:
        raise ValidationError({"cuenta_cobro": f"Indique la cuenta de cobro (no existe la {CODIGO_CUENTA_COBRO})."})
    cuenta_cobro = _cuenta_balance(cuenta_cobro, Cuenta.Tipo.ACTIVO, "cuenta_cobro", "cuenta de cobro")

    lineas_asiento, gravadas, exentas = [], CERO, CERO
    cuentas = Cuenta.objects.in_bulk([l["cuenta"].pk for l in lineas])
    for n, linea in enumerate(lineas, start=1):
        monto = _monto(linea.get("monto"))
        cuenta = cuentas[linea["cuenta"].pk]
        if cuenta.tipo != Cuenta.Tipo.INGRESO:
            raise ValidationError({"lineas": f"Línea {n}: la cuenta {cuenta.codigo} no es de ingreso."})
        exenta = bool(linea.get("exenta"))
        if exenta:
            exentas += monto
        else:
            gravadas += monto
        descripcion = _texto(linea.get("descripcion")) or concepto
        lineas_asiento.append({
            "cuenta": cuenta, "centro_costo": linea.get("centro_costo"),
            "descripcion": f"{descripcion}{' (exenta)' if exenta else ''}"[:200], "debe": CERO, "haber": monto,
        })
    iva = calcular_iva(gravadas)
    total = gravadas + exentas + iva
    if iva:
        cuenta_iva = Cuenta.objects.filter(codigo=CODIGO_IVA_DEBITO).first()
        if cuenta_iva is None:
            raise ValidationError({"lineas": f"Falta la cuenta {CODIGO_IVA_DEBITO} (IVA débito fiscal) en el catálogo; cárguela con cargar_catalogo_base."})
        cuenta_iva = _cuenta_balance(cuenta_iva, Cuenta.Tipo.PASIVO, "lineas", "cuenta de IVA débito fiscal")
        lineas_asiento.append({
            "cuenta": cuenta_iva, "centro_costo": None, "descripcion": f"IVA débito fiscal 13 % · {tipo_documento} {numero}"[:200],
            "debe": CERO, "haber": iva,
        })
    lineas_asiento.insert(0, {
        "cuenta": cuenta_cobro, "centro_costo": None, "descripcion": f"{cliente.nombre} · {tipo_documento} {numero}"[:200],
        "debe": total, "haber": CERO,
    })

    tipo_label = Tipo(tipo_documento).label
    asiento = contabilidad.crear_asiento(
        usuario=usuario, fecha=fecha_emision, concepto=f"{tipo_label} {numero} a {cliente.nombre}: {concepto}"[:300],
        referencia=f"{tipo_documento} {numero}"[:50], lineas=lineas_asiento, request=request,
    )
    asiento = contabilidad.contabilizar_asiento(asiento, usuario=usuario, request=request)
    doc = DocumentoVenta.objects.create(
        cliente=cliente, tipo_documento=tipo_documento, numero_documento=numero, fecha_emision=fecha_emision,
        concepto=concepto, ventas_gravadas=gravadas, ventas_exentas=exentas, iva_debito_fiscal=iva, total=total,
        cuenta_cobro=cuenta_cobro, asiento=asiento, creado_por=usuario,
    )
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="documento_venta", objeto_id=doc.pk,
        descripcion=f"Emisión de {tipo_label.lower()} {numero} a {cliente.nombre} por {total:,.2f} (asiento {asiento.codigo})",
        valor_nuevo=instantanea(doc), request=request,
    )
    return doc


@transaction.atomic
def anular_documento_venta(doc, *, usuario, motivo, fecha=None, request=None):
    contabilidad, _ = _contabilidad()
    doc = DocumentoVenta.objects.select_for_update(of=("self",)).select_related("cliente", "asiento").get(pk=doc.pk)
    motivo = _texto(motivo)
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la anulación."})
    if doc.estado == Estado.ANULADO:
        raise ValidationError("El documento ya está anulado.")
    antes = instantanea(doc)
    reversion = contabilidad.revertir_asiento(
        doc.asiento, usuario=usuario, motivo=f"Anulación de {doc.tipo_documento} {doc.numero_documento}: {motivo}",
        fecha=fecha or max(timezone.localdate(), doc.asiento.fecha), request=request, permitir_ventas=True,
    )
    doc.estado = Estado.ANULADO
    doc.asiento_anulacion = reversion
    doc.motivo_anulacion = motivo[:300]
    doc.anulado_por = usuario
    doc.anulado_en = timezone.now()
    doc.save()
    registrar_evento(
        Bitacora.Accion.ANULAR, usuario=usuario, entidad="documento_venta", objeto_id=doc.pk,
        descripcion=f"Anulación de {doc.tipo_documento} {doc.numero_documento} de {doc.cliente.nombre} (reversión {reversion.codigo}). Motivo: {motivo}",
        valor_anterior=antes, valor_nuevo={**instantanea(doc), "asiento_anulacion": reversion.codigo}, request=request,
    )
    return doc


def consultar_documentos(*, desde=None, hasta=None, tipo_documento=None, estado=None, cliente=None, q=None):
    qs = DocumentoVenta.objects.select_related("cliente", "asiento").order_by("-fecha_emision", "-id")
    if desde:
        qs = qs.filter(fecha_emision__gte=desde)
    if hasta:
        qs = qs.filter(fecha_emision__lte=hasta)
    if tipo_documento:
        qs = qs.filter(tipo_documento=tipo_documento)
    if estado:
        qs = qs.filter(estado=estado)
    if cliente is not None:
        qs = qs.filter(cliente=cliente)
    if q:
        q = q.strip()
        qs = qs.filter(Q(numero_documento__icontains=q) | Q(concepto__icontains=q) | Q(cliente__nombre__icontains=q))
    return qs
