from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from centros_costo import services
from centros_costo.models import CentroCosto, ReglaAsignacion
from contabilidad.models import Cuenta
from tesoreria import services as tesoreria
from tesoreria.models import Proveedor

# Proveedores de EJEMPLO (ficticios): (NIT, nombre, NRC).
PROVEEDORES = [
    ("0614-150399-101-1", "Distribuidora Eléctrica del Centro, S.A. de C.V.", "12345-6"),
    ("0614-020288-102-4", "Acueductos Metropolitanos, S.A. de C.V.", "23456-7"),
    ("0614-110705-103-8", "Telecomunicaciones Unidas, S.A. de C.V.", "34567-8"),
    ("0614-300610-104-2", "Seguridad Integral Salvadoreña, S.A. de C.V.", "45678-9"),
    ("0614-051215-105-5", "Soluciones de Software Bancario, S.A. de C.V.", "56789-0"),
]

# Reglas de EJEMPLO: (código de cuenta | None, NIT del proveedor | None, código de centro, descripción).
REGLAS = [
    ("520201", None, "01-01", "Energía eléctrica de casa matriz: la administra Gerencia general."),
    ("520202", None, "01-01", "Agua de casa matriz: la administra Gerencia general."),
    ("520204", None, "01-01", "Alquileres: contratos firmados por Gerencia general."),
    ("520203", None, "01-03", "Telecomunicaciones: enlaces y telefonía a cargo de Tecnología."),
    ("520103", None, "01-04", "Capacitación del personal: presupuesto de Recursos humanos."),
    (None, "0614-300610-104-2", "01-01", "Contrato de vigilancia corporativo."),
    ("520205", "0614-051215-105-5", "01-03", "Mantenimiento del core bancario: Tecnología."),
]

INICIO = date(2026, 1, 1)


class Command(BaseCommand):
    help = "Carga proveedores y reglas de asignación de ejemplo (requiere catálogo y centros base). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda registrado como autor.")

    def handle(self, *args, usuario, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{usuario}'.")

        creados = 0
        for nit, nombre, nrc in PROVEEDORES:
            if not Proveedor.objects.filter(nit=nit).exists():
                tesoreria.crear_proveedor(usuario=autor, nit=nit, nombre=nombre, nrc=nrc)
                creados += 1
        self.stdout.write(f"Proveedores creados: {creados}. Ya existían: {len(PROVEEDORES) - creados}.")

        creadas = existentes = 0
        for codigo_cuenta, nit, codigo_centro, descripcion in REGLAS:
            try:
                cuenta = Cuenta.objects.get(codigo=codigo_cuenta) if codigo_cuenta else None
                proveedor = Proveedor.objects.get(nit=nit) if nit else None
                centro = CentroCosto.objects.get(codigo=codigo_centro)
            except (Cuenta.DoesNotExist, CentroCosto.DoesNotExist):
                raise CommandError("Faltan cuentas o centros: ejecute antes cargar_catalogo_base y cargar_centros_base.")
            if ReglaAsignacion.objects.filter(cuenta=cuenta, proveedor=proveedor).exists():
                existentes += 1
                continue
            try:
                services.crear_regla(
                    usuario=autor,
                    cuenta=cuenta,
                    proveedor=proveedor,
                    centro_costo=centro,
                    descripcion=descripcion,
                    vigente_desde=max(INICIO, centro.vigente_desde),
                )
                creadas += 1
            except ValidationError as exc:
                self.stderr.write(f"  {codigo_cuenta or ''} {nit or ''}: {'; '.join(exc.messages)}")
        self.stdout.write(self.style.SUCCESS(f"Reglas creadas: {creadas}. Ya existían: {existentes}."))
