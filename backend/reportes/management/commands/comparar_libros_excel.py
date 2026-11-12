"""Compara libros Excel exportados (p. ej. desde Oracle) con los que genera HOY el sistema sobre la base
configurada (DATABASE_URL), celda por celda y con el mismo código de exportación (T7.1–T7.3).

Uso:
    python manage.py comparar_libros_excel ../libros_excel

Reconoce los archivos por su nombre: Catalogo, Libro_de_ventas_AAAA-MM, Libro_de_compras_AAAA-MM,
Libro_diario_AAAA y Libro_mayor_AAAA (el rango del diario y del mayor se toma de su fila 4, "Del … al …").
Se ignoran la fila 5 ("Generado el … por …") y, en el catálogo, la fecha de corte de la fila 4.
Los importes se comparan con tolerancia de medio centavo. Termina con código 1 si hay diferencias.
"""
import io
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from openpyxl import load_workbook

MAX_DIFERENCIAS = 8
RE_RANGO = re.compile(r"Del (\d{2})/(\d{2})/(\d{4}) al (\d{2})/(\d{2})/(\d{4})")


def _generador(ruta, primera_hoja):
    """(descripción, función que devuelve el .xlsx en bytes, filas a ignorar) según el nombre del archivo."""
    from contabilidad import exportacion as contab, services
    from tesoreria import exportacion as tesoreria
    from ventas import exportacion as ventas

    nombre = ruta.stem.lower()
    if "catalogo" in nombre:
        return "Catálogo de cuentas", lambda: contab.catalogo_xlsx(services.consultar_cuentas()), {4, 5}
    if m := re.search(r"ventas_(\d{4})-(\d{2})", nombre):
        anio, mes = int(m[1]), int(m[2])
        return f"Libro de ventas {anio}-{mes:02d}", lambda: ventas.libro_ventas_xlsx(anio=anio, mes=mes), {5}
    if m := re.search(r"compras_(\d{4})-(\d{2})", nombre):
        anio, mes = int(m[1]), int(m[2])
        return f"Libro de compras {anio}-{mes:02d}", lambda: tesoreria.libro_compras_xlsx(anio=anio, mes=mes), {5}
    if "diario" in nombre or "mayor" in nombre:
        rango = RE_RANGO.search(str(primera_hoja.cell(row=4, column=1).value or ""))
        if not rango:
            raise CommandError(f"{ruta.name}: no se encontró el rango 'Del dd/mm/aaaa al dd/mm/aaaa' en la fila 4.")
        g = [int(x) for x in rango.groups()]
        desde, hasta = date(g[2], g[1], g[0]), date(g[5], g[4], g[3])
        if "diario" in nombre:
            return f"Libro diario {desde}..{hasta}", lambda: contab.diario_xlsx(desde=desde, hasta=hasta), {5}
        return f"Libro mayor {desde}..{hasta}", lambda: contab.mayor_xlsx(desde=desde, hasta=hasta), {5}
    return None


def _normalizar(valor):
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, (int, float, Decimal)) and not isinstance(valor, bool):
        return Decimal(str(valor)).quantize(Decimal("0.01"))
    if valor == "":
        return None
    return valor


def _iguales(a, b):
    a, b = _normalizar(a), _normalizar(b)
    if isinstance(a, Decimal) and isinstance(b, Decimal):
        return abs(a - b) <= Decimal("0.005")
    return a == b


def _comparar(esperado, generado, ignorar):
    diferencias = []
    hojas_e = [ws.title for ws in esperado.worksheets]
    hojas_g = [ws.title for ws in generado.worksheets]
    if hojas_e != hojas_g:
        diferencias.append(f"hojas distintas: Excel {hojas_e} / sistema {hojas_g}")
    for ws_e in esperado.worksheets:
        if ws_e.title not in hojas_g:
            continue
        filas_e = list(ws_e.iter_rows(values_only=True))
        filas_g = list(generado[ws_e.title].iter_rows(values_only=True))
        if len(filas_e) != len(filas_g):
            diferencias.append(f"[{ws_e.title}] filas: Excel {len(filas_e)} / sistema {len(filas_g)}")
        for n in range(max(len(filas_e), len(filas_g))):
            if n + 1 in ignorar:
                continue
            fe = filas_e[n] if n < len(filas_e) else ()
            fg = filas_g[n] if n < len(filas_g) else ()
            for c in range(max(len(fe), len(fg))):
                ve = fe[c] if c < len(fe) else None
                vg = fg[c] if c < len(fg) else None
                if not _iguales(ve, vg):
                    diferencias.append(f"[{ws_e.title}] fila {n + 1}, col {c + 1}: Excel {ve!r} / sistema {vg!r}")
    return diferencias


class Command(BaseCommand):
    help = "Compara libros Excel exportados con los que genera el sistema sobre la base configurada."

    def add_arguments(self, parser):
        parser.add_argument("carpeta", help="Carpeta con los .xlsx (p. ej. ../libros_excel).")

    def handle(self, *args, carpeta, **options):
        archivos = sorted(Path(carpeta).glob("*.xlsx"))
        if not archivos:
            raise CommandError(f"No hay archivos .xlsx en {carpeta}.")
        total_dif = 0
        for ruta in archivos:
            esperado = load_workbook(ruta, data_only=True)
            gen = _generador(ruta, esperado.worksheets[0])
            if gen is None:
                self.stdout.write(self.style.WARNING(f"[OMITIDO] {ruta.name}: tipo de libro no reconocido"))
                continue
            descripcion, generar, ignorar = gen
            generado = load_workbook(io.BytesIO(generar()), data_only=True)
            diferencias = _comparar(esperado, generado, ignorar)
            total_dif += len(diferencias)
            if diferencias:
                self.stdout.write(self.style.ERROR(f"[DIFIERE] {ruta.name} ({descripcion}): {len(diferencias)} diferencia(s)"))
                for d in diferencias[:MAX_DIFERENCIAS]:
                    self.stdout.write(f"    - {d}")
                if len(diferencias) > MAX_DIFERENCIAS:
                    self.stdout.write(f"    … y {len(diferencias) - MAX_DIFERENCIAS} más")
            else:
                self.stdout.write(self.style.SUCCESS(f"[IGUAL  ] {ruta.name} ({descripcion})"))
        if total_dif:
            self.stdout.write(self.style.ERROR(f"Total: {total_dif} diferencia(s)."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("Todos los libros coinciden con el sistema."))
