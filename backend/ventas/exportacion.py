"""Exportación a Excel del libro de ventas (T7.3): una hoja por libro, con el formato común de T7.1."""
from config.excel import Columna, Fila, construir_libro_hojas

from .libro import libro_ventas

COLUMNAS_CONTRIBUYENTES = [
    Columna("N.º", "entero"),
    Columna("Fecha de emisión", "fecha"),
    Columna("N.º de documento"),
    Columna("NRC"),
    Columna("NIT"),
    Columna("Nombre del cliente"),
    Columna("Ventas exentas", "monto"),
    Columna("Ventas gravadas", "monto"),
    Columna("IVA débito fiscal", "monto"),
    Columna("Total", "monto"),
]

COLUMNAS_CONSUMIDOR = [
    Columna("Fecha", "fecha"),
    Columna("Del N.º"),
    Columna("Al N.º"),
    Columna("Documentos", "entero"),
    Columna("Anulados", "entero"),
    Columna("Ventas exentas", "monto"),
    Columna("Ventas gravadas (IVA incluido)", "monto"),
    Columna("IVA débito fiscal incluido", "monto"),
    Columna("Total ventas", "monto"),
]


def libro_ventas_xlsx(*, anio, mes, usuario=None):
    libro = libro_ventas(anio=anio, mes=mes)
    periodo = f"Mes de {libro['periodo']}"

    ccf = libro["contribuyentes"]
    filas_ccf = [
        [f["correlativo"], f["fecha_emision"], f["numero_documento"], f["cliente"]["nrc"], f["cliente"]["nit"],
         f"{f['cliente']['nombre']} (ANULADO)" if f["anulado"] else f["cliente"]["nombre"],
         f["ventas_exentas"], f["ventas_gravadas"], f["iva_debito_fiscal"], f["total"]]
        for f in ccf["filas"]
    ]
    t = ccf["totales"]
    filas_ccf.append(Fila([None, None, "", "", "", f"TOTALES DEL MES ({len(ccf['filas'])} documentos)",
                           t["ventas_exentas"], t["ventas_gravadas"], t["iva_debito_fiscal"], t["total"]], estilo="total"))

    cf = libro["consumidor_final"]
    filas_cf = [
        [f["fecha"], f["del_numero"], f["al_numero"], f["documentos"], f["anulados"],
         f["ventas_exentas"], f["ventas_gravadas"], f["iva_debito_fiscal"], f["total"]]
        for f in cf["filas"]
    ]
    t = cf["totales"]
    filas_cf.append(Fila([None, "TOTALES DEL MES", "", sum(f["documentos"] for f in cf["filas"]),
                          sum(f["anulados"] for f in cf["filas"]),
                          t["ventas_exentas"], t["ventas_gravadas"], t["iva_debito_fiscal"], t["total"]], estilo="total"))

    return construir_libro_hojas(
        [
            {"hoja": "Contribuyentes", "titulo": "Libro de ventas a contribuyentes", "periodo": periodo,
             "columnas": COLUMNAS_CONTRIBUYENTES, "filas": filas_ccf},
            {"hoja": "Consumidor final", "titulo": "Libro de ventas a consumidor final", "periodo": periodo,
             "columnas": COLUMNAS_CONSUMIDOR, "filas": filas_cf},
        ],
        usuario=usuario,
    )
