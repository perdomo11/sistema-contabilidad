"""Exportación a Excel del libro de compras (T7.2) con el formato común de `config.excel` (T7.1).

Toma los datos de `libro_compras.libro_compras` (no recalcula nada).
"""
from config.excel import Columna, Fila, construir_libro

from .libro_compras import libro_compras

COLUMNAS_LIBRO_COMPRAS = [
    Columna("N.º", "entero"),
    Columna("Fecha de emisión", "fecha"),
    Columna("Tipo de documento"),
    Columna("N.º de documento"),
    Columna("NRC"),
    Columna("NIT"),
    Columna("Nombre del proveedor"),
    Columna("Compras exentas", "monto"),
    Columna("Compras gravadas", "monto"),
    Columna("IVA crédito fiscal", "monto"),
    Columna("Retención / percepción 1 %", "monto"),
    Columna("Total compras", "monto"),
]


def libro_compras_xlsx(*, anio, mes, usuario=None):
    libro = libro_compras(anio=anio, mes=mes)
    filas = [
        [
            f["correlativo"],
            f["fecha_emision"],
            f["tipo_documento"],
            f["numero_documento"],
            f["proveedor"]["nrc"],
            f["proveedor"]["nit"],
            f["proveedor"]["nombre"],
            f["compras_exentas"],
            f["compras_gravadas"],
            f["iva_credito_fiscal"],
            f["iva_retenido"],
            f["total"],
        ]
        for f in libro["filas"]
    ]
    t = libro["totales"]
    filas.append(Fila(
        [None, None, "", "", "", "", f"TOTALES DEL MES ({len(libro['filas'])} documentos)",
         t["compras_exentas"], t["compras_gravadas"], t["iva_credito_fiscal"], t["iva_retenido"], t["total"]],
        estilo="total",
    ))
    return construir_libro(
        titulo="Libro de compras",
        periodo=f"Mes de {libro['periodo']}",
        columnas=COLUMNAS_LIBRO_COMPRAS,
        filas=filas,
        usuario=usuario,
        hoja="Compras",
    )
