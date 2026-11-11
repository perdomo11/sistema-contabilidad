"""Exportación a Excel del catálogo de cuentas, libro diario y libro mayor (T7.1).

Toma los datos de `services.consultar_cuentas` y de `libros.py` (no recalcula nada)
y les da el formato común de `config.excel`.
"""
from decimal import Decimal

from django.utils import timezone

from config.excel import Columna, Fila, construir_libro

from . import libros
from .models import Cuenta

CERO = Decimal("0.00")


def _fecha(d):
    return d.strftime("%d/%m/%Y")


def _rango(desde, hasta):
    return f"Del {_fecha(desde)} al {_fecha(hasta)}"


def _o_vacio(monto):
    """Celda vacía en lugar de 0.00 para la columna que no corresponde (cargo o abono)."""
    return monto if Decimal(monto) else None


# --- Catálogo de cuentas -----------------------------------------------------

COLUMNAS_CATALOGO = [
    Columna("Código"),
    Columna("Nombre de la cuenta"),
    Columna("Nivel", "entero"),
    Columna("Tipo"),
    Columna("Naturaleza"),
    Columna("Acepta movimientos"),
    Columna("Activa"),
    Columna("Cuenta padre"),
]


def catalogo_xlsx(cuentas, *, usuario=None):
    filas = []
    for c in cuentas:
        sangria = "    " * (c.nivel - 1)
        fila = Fila(
            [
                c.codigo,
                sangria + c.nombre,
                c.nivel,
                c.get_tipo_display(),
                c.get_naturaleza_display(),
                c.acepta_movimientos,
                c.activa,
                f"{c.padre.codigo} {c.padre.nombre}" if c.padre_id else "",
            ],
            # Las cuentas de agrupación se destacan como en el árbol de la pantalla.
            estilo=None if c.acepta_movimientos else "grupo",
        )
        filas.append(fila)
    filas.append(Fila([f"Total de cuentas: {len(filas)}"], estilo="total"))
    return construir_libro(
        titulo="Catálogo de cuentas",
        periodo=f"Al {_fecha(timezone.localdate())}",
        columnas=COLUMNAS_CATALOGO,
        filas=filas,
        usuario=usuario,
        hoja="Catálogo",
    )


# --- Libro diario ------------------------------------------------------------

COLUMNAS_DIARIO = [
    Columna("Fecha", "fecha"),
    Columna("Partida"),
    Columna("Código"),
    Columna("Cuenta / concepto"),
    Columna("Centro de costo"),
    Columna("Descripción"),
    Columna("Cargo", "monto"),
    Columna("Abono", "monto"),
]


def diario_xlsx(*, desde, hasta, usuario=None):
    asientos, totales = libros.libro_diario(desde=desde, hasta=hasta)
    filas = []
    for a in asientos:
        concepto = a.concepto + (f" (Ref. {a.referencia})" if a.referencia else "")
        filas.append(Fila([a.fecha, a.codigo, "", concepto, "", "", None, None], estilo="grupo"))
        debe = haber = CERO
        for linea in a.lineas.all():
            debe += linea.debe
            haber += linea.haber
            filas.append(
                [
                    None,
                    "",
                    linea.cuenta.codigo,
                    linea.cuenta.nombre,
                    linea.centro_costo.codigo if linea.centro_costo_id else "",
                    linea.descripcion,
                    _o_vacio(linea.debe),
                    _o_vacio(linea.haber),
                ]
            )
        filas.append(Fila([None, "", "", f"Total partida {a.codigo}", "", "", debe, haber], estilo="subtotal"))
    filas.append(Fila([None, "", "", "TOTALES DEL PERIODO", "", "", totales["debe"], totales["haber"]], estilo="total"))
    return construir_libro(
        titulo="Libro diario",
        periodo=_rango(desde, hasta),
        columnas=COLUMNAS_DIARIO,
        filas=filas,
        usuario=usuario,
        hoja="Diario",
    )


# --- Libro mayor -------------------------------------------------------------

COLUMNAS_MAYOR = [
    Columna("Fecha", "fecha"),
    Columna("Partida"),
    Columna("Concepto"),
    Columna("Cuenta"),
    Columna("Centro de costo"),
    Columna("Descripción"),
    Columna("Cargo", "monto"),
    Columna("Abono", "monto"),
    Columna("Saldo", "monto"),
]


def _filas_mayor(m):
    cta = m["cuenta"]
    naturaleza = Cuenta.Naturaleza(cta["naturaleza"]).label.lower()
    filas = [
        Fila([None, "", f"{cta['codigo']} {cta['nombre']} (naturaleza {naturaleza})"] + [""] * 3 + [None] * 3,
             estilo="grupo"),
        [None, "", "Saldo inicial", "", "", "", None, None, m["saldo_inicial"]],
    ]
    for mov in m["movimientos"]:
        filas.append(
            [
                mov["fecha"],
                mov["asiento_codigo"],
                mov["concepto"],
                mov["cuenta_codigo"],
                mov["centro_codigo"] or "",
                mov["descripcion"],
                _o_vacio(mov["debe"]),
                _o_vacio(mov["haber"]),
                mov["saldo"],
            ]
        )
    filas.append(
        Fila(
            [None, "", f"Totales y saldo final {cta['codigo']}", "", "", "",
             m["totales"]["debe"], m["totales"]["haber"], m["saldo_final"]],
            estilo="subtotal",
        )
    )
    return filas


def mayor_xlsx(*, desde, hasta, cuenta=None, usuario=None):
    """Mayor de una cuenta (de detalle o de agrupación) o, sin cuenta, de todas las cuentas de detalle."""
    if cuenta is not None:
        mayores = [libros.libro_mayor(cuenta=cuenta, desde=desde, hasta=hasta)]
        titulo = f"Libro mayor: {cuenta.codigo} {cuenta.nombre}"
    else:
        mayores = libros.libro_mayor_general(desde=desde, hasta=hasta)
        titulo = "Libro mayor"
    filas = []
    for m in mayores:
        filas.extend(_filas_mayor(m))
    if cuenta is None:
        debe = sum((Decimal(m["totales"]["debe"]) for m in mayores), CERO)
        haber = sum((Decimal(m["totales"]["haber"]) for m in mayores), CERO)
        filas.append(Fila([None, "", "TOTALES DEL PERIODO", "", "", "", debe, haber, None], estilo="total"))
    return construir_libro(
        titulo=titulo,
        periodo=_rango(desde, hasta),
        columnas=COLUMNAS_MAYOR,
        filas=filas,
        usuario=usuario,
        hoja="Mayor",
    )
