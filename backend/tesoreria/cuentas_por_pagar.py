"""Cuentas por pagar con vencimientos (T5.1) e IVA en compras (T7.2).

Cada documento genera su asiento (cargo a las líneas de imputación con su centro y, en un CCF, al IVA
crédito fiscal; abono a la cuenta por pagar y, si se retiene, al IVA retenido por pagar) y cada pago otro
(cargo a la cuenta por pagar, abono a banco/caja). Las anulaciones revierten el asiento correspondiente.
Documentos y pagos no se editan ni se eliminan (también lo impide Oracle).
"""
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from usuarios.models import Bitacora
from usuarios.services import registrar_evento

from .models import CuentaPorPagar, PagoCuentaPorPagar, Proveedor

CERO = Decimal("0.00")
CODIGO_CUENTA_PASIVO = "2401"  # Cuentas por pagar a proveedores (catálogo base)
CODIGO_IVA_CREDITO = "1403"  # IVA crédito fiscal (T7.2)
CODIGO_IVA_RETENIDO = "2405"  # IVA retenido a terceros por pagar (T7.2)
TASA_IVA = Decimal("0.13")
TASA_RETENCION = Decimal("0.01")
MINIMO_RETENCION = Decimal("100.00")  # la retención del 1 % aplica a compras gravadas de US$100 o más
TOLERANCIA_IVA = Decimal("0.01")  # diferencia de redondeo admitida frente al 13 % del documento
DIAS_POR_VENCER = 7
TRAMOS = ((1, 30, "1-30"), (31, 60, "31-60"), (61, 90, "61-90"), (91, None, "mas_90"))
Estado, EstadoPago = CuentaPorPagar.Estado, PagoCuentaPorPagar.Estado


def _contabilidad():
    # Importación local: contabilidad depende de tesoreria (Asiento.proveedor).
    from contabilidad import services
    from contabilidad.models import Cuenta

    return services, Cuenta


def _texto(v):
    return (v or "").strip()


def _monto(valor, campo="monto"):
    try:
        monto = Decimal(str(valor))
    except Exception:  # noqa: BLE001
        raise ValidationError({campo: "Monto inválido."}) from None
    if not monto.is_finite() or monto != monto.quantize(Decimal("0.01")):
        raise ValidationError({campo: "El monto admite como máximo 2 decimales."})
    if monto <= 0:
        raise ValidationError({campo: "El monto debe ser mayor que cero."})
    return monto.quantize(Decimal("0.01"))


def instantanea(cxp):
    return {
        "proveedor": cxp.proveedor.nit,
        "documento": f"{cxp.tipo_documento} {cxp.numero_documento}",
        "fecha_emision": cxp.fecha_emision.isoformat(),
        "fecha_vencimiento": cxp.fecha_vencimiento.isoformat(),
        "compras_gravadas": f"{cxp.compras_gravadas:.2f}",
        "compras_exentas": f"{cxp.compras_exentas:.2f}",
        "iva_credito_fiscal": f"{cxp.iva_credito_fiscal:.2f}",
        "iva_retenido": f"{cxp.iva_retenido:.2f}",
        "monto_total": f"{cxp.monto_total:.2f}",
        "saldo": f"{cxp.saldo:.2f}",
        "estado": cxp.estado,
        "asiento": cxp.asiento.codigo,
    }


def cuenta_pasivo_por_defecto():
    _, Cuenta = _contabilidad()
    return Cuenta.objects.filter(codigo=CODIGO_CUENTA_PASIVO).first()


def _validar_cuenta_tesoreria(cuenta, tipo, campo, nombre):
    _, Cuenta = _contabilidad()
    cuenta = Cuenta.objects.get(pk=cuenta.pk)
    if cuenta.tipo != tipo:
        raise ValidationError({campo: f"La {nombre} debe ser de {Cuenta.Tipo(tipo).label.lower()} (la {cuenta.codigo} no lo es)."})
    if not cuenta.acepta_movimientos or not cuenta.activa:
        raise ValidationError({campo: f"La cuenta {cuenta.codigo} debe ser de detalle y estar activa."})
    if not cuenta.exenta_centro_costo:
        raise ValidationError({campo: f"La cuenta {cuenta.codigo} debe estar exenta de centro de costo (cuenta de balance)."})
    return cuenta


def _centavos(monto):
    return monto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _monto_no_negativo(valor, campo):
    if valor is None or valor == "":
        return None
    try:
        monto = Decimal(str(valor))
    except Exception:  # noqa: BLE001
        raise ValidationError({campo: "Monto inválido."}) from None
    if not monto.is_finite() or monto != monto.quantize(Decimal("0.01")):
        raise ValidationError({campo: "El monto admite como máximo 2 decimales."})
    if monto < 0:
        raise ValidationError({campo: "El monto no puede ser negativo."})
    return monto.quantize(Decimal("0.01"))


def desglose_fiscal(*, tipo_documento, base, compras_gravadas=None, compras_exentas=None, iva_credito_fiscal=None,
                    aplica_retencion=False):
    """Desglose fiscal de una compra cuya imputación (gastos o activos) suma `base`.

    - gravadas + exentas = base. Sin indicarlas: factura y CCF son gravadas; recibo y otro, exentas/no sujetas.
    - Solo el CCF da crédito fiscal: IVA = 13 % de las gravadas (se admite ±0.01 de redondeo del documento).
      Retención del 1 % de las gravadas si se indica y las gravadas son de US$100 o más.
    - En factura, recibo u otro el IVA pagado forma parte del costo: no hay crédito fiscal ni retención.
    Devuelve (gravadas, exentas, iva, retencion, monto_total).
    """
    gravadas = _monto_no_negativo(compras_gravadas, "compras_gravadas")
    exentas = _monto_no_negativo(compras_exentas, "compras_exentas")
    iva = _monto_no_negativo(iva_credito_fiscal, "iva_credito_fiscal")
    es_fiscal = tipo_documento in (CuentaPorPagar.TipoDocumento.CCF, CuentaPorPagar.TipoDocumento.FACTURA)
    if gravadas is None and exentas is None:
        gravadas, exentas = (base, CERO) if es_fiscal else (CERO, base)
    elif gravadas is None:
        gravadas = base - exentas
    elif exentas is None:
        exentas = base - gravadas
    if gravadas < 0 or exentas < 0 or gravadas + exentas != base:
        raise ValidationError({
            "compras_gravadas": f"Compras gravadas ({gravadas:,.2f}) más exentas ({exentas:,.2f}) deben sumar la imputación ({base:,.2f})."
        })

    if tipo_documento != CuentaPorPagar.TipoDocumento.CCF:
        if iva or aplica_retencion:
            raise ValidationError({
                "iva_credito_fiscal": "Solo el comprobante de crédito fiscal (CCF) da derecho a crédito fiscal y retención; "
                "en una factura el IVA forma parte del costo."
            })
        return gravadas, exentas, CERO, CERO, base

    esperado = _centavos(gravadas * TASA_IVA)
    if iva is None:
        iva = esperado
    elif abs(iva - esperado) > TOLERANCIA_IVA:
        raise ValidationError({
            "iva_credito_fiscal": f"El IVA crédito fiscal debe ser el 13 % de las compras gravadas ({esperado:,.2f})."
        })
    retencion = CERO
    if aplica_retencion:
        if gravadas < MINIMO_RETENCION:
            raise ValidationError({
                "aplica_retencion": f"La retención del 1 % aplica a compras gravadas de {MINIMO_RETENCION:,.2f} o más."
            })
        retencion = _centavos(gravadas * TASA_RETENCION)
    return gravadas, exentas, iva, retencion, base + iva - retencion


def _cuenta_fiscal(codigo, tipo, campo, nombre):
    _, Cuenta = _contabilidad()
    cuenta = Cuenta.objects.filter(codigo=codigo).first()
    if cuenta is None:
        raise ValidationError({campo: f"Falta la cuenta {codigo} ({nombre}) en el catálogo; cárguela con cargar_catalogo_base."})
    return _validar_cuenta_tesoreria(cuenta, tipo, campo, nombre)


def _estado_por_saldo(cxp):
    if cxp.saldo == 0:
        return Estado.PAGADA
    return Estado.PENDIENTE if cxp.saldo == cxp.monto_total else Estado.PARCIAL


def _bloquear(cxp):
    return CuentaPorPagar.objects.select_for_update(of=("self",)).select_related("proveedor", "asiento").get(pk=cxp.pk)


# =============================================================================
# Registro y anulación de documentos
# =============================================================================

@transaction.atomic
def registrar_cuenta_por_pagar(
    *, usuario, proveedor, tipo_documento, numero_documento, fecha_emision, fecha_vencimiento, concepto, lineas,
    cuenta_pasivo=None, compras_gravadas=None, compras_exentas=None, iva_credito_fiscal=None, aplica_retencion=False,
    request=None,
):
    """Registra el documento y contabiliza su asiento. Las líneas son la imputación (sin IVA): ver `desglose_fiscal`."""
    contabilidad, Cuenta = _contabilidad()
    proveedor = Proveedor.objects.get(pk=proveedor.pk)
    if not proveedor.activo:
        raise ValidationError({"proveedor": f"El proveedor {proveedor.nombre} está inactivo."})
    numero, concepto = _texto(numero_documento), _texto(concepto)
    errores = {}
    if not numero:
        errores["numero_documento"] = "Indique el número del documento."
    if not concepto:
        errores["concepto"] = "Indique el concepto."
    if fecha_vencimiento < fecha_emision:
        errores["fecha_vencimiento"] = "El vencimiento no puede ser anterior a la emisión."
    if not lineas:
        errores["lineas"] = "Indique al menos una línea de imputación."
    if errores:
        raise ValidationError(errores)
    duplicado = (
        CuentaPorPagar.objects.filter(proveedor=proveedor, tipo_documento=tipo_documento, numero_documento__iexact=numero)
        .exclude(estado=Estado.ANULADA).first()
    )
    if duplicado:
        raise ValidationError({"numero_documento": f"El documento {numero} de {proveedor.nombre} ya está registrado."})

    cuenta_pasivo = cuenta_pasivo or cuenta_pasivo_por_defecto()
    if cuenta_pasivo is None:
        raise ValidationError({"cuenta_pasivo": f"Indique la cuenta por pagar (no existe la {CODIGO_CUENTA_PASIVO})."})
    cuenta_pasivo = _validar_cuenta_tesoreria(cuenta_pasivo, Cuenta.Tipo.PASIVO, "cuenta_pasivo", "cuenta por pagar")

    lineas_asiento, base = [], CERO
    for n, linea in enumerate(lineas, start=1):
        monto = _monto(linea.get("monto"), "lineas")
        if linea["cuenta"].pk == cuenta_pasivo.pk:
            raise ValidationError({"lineas": f"Línea {n}: no impute a la misma cuenta por pagar."})
        base += monto
        lineas_asiento.append({
            "cuenta": linea["cuenta"], "centro_costo": linea.get("centro_costo"),
            "descripcion": _texto(linea.get("descripcion")) or concepto[:200], "debe": monto, "haber": CERO,
        })

    gravadas, exentas, iva, retencion, total = desglose_fiscal(
        tipo_documento=tipo_documento, base=base, compras_gravadas=compras_gravadas, compras_exentas=compras_exentas,
        iva_credito_fiscal=iva_credito_fiscal, aplica_retencion=aplica_retencion,
    )
    if iva:
        cuenta_iva = _cuenta_fiscal(CODIGO_IVA_CREDITO, Cuenta.Tipo.ACTIVO, "iva_credito_fiscal", "cuenta de IVA crédito fiscal")
        lineas_asiento.append({
            "cuenta": cuenta_iva, "centro_costo": None,
            "descripcion": f"IVA crédito fiscal 13 % · {numero}"[:200], "debe": iva, "haber": CERO,
        })
    lineas_asiento.append({
        "cuenta": cuenta_pasivo, "centro_costo": None,
        "descripcion": f"{proveedor.nombre} · {numero}"[:200], "debe": CERO, "haber": total,
    })
    if retencion:
        cuenta_retencion = _cuenta_fiscal(CODIGO_IVA_RETENIDO, Cuenta.Tipo.PASIVO, "aplica_retencion", "cuenta de IVA retenido por pagar")
        lineas_asiento.append({
            "cuenta": cuenta_retencion, "centro_costo": None,
            "descripcion": f"Retención IVA 1 % · {proveedor.nombre} · {numero}"[:200], "debe": CERO, "haber": retencion,
        })

    tipo_label = CuentaPorPagar.TipoDocumento(tipo_documento).label
    asiento = contabilidad.crear_asiento(
        usuario=usuario, fecha=fecha_emision, concepto=f"{tipo_label} {numero} de {proveedor.nombre}: {concepto}"[:300],
        referencia=f"{tipo_documento} {numero}"[:50], proveedor=proveedor, lineas=lineas_asiento, request=request,
    )
    asiento = contabilidad.contabilizar_asiento(asiento, usuario=usuario, request=request)

    cxp = CuentaPorPagar.objects.create(
        proveedor=proveedor, tipo_documento=tipo_documento, numero_documento=numero, fecha_emision=fecha_emision,
        fecha_vencimiento=fecha_vencimiento, concepto=concepto, compras_gravadas=gravadas, compras_exentas=exentas,
        iva_credito_fiscal=iva, iva_retenido=retencion, monto_total=total, saldo=total,
        cuenta_pasivo=cuenta_pasivo, asiento=asiento, creado_por=usuario, modificado_por=usuario,
    )
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="cuenta_por_pagar", objeto_id=cxp.pk,
        descripcion=f"Registro de {tipo_label.lower()} {numero} de {proveedor.nombre} por {total:,.2f} (asiento {asiento.codigo})",
        valor_nuevo=instantanea(cxp), request=request,
    )
    return cxp


@transaction.atomic
def anular_cuenta_por_pagar(cxp, *, usuario, motivo, fecha=None, request=None):
    contabilidad, _ = _contabilidad()
    cxp = _bloquear(cxp)
    motivo = _texto(motivo)
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la anulación."})
    if cxp.estado == Estado.ANULADA:
        raise ValidationError("El documento ya está anulado.")
    if cxp.pagos.filter(estado=EstadoPago.VIGENTE).exists():
        raise ValidationError("El documento tiene pagos vigentes: anúlelos primero.")
    antes = instantanea(cxp)
    reversion = contabilidad.revertir_asiento(
        cxp.asiento, usuario=usuario, motivo=f"Anulación de {cxp.numero_documento}: {motivo}",
        fecha=fecha or max(timezone.localdate(), cxp.asiento.fecha), request=request, permitir_tesoreria=True,
    )
    cxp.estado = Estado.ANULADA
    cxp.asiento_anulacion = reversion
    cxp.motivo_anulacion = motivo[:300]
    cxp.anulado_por = cxp.modificado_por = usuario
    cxp.anulado_en = timezone.now()
    cxp.save()
    registrar_evento(
        Bitacora.Accion.ANULAR, usuario=usuario, entidad="cuenta_por_pagar", objeto_id=cxp.pk,
        descripcion=f"Anulación de {cxp.numero_documento} de {cxp.proveedor.nombre} (reversión {reversion.codigo}). Motivo: {motivo}",
        valor_anterior=antes, valor_nuevo={**instantanea(cxp), "asiento_anulacion": reversion.codigo}, request=request,
    )
    return cxp


# =============================================================================
# Pagos
# =============================================================================

@transaction.atomic
def registrar_pago(cxp, *, usuario, fecha, monto, cuenta_banco, referencia="", request=None):
    contabilidad, Cuenta = _contabilidad()
    cxp = _bloquear(cxp)
    if cxp.estado in (Estado.ANULADA, Estado.PAGADA):
        raise ValidationError(f"El documento está {cxp.get_estado_display().lower()}: no admite pagos.")
    monto = _monto(monto)
    if monto > cxp.saldo:
        raise ValidationError({"monto": f"El pago excede el saldo pendiente ({cxp.saldo:,.2f})."})
    if fecha < cxp.fecha_emision:
        raise ValidationError({"fecha": "La fecha de pago no puede ser anterior a la emisión del documento."})
    cuenta_banco = _validar_cuenta_tesoreria(cuenta_banco, Cuenta.Tipo.ACTIVO, "cuenta_banco", "cuenta de banco o caja")
    referencia = _texto(referencia)

    asiento = contabilidad.crear_asiento(
        usuario=usuario, fecha=fecha, proveedor=cxp.proveedor, referencia=(referencia or cxp.numero_documento)[:50],
        concepto=f"Pago de {cxp.numero_documento} a {cxp.proveedor.nombre}"[:300],
        lineas=[
            {"cuenta": cxp.cuenta_pasivo, "centro_costo": None, "descripcion": f"{cxp.proveedor.nombre} · {cxp.numero_documento}"[:200],
             "debe": monto, "haber": CERO},
            {"cuenta": cuenta_banco, "centro_costo": None, "descripcion": (referencia or "Pago a proveedor")[:200],
             "debe": CERO, "haber": monto},
        ],
        request=request,
    )
    asiento = contabilidad.contabilizar_asiento(asiento, usuario=usuario, request=request)
    pago = PagoCuentaPorPagar.objects.create(
        cuenta_por_pagar=cxp, fecha=fecha, monto=monto, cuenta_banco=cuenta_banco, referencia=referencia[:60],
        asiento=asiento, creado_por=usuario,
    )
    antes = instantanea(cxp)
    cxp.saldo -= monto
    cxp.estado = _estado_por_saldo(cxp)
    cxp.modificado_por = usuario
    cxp.save()
    registrar_evento(
        Bitacora.Accion.CREAR, usuario=usuario, entidad="pago_cxp", objeto_id=pago.pk,
        descripcion=f"Pago de {monto:,.2f} a {cxp.proveedor.nombre} por {cxp.numero_documento} (asiento {asiento.codigo})",
        valor_anterior=antes, valor_nuevo={**instantanea(cxp), "pago": f"{monto:.2f}", "asiento_pago": asiento.codigo},
        request=request,
    )
    return pago


@transaction.atomic
def anular_pago(pago, *, usuario, motivo, fecha=None, request=None):
    contabilidad, _ = _contabilidad()
    cxp = _bloquear(pago.cuenta_por_pagar)
    pago = PagoCuentaPorPagar.objects.select_for_update(of=("self",)).select_related("asiento").get(pk=pago.pk)
    motivo = _texto(motivo)
    if not motivo:
        raise ValidationError({"motivo": "Indique el motivo de la anulación."})
    if pago.estado == EstadoPago.ANULADO:
        raise ValidationError("El pago ya está anulado.")
    reversion = contabilidad.revertir_asiento(
        pago.asiento, usuario=usuario, motivo=f"Anulación de pago de {cxp.numero_documento}: {motivo}",
        fecha=fecha or max(timezone.localdate(), pago.fecha), request=request, permitir_tesoreria=True,
    )
    pago.estado = EstadoPago.ANULADO
    pago.asiento_anulacion = reversion
    pago.motivo_anulacion = motivo[:300]
    pago.anulado_por = usuario
    pago.anulado_en = timezone.now()
    pago.save()
    antes = instantanea(cxp)
    cxp.saldo += pago.monto
    cxp.estado = _estado_por_saldo(cxp)
    cxp.modificado_por = usuario
    cxp.save()
    registrar_evento(
        Bitacora.Accion.ANULAR, usuario=usuario, entidad="pago_cxp", objeto_id=pago.pk,
        descripcion=f"Anulación del pago de {pago.monto:,.2f} de {cxp.numero_documento} (reversión {reversion.codigo}). Motivo: {motivo}",
        valor_anterior=antes, valor_nuevo={**instantanea(cxp), "asiento_anulacion": reversion.codigo}, request=request,
    )
    return pago


# =============================================================================
# Consultas y vencimientos
# =============================================================================

def situacion_vencimiento(cxp, fecha):
    """('VENCIDA' | 'POR_VENCER' | 'AL_DIA' | None, días): días de atraso (vencida) o que faltan."""
    if cxp.estado in (Estado.PAGADA, Estado.ANULADA):
        return None, None
    dias = (cxp.fecha_vencimiento - fecha).days
    if dias < 0:
        return "VENCIDA", -dias
    return ("POR_VENCER" if dias <= DIAS_POR_VENCER else "AL_DIA"), dias


def consultar_cuentas_por_pagar(*, fecha, proveedor=None, estado=None, vencimiento=None, q=None):
    qs = CuentaPorPagar.objects.select_related("proveedor", "asiento").order_by("fecha_vencimiento", "id")
    if proveedor is not None:
        qs = qs.filter(proveedor=proveedor)
    if estado == "CON_SALDO":
        qs = qs.filter(estado__in=[Estado.PENDIENTE, Estado.PARCIAL])
    elif estado:
        qs = qs.filter(estado=estado)
    con_saldo = Q(estado__in=[Estado.PENDIENTE, Estado.PARCIAL])
    if vencimiento == "VENCIDA":
        qs = qs.filter(con_saldo, fecha_vencimiento__lt=fecha)
    elif vencimiento == "POR_VENCER":
        qs = qs.filter(con_saldo, fecha_vencimiento__gte=fecha, fecha_vencimiento__lte=fecha + timedelta(days=DIAS_POR_VENCER))
    elif vencimiento == "AL_DIA":
        qs = qs.filter(con_saldo, fecha_vencimiento__gt=fecha + timedelta(days=DIAS_POR_VENCER))
    if q:
        q = q.strip()
        qs = qs.filter(Q(numero_documento__icontains=q) | Q(concepto__icontains=q) | Q(proveedor__nombre__icontains=q))
    return qs


def resumen_cuentas_por_pagar(*, fecha):
    """Totales con saldo a la fecha: pendiente, vencido, por vencer y antigüedad de saldos vencidos."""
    pendientes = CuentaPorPagar.objects.filter(estado__in=[Estado.PENDIENTE, Estado.PARCIAL]).values(
        "fecha_vencimiento", "saldo"
    )
    total = vencido = por_vencer = CERO
    documentos = {"total": 0, "vencidos": 0, "por_vencer": 0}
    tramos = {nombre: CERO for _, _, nombre in TRAMOS}
    for d in pendientes:
        dias = (fecha - d["fecha_vencimiento"]).days
        total += d["saldo"]
        documentos["total"] += 1
        if dias > 0:
            vencido += d["saldo"]
            documentos["vencidos"] += 1
            for desde, hasta, nombre in TRAMOS:
                if dias >= desde and (hasta is None or dias <= hasta):
                    tramos[nombre] += d["saldo"]
        elif -dias <= DIAS_POR_VENCER:
            por_vencer += d["saldo"]
            documentos["por_vencer"] += 1
    t = lambda m: f"{m + CERO:.2f}"  # noqa: E731
    return {
        "fecha": fecha.isoformat(),
        "pendiente": t(total),
        "vencido": t(vencido),
        "por_vencer": t(por_vencer),
        "al_dia": t(total - vencido - por_vencer),
        "dias_por_vencer": DIAS_POR_VENCER,
        "documentos": documentos,
        "antiguedad": [{"tramo": n, "monto": t(m)} for n, m in tramos.items()],
        "pagado_en_el_mes": t(
            PagoCuentaPorPagar.objects.filter(
                estado=EstadoPago.VIGENTE, fecha__year=fecha.year, fecha__month=fecha.month, fecha__lte=fecha
            ).aggregate(s=Sum("monto"))["s"] or CERO
        ),
    }
