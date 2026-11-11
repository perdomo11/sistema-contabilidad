"""Generación de libros y reportes en Excel (.xlsx) con openpyxl (T7.1).

Formato común de todos los libros exportados:
- Encabezado: nombre de la empresa, NIT y NRC (de `settings.EMPRESA_*`), título del
  libro, periodo y una nota con la moneda y la fecha de generación.
- Fila de títulos de columna fija (inmovilizada) y repetida al imprimir.
- Montos como números con 2 decimales (`#,##0.00`), nunca como texto; fechas como fechas.
- Filas de grupo, subtotal y total con estilos propios; columnas ajustadas al contenido.

Solo da formato: los datos (y sus totales) los calculan los servicios de cada app.
"""
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
FORMATO_MONTO = "#,##0.00"
FORMATO_FECHA = "DD/MM/YYYY"

FILA_TITULOS = 7  # filas 1-5: encabezado; 6: separación; 7: títulos de columna
ANCHO_MAXIMO = 60

_delgada = Side(style="thin", color="9CA3AF")
_FUENTE_TITULOS = Font(bold=True, color="FFFFFF")
_RELLENO_TITULOS = PatternFill("solid", fgColor="1F3A5F")
_RELLENO_GRUPO = PatternFill("solid", fgColor="E8EEF6")
_RELLENO_TOTAL = PatternFill("solid", fgColor="F3F4F6")


@dataclass(frozen=True)
class Columna:
    titulo: str
    tipo: str = "texto"  # texto | monto | fecha | entero
    ancho: int | None = None  # ancho fijo opcional; si no, se ajusta al contenido


@dataclass
class Fila:
    """Fila con estilo. Una lista simple de valores equivale a `Fila(valores)`.

    estilo: None (detalle), "grupo" (encabezado de una sección o asiento),
    "subtotal" o "total".
    """

    valores: list
    estilo: str | None = None


def _normalizar(valor, tipo):
    if valor is None or valor == "":
        return None
    if tipo == "monto":
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    if tipo == "fecha" and isinstance(valor, str):
        return date.fromisoformat(valor[:10])
    if tipo == "entero" and isinstance(valor, str):
        return int(valor)
    return valor


def _texto_visible(valor, tipo):
    """Texto aproximado que verá el usuario, para calcular el ancho de la columna."""
    if valor is None:
        return ""
    if tipo == "monto":
        return f"{valor:,.2f}"
    if isinstance(valor, (date, datetime)):
        return "00/00/0000"
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    return str(valor)


def construir_libro(*, titulo, periodo, columnas, filas, usuario=None, hoja="Libro"):
    """Devuelve el contenido (bytes) del archivo .xlsx."""
    libro = Workbook()
    ws = libro.active
    ws.title = hoja[:31]
    ultima = get_column_letter(len(columnas))
    generado = timezone.localtime().strftime("%d/%m/%Y %H:%M")
    por = f" por {usuario.get_username()}" if usuario is not None else ""

    encabezado = [
        (settings.EMPRESA_NOMBRE, Font(bold=True, size=14)),
        (f"NIT: {settings.EMPRESA_NIT}    NRC: {settings.EMPRESA_NRC}", Font(size=10)),
        (titulo, Font(bold=True, size=12)),
        (periodo, Font(size=10)),
        (f"Cifras en dólares de los Estados Unidos de América (US$). Generado el {generado}{por}.",
         Font(size=9, italic=True, color="6B7280")),
    ]
    for numero, (texto, fuente) in enumerate(encabezado, start=1):
        ws.merge_cells(f"A{numero}:{ultima}{numero}")
        celda = ws.cell(row=numero, column=1, value=texto)
        celda.font = fuente
        celda.alignment = Alignment(horizontal="center")

    for indice, col in enumerate(columnas, start=1):
        celda = ws.cell(row=FILA_TITULOS, column=indice, value=col.titulo)
        celda.font = _FUENTE_TITULOS
        celda.fill = _RELLENO_TITULOS
        celda.border = Border(top=_delgada, bottom=_delgada, left=_delgada, right=_delgada)
        celda.alignment = Alignment(
            horizontal="right" if col.tipo == "monto" else "center", vertical="center", wrap_text=True
        )

    anchos = [len(col.titulo) for col in columnas]
    numero = FILA_TITULOS
    for fila in filas:
        if not isinstance(fila, Fila):
            fila = Fila(list(fila))
        numero += 1
        for indice, (col, valor) in enumerate(zip(columnas, fila.valores), start=1):
            valor = _normalizar(valor, col.tipo)
            if isinstance(valor, bool):
                valor = "Sí" if valor else "No"
            celda = ws.cell(row=numero, column=indice, value=valor)
            if col.tipo == "monto":
                celda.number_format = FORMATO_MONTO
            elif col.tipo == "fecha":
                celda.number_format = FORMATO_FECHA
                celda.alignment = Alignment(horizontal="center")
            if fila.estilo == "grupo":
                celda.font = Font(bold=True)
                celda.fill = _RELLENO_GRUPO
            elif fila.estilo in ("subtotal", "total"):
                celda.font = Font(bold=True)
                celda.fill = _RELLENO_TOTAL
                celda.border = Border(
                    top=_delgada, bottom=Side(style="double" if fila.estilo == "total" else "thin")
                )
            # Las filas de grupo suelen llevar un texto largo en una sola celda: no ensancha la columna.
            if fila.estilo != "grupo" or col.tipo != "texto":
                anchos[indice - 1] = max(anchos[indice - 1], len(_texto_visible(valor, col.tipo)))

    for indice, col in enumerate(columnas, start=1):
        ws.column_dimensions[get_column_letter(indice)].width = col.ancho or min(anchos[indice - 1] + 2, ANCHO_MAXIMO)

    ws.freeze_panes = ws.cell(row=FILA_TITULOS + 1, column=1)
    ws.print_title_rows = f"{FILA_TITULOS}:{FILA_TITULOS}"
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddFooter.center.text = "Página &P de &N"

    salida = BytesIO()
    libro.save(salida)
    return salida.getvalue()


def respuesta_excel(nombre_archivo, contenido):
    respuesta = HttpResponse(contenido, content_type=TIPO_XLSX)
    respuesta["Content-Disposition"] = f'attachment; filename="{nombre_archivo}"'
    return respuesta
