"""Libro de ventas mensual (T7.3). Solo lectura.

Dos libros, con el formato de El Salvador:

- **Ventas a contribuyentes** (CCF): un renglón por comprobante, en orden de fecha y número, con correlativo,
  datos del cliente, ventas exentas, ventas gravadas, IVA débito fiscal y total. Los CCF anulados se anotan
  con montos en cero y la marca "ANULADO" (el número emitido debe quedar en el libro).
- **Ventas a consumidor final** (facturas): un renglón por día con el rango de números emitidos (del … al …),
  ventas exentas, ventas gravadas **con IVA incluido** (como se cobran al público), el IVA débito fiscal que
  contienen y el total. Las facturas anuladas cuentan en el rango pero no en los montos.

El IVA débito fiscal del mes (contribuyentes + consumidor final) es igual al movimiento de la cuenta 2406.
"""
from collections import OrderedDict
from decimal import Decimal

from tesoreria.libro_compras import nombre_mes, rango_mes

from .models import DocumentoVenta

CERO = Decimal("0.00")
MONTOS_CCF = ("ventas_exentas", "ventas_gravadas", "iva_debito_fiscal", "total")
MONTOS_CF = ("ventas_exentas", "ventas_gravadas", "iva_debito_fiscal", "total")


def _t(valores):
    return {k: f"{v:.2f}" for k, v in valores.items()}


def _documentos(tipo, desde, hasta):
    return (
        DocumentoVenta.objects.filter(tipo_documento=tipo, fecha_emision__gte=desde, fecha_emision__lte=hasta)
        .select_related("cliente")
        .order_by("fecha_emision", "numero_documento", "id")
    )


def _contribuyentes(desde, hasta):
    filas, totales = [], dict.fromkeys(MONTOS_CCF, CERO)
    for correlativo, d in enumerate(_documentos(DocumentoVenta.TipoDocumento.CCF, desde, hasta), start=1):
        anulado = d.estado == DocumentoVenta.Estado.ANULADO
        montos = dict.fromkeys(MONTOS_CCF, CERO) if anulado else {
            "ventas_exentas": d.ventas_exentas, "ventas_gravadas": d.ventas_gravadas,
            "iva_debito_fiscal": d.iva_debito_fiscal, "total": d.total,
        }
        for k, v in montos.items():
            totales[k] += v
        filas.append({
            "correlativo": correlativo,
            "id": d.pk,
            "fecha_emision": d.fecha_emision.isoformat(),
            "numero_documento": d.numero_documento,
            "cliente": {"id": d.cliente_id, "nombre": d.cliente.nombre, "nit": d.cliente.nit or "", "nrc": d.cliente.nrc or ""},
            "anulado": anulado,
            **_t(montos),
        })
    return {"filas": filas, "totales": _t(totales)}


def _consumidor_final(desde, hasta):
    dias = OrderedDict()
    for d in _documentos(DocumentoVenta.TipoDocumento.FACTURA, desde, hasta):
        dia = dias.setdefault(d.fecha_emision, {"numeros": [], "anulados": 0, **dict.fromkeys(MONTOS_CF, CERO)})
        dia["numeros"].append(d.numero_documento)
        if d.estado == DocumentoVenta.Estado.ANULADO:
            dia["anulados"] += 1
            continue
        dia["ventas_exentas"] += d.ventas_exentas
        dia["ventas_gravadas"] += d.ventas_gravadas + d.iva_debito_fiscal  # con IVA incluido
        dia["iva_debito_fiscal"] += d.iva_debito_fiscal
        dia["total"] += d.total
    filas, totales = [], dict.fromkeys(MONTOS_CF, CERO)
    for fecha, dia in dias.items():
        for k in MONTOS_CF:
            totales[k] += dia[k]
        filas.append({
            "fecha": fecha.isoformat(),
            "del_numero": dia["numeros"][0],
            "al_numero": dia["numeros"][-1],
            "documentos": len(dia["numeros"]),
            "anulados": dia["anulados"],
            **_t({k: dia[k] for k in MONTOS_CF}),
        })
    return {"filas": filas, "totales": _t(totales)}


def libro_ventas(*, anio, mes):
    desde, hasta = rango_mes(anio, mes)
    contribuyentes = _contribuyentes(desde, hasta)
    consumidor = _consumidor_final(desde, hasta)
    debito = Decimal(contribuyentes["totales"]["iva_debito_fiscal"]) + Decimal(consumidor["totales"]["iva_debito_fiscal"])
    total = Decimal(contribuyentes["totales"]["total"]) + Decimal(consumidor["totales"]["total"])
    return {
        "anio": anio,
        "mes": mes,
        "periodo": nombre_mes(anio, mes),
        "desde": desde.isoformat(),
        "hasta": hasta.isoformat(),
        "contribuyentes": contribuyentes,
        "consumidor_final": consumidor,
        "resumen": {"iva_debito_fiscal": f"{debito:.2f}", "total_ventas": f"{total:.2f}"},
    }
