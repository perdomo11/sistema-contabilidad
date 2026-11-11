"""Carga varios meses de operación verosímil de una red bancaria pequeña (T7.4). Idempotente.

    python manage.py cargar_datos_demo --usuario contador --desde 2026-08-01 --hasta 2026-11-30

Prepara lo que falte (catálogo, ejercicio, centros, reglas de asignación y de prorrateo, flujo), carga
mes a mes con los servicios de cada módulo, ejecuta el prorrateo de cada mes completo, verifica la
integridad y muestra un resumen. Los datos están en `config/datos_demo.py`.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count, Q

from config import datos_demo
from contabilidad import services as contabilidad
from contabilidad.models import Asiento, PeriodoContable
from tesoreria.libro_compras import libro_compras
from ventas.libro import libro_ventas


def _fecha(texto, nombre):
    try:
        return date.fromisoformat(texto)
    except ValueError:
        raise CommandError(f"--{nombre}: use el formato AAAA-MM-DD.") from None


def _m(valor):
    return f"{Decimal(valor):>14,.2f}"


class Command(BaseCommand):
    help = "Carga datos de demostración realistas (compras, ventas, planillas, pagos, depreciación, prorrateo). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda registrado como autor (p. ej. contador).")
        parser.add_argument("--desde", required=True, help="Primer día a cargar (AAAA-MM-DD).")
        parser.add_argument("--hasta", required=True, help="Último día a cargar (AAAA-MM-DD).")

    def handle(self, *args, usuario, desde, hasta, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{usuario}'.") from None
        desde, hasta = _fecha(desde, "desde"), _fecha(hasta, "hasta")
        if desde > hasta:
            raise CommandError("--desde no puede ser posterior a --hasta.")
        meses = list(datos_demo.meses_entre(desde, hasta))
        anios = sorted({a for a, _ in meses})

        self.preparar(autor, anios, meses)
        self.stdout.write(f"Cargando datos de demostración del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}…")
        try:
            resultado = datos_demo.CargaDemo(usuario=autor, desde=desde, hasta=hasta, salida=self.stdout.write).ejecutar()
        except ValidationError as exc:
            raise CommandError(f"La carga se detuvo: {'; '.join(exc.messages)}") from exc

        self.resumen(resultado, desde, hasta, meses)
        self.integridad(anios)

    # -------------------------------------------------------------------------

    def preparar(self, autor, anios, meses):
        """Ejercicios, periodos abiertos y datos base (todo idempotente)."""
        silencio = {"stdout": StringIO(), "stderr": StringIO()}
        call_command("cargar_catalogo_base", usuario=autor.username, **silencio)
        for anio in anios:
            if not PeriodoContable.objects.filter(anio=anio).exists():
                contabilidad.crear_ejercicio(usuario=autor, anio=anio)
                self.stdout.write(f"Ejercicio {anio} creado.")
        cerrados = [
            p.nombre for p in PeriodoContable.objects.filter(
                Q(*[Q(anio=a, mes=m) for a, m in meses], _connector=Q.OR), estado=PeriodoContable.Estado.CERRADO
            ).order_by("anio", "mes")
        ] if meses else []
        if cerrados:
            raise CommandError(
                f"No se puede registrar en periodos cerrados: {', '.join(cerrados)}. "
                "Reabra esos periodos (superusuario) o elija un rango con periodos abiertos. No se cargó nada."
            )
        call_command("cargar_centros_base", usuario=autor.username, **silencio)
        call_command("cargar_asignacion_base", usuario=autor.username, **silencio)
        for anio in anios:
            call_command("cargar_prorrateo_base", usuario=autor.username, anio=anio, **silencio)
        call_command("cargar_flujo_base", usuario=autor.username, **silencio)

    def resumen(self, r, desde, hasta, meses):
        etiquetas = [
            ("asientos", "Asientos contabilizados nuevos"), ("proveedores", "Proveedores nuevos"), ("clientes", "Clientes nuevos"),
            ("compras", "Documentos de compra"), ("pagos", "Pagos a proveedores"), ("ventas", "Documentos de venta"),
            ("planillas", "Planillas"), ("pagos_planilla", "Pagos de ISSS, AFP y renta"), ("depreciaciones", "Depreciaciones"),
            ("intereses_depositos", "Intereses sobre depósitos"), ("cartera", "Movimientos de cartera y depósitos"),
            ("prorrateos", "Prorrateos ejecutados"), ("apertura", "Asientos de apertura"), ("egresos_programados", "Egresos programados"),
        ]
        self.stdout.write(self.style.MIGRATE_HEADING("\nResumen de la carga"))
        for clave, texto in etiquetas:
            self.stdout.write(f"  {texto:<38}{r.creados.get(clave, 0):>6}")
        if not r.creados.get("asientos"):
            self.stdout.write(self.style.WARNING("  No se creó nada nuevo: los datos del rango ya estaban cargados."))
        for aviso in r.avisos:
            self.stdout.write(self.style.WARNING(f"  Aviso: {aviso}"))

        self.stdout.write(self.style.MIGRATE_HEADING("\nTotales por mes (todos los datos del mes, no solo los de esta carga)"))
        self.stdout.write(
            f"  {'Mes':<16}{'Asientos':>9}{'Compras CCF':>12}{'Gravadas':>15}{'IVA crédito':>15}"
            f"{'Ventas':>8}{'Total ventas':>15}{'IVA débito':>15}"
        )
        asientos = {
            (x["fecha__year"], x["fecha__month"]): x["n"]
            for x in Asiento.objects.filter(estado=Asiento.Estado.CONTABILIZADO, fecha__gte=desde, fecha__lte=hasta)
            .values("fecha__year", "fecha__month").annotate(n=Count("id"))
        }
        for anio, mes in meses:
            compras = libro_compras(anio=anio, mes=mes)
            ventas = libro_ventas(anio=anio, mes=mes)
            n_ventas = len(ventas["contribuyentes"]["filas"]) + sum(f["documentos"] for f in ventas["consumidor_final"]["filas"])
            self.stdout.write(
                f"  {compras['periodo']:<16}{asientos.get((anio, mes), 0):>9}{len(compras['filas']):>12}"
                f"{_m(compras['totales']['compras_gravadas'])}{_m(compras['totales']['iva_credito_fiscal'])}"
                f"{n_ventas:>8}{_m(ventas['resumen']['total_ventas'])}{_m(ventas['resumen']['iva_debito_fiscal'])}"
            )

    def integridad(self, anios):
        self.stdout.write(self.style.MIGRATE_HEADING("\nVerificación de integridad"))
        fallas = False
        for anio in anios:
            salida = StringIO()
            try:
                call_command("verificar_integridad", anio=anio, stdout=salida)
            except SystemExit:
                fallas = True
            for linea in salida.getvalue().splitlines():
                self.stdout.write(f"  {linea}")
        if fallas:
            raise CommandError("La verificación de integridad encontró fallas.")
        self.stdout.write(self.style.SUCCESS("Datos de demostración cargados y verificados."))
