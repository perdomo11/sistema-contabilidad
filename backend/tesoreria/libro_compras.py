"""Libro de compras mensual (T7.2). Solo lectura.

Formato del libro de compras de El Salvador (contribuyentes inscritos en IVA): un renglón por comprobante
de crédito fiscal (CCF) recibido en el mes, en orden de fecha de emisión, con correlativo, datos del
proveedor, compras exentas, compras gravadas, IVA crédito fiscal, retención del 1 % y total de compras.

- Solo el CCF da derecho a crédito fiscal: facturas de consumidor final, recibos y otros no se anotan.
- Los documentos anulados no se anotan (su asiento quedó revertido).
- Total de compras = exentas + gravadas + IVA crédito fiscal (la retención se informa aparte: es IVA que
  el banco retiene al proveedor y entera a Hacienda; lo que se paga al proveedor es total − retención).
"""
import calendar
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError

from contabilidad.models import MESES

from .models import CuentaPorPagar

CERO = Decimal("0.00")
COLUMNAS_MONTO = ("compras_exentas", "compras_gravadas", "iva_credito_fiscal", "iva_retenido", "total")


def rango_mes(anio, mes):
    if not (2000 <= anio <= 2100 and 1 <= mes <= 12):
        raise ValidationError({"mes": "Indique un año y un mes válidos."})
    return date(anio, mes, 1), date(anio, mes, calendar.monthrange(anio, mes)[1])


def nombre_mes(anio, mes):
    return f"{MESES[mes - 1].capitalize()} {anio}"


def libro_compras(*, anio, mes):
    desde, hasta = rango_mes(anio, mes)
    documentos = (
        CuentaPorPagar.objects.filter(
            tipo_documento=CuentaPorPagar.TipoDocumento.CCF, fecha_emision__gte=desde, fecha_emision__lte=hasta,
        )
        .exclude(estado=CuentaPorPagar.Estado.ANULADA)
        .select_related("proveedor")
        .order_by("fecha_emision", "id")
    )
    filas, totales = [], dict.fromkeys(COLUMNAS_MONTO, CERO)
    for correlativo, c in enumerate(documentos, start=1):
        montos = {
            "compras_exentas": c.compras_exentas,
            "compras_gravadas": c.compras_gravadas,
            "iva_credito_fiscal": c.iva_credito_fiscal,
            "iva_retenido": c.iva_retenido,
            "total": c.compras_exentas + c.compras_gravadas + c.iva_credito_fiscal,
        }
        for k, v in montos.items():
            totales[k] += v
        filas.append({
            "correlativo": correlativo,
            "id": c.pk,
            "fecha_emision": c.fecha_emision.isoformat(),
            "tipo_documento": c.tipo_documento,
            "tipo_documento_display": c.get_tipo_documento_display(),
            "numero_documento": c.numero_documento,
            "proveedor": {"id": c.proveedor_id, "nombre": c.proveedor.nombre, "nit": c.proveedor.nit, "nrc": c.proveedor.nrc},
            **{k: f"{v:.2f}" for k, v in montos.items()},
        })
    return {
        "anio": anio,
        "mes": mes,
        "periodo": nombre_mes(anio, mes),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "filas": filas,
        "totales": {k: f"{v:.2f}" for k, v in totales.items()},
    }
