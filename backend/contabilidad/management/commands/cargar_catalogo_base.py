from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from contabilidad import services
from contabilidad.models import Cuenta

A, D = Cuenta.Naturaleza.ACREEDORA, Cuenta.Naturaleza.DEUDORA

# Catálogo bancario DE EJEMPLO, simplificado (no es el catálogo regulatorio oficial).
# (código, nombre, tipo solo en raíces, naturaleza si difiere de la del tipo)
CATALOGO = [
    ("1", "Activo", Cuenta.Tipo.ACTIVO, None),
    ("11", "Fondos disponibles", None, None),
    ("1101", "Caja", None, None),
    ("110101", "Caja general", None, None),
    ("110102", "Caja chica", None, None),
    ("1102", "Depósitos en el Banco Central de Reserva", None, None),
    ("1103", "Depósitos en bancos locales", None, None),
    ("1104", "Depósitos en bancos del exterior", None, None),
    ("12", "Inversiones financieras", None, None),
    ("1201", "Títulos valores para conservarse hasta el vencimiento", None, None),
    ("1202", "Títulos valores disponibles para la venta", None, None),
    ("13", "Cartera de préstamos", None, None),
    ("1301", "Préstamos vigentes", None, None),
    ("130101", "Préstamos de consumo", None, None),
    ("130102", "Préstamos para vivienda", None, None),
    ("130103", "Préstamos empresariales", None, None),
    ("1302", "Préstamos vencidos", None, None),
    ("1309", "Estimación por incobrabilidad de préstamos", None, A),
    ("14", "Otros activos", None, None),
    ("1401", "Cuentas por cobrar diversas", None, None),
    ("1402", "Gastos pagados por anticipado", None, None),
    ("1403", "IVA crédito fiscal", None, None),
    ("15", "Activo fijo", None, None),
    ("1501", "Terrenos", None, None),
    ("1502", "Edificaciones", None, None),
    ("1503", "Mobiliario y equipo", None, None),
    ("1504", "Equipo de cómputo", None, None),
    ("1509", "Depreciación acumulada", None, A),
    ("2", "Pasivo", Cuenta.Tipo.PASIVO, None),
    ("21", "Depósitos de clientes", None, None),
    ("2101", "Depósitos en cuenta corriente", None, None),
    ("2102", "Depósitos de ahorro", None, None),
    ("2103", "Depósitos a plazo", None, None),
    ("22", "Préstamos por pagar", None, None),
    ("2201", "Préstamos del Banco Central de Reserva", None, None),
    ("2202", "Préstamos de otros bancos", None, None),
    ("23", "Obligaciones a la vista", None, None),
    ("2301", "Cheques de caja y de gerencia", None, None),
    ("24", "Otros pasivos", None, None),
    ("2401", "Cuentas por pagar a proveedores", None, None),
    ("2402", "Retenciones y descuentos por pagar", None, None),
    ("2403", "Impuestos por pagar", None, None),
    ("2404", "Provisiones laborales", None, None),
    ("2405", "IVA retenido a terceros por pagar", None, None),
    ("2406", "IVA débito fiscal", None, None),
    ("3", "Patrimonio", Cuenta.Tipo.PATRIMONIO, None),
    ("31", "Capital social pagado", None, None),
    ("32", "Reservas de capital", None, None),
    ("3201", "Reserva legal", None, None),
    ("33", "Resultados", None, None),
    ("3301", "Resultados de ejercicios anteriores", None, None),
    ("3302", "Resultado del presente ejercicio", None, None),
    ("4", "Ingresos", Cuenta.Tipo.INGRESO, None),
    ("41", "Ingresos de operaciones de intermediación", None, None),
    ("4101", "Intereses sobre préstamos", None, None),
    ("4102", "Comisiones y recargos sobre préstamos", None, None),
    ("4103", "Intereses sobre inversiones", None, None),
    ("42", "Ingresos por servicios", None, None),
    ("4201", "Comisiones por servicios bancarios", None, None),
    ("4202", "Comisiones por tarjetas", None, None),
    ("43", "Otros ingresos", None, None),
    ("4301", "Ingresos no operacionales", None, None),
    ("5", "Gastos", Cuenta.Tipo.GASTO, None),
    ("51", "Costos de intermediación", None, None),
    ("5101", "Intereses sobre depósitos", None, None),
    ("5102", "Intereses sobre préstamos recibidos", None, None),
    ("5103", "Estimaciones por incobrabilidad", None, None),
    ("52", "Gastos de operación", None, None),
    ("5201", "Gastos de funcionarios y empleados", None, None),
    ("520101", "Salarios", None, None),
    ("520102", "Prestaciones sociales", None, None),
    ("520103", "Capacitación", None, None),
    ("5202", "Gastos generales", None, None),
    ("520201", "Energía eléctrica", None, None),
    ("520202", "Agua", None, None),
    ("520203", "Telecomunicaciones", None, None),
    ("520204", "Alquileres", None, None),
    ("520205", "Mantenimiento", None, None),
    ("520206", "Seguridad y vigilancia", None, None),
    ("520207", "Papelería y útiles", None, None),
    ("520208", "Publicidad", None, None),
    ("5203", "Depreciaciones y amortizaciones", None, None),
    ("53", "Otros gastos", None, None),
    ("5301", "Gastos no operacionales", None, None),
    ("6", "Cuentas de orden y contingentes", Cuenta.Tipo.ORDEN, None),
    ("61", "Contingentes deudoras", None, None),
    ("6101", "Garantías otorgadas", None, None),
    ("62", "Cuentas de orden deudoras", None, None),
    ("6201", "Valores en custodia", None, None),
    ("63", "Contingentes y cuentas de orden por contra", None, A),
    ("6301", "Responsabilidad por garantías otorgadas", None, A),
    ("6302", "Responsabilidad por valores en custodia", None, A),
]


def _padre_de(codigo, codigos):
    """El código más largo del catálogo que es prefijo propio de `codigo`."""
    candidatos = [c for c in codigos if codigo.startswith(c) and len(c) < len(codigo)]
    return max(candidatos, key=len) if candidatos else None


R = Cuenta.Rubro
V, F = Cuenta.Comportamiento.VARIABLE, Cuenta.Comportamiento.FIJO

# Clasificación de EJEMPLO (las subcuentas heredan): rubro, comportamiento del costo y controlabilidad.
CLASIFICACION = {
    "41": {"rubro_resultado": R.INGRESO_OPERACION},
    "42": {"rubro_resultado": R.INGRESO_OPERACION},
    "43": {"rubro_resultado": R.INGRESO_NO_OPERACION},
    # Los costos de intermediación varían con el volumen de depósitos y préstamos.
    "51": {"rubro_resultado": R.COSTO_INTERMEDIACION, "comportamiento_costo": V, "controlable": True},
    "52": {"rubro_resultado": R.GASTO_OPERACION, "comportamiento_costo": F, "controlable": True},
    # Papelería y útiles: crece con las operaciones de ventanilla.
    "520207": {"comportamiento_costo": V},
    # Alquileres y depreciaciones los decide la gerencia: el jefe del centro no los controla.
    "520204": {"controlable": False},
    "5203": {"controlable": False},
    "53": {"rubro_resultado": R.GASTO_NO_OPERACION, "comportamiento_costo": F, "controlable": False},
}


class Command(BaseCommand):
    help = "Carga un catálogo bancario de ejemplo simplificado. Idempotente: no duplica cuentas existentes."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda registrado como autor.")

    def handle(self, *args, usuario, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{usuario}'.")

        codigos = [c for c, *_ in CATALOGO]
        tipos_raiz = {c: t for c, _, t, _ in CATALOGO if t}
        creadas = existentes = 0

        for codigo, nombre, tipo, naturaleza in sorted(CATALOGO, key=lambda f: (len(f[0]), f[0])):
            if Cuenta.objects.filter(codigo=codigo).exists():
                existentes += 1
                continue
            codigo_padre = _padre_de(codigo, codigos)
            tipo_cuenta = tipos_raiz[codigo[0]]
            es_detalle = not any(c.startswith(codigo) and c != codigo for c in codigos)
            try:
                services.crear_cuenta(
                    usuario=autor,
                    codigo=codigo,
                    nombre=nombre,
                    padre=Cuenta.objects.get(codigo=codigo_padre) if codigo_padre else None,
                    tipo=tipo,
                    naturaleza=naturaleza,
                    acepta_movimientos=es_detalle,
                    # Ejemplo: las cuentas de balance quedan exentas de centro de costo;
                    # ingresos y gastos siempre lo exigen.
                    exenta_centro_costo=tipo_cuenta in Cuenta.TIPOS_BALANCE,
                )
                creadas += 1
            except ValidationError as exc:
                self.stderr.write(f"  {codigo} {nombre}: {'; '.join(exc.messages)}")

        self.stdout.write(self.style.SUCCESS(f"Cuentas creadas: {creadas}. Ya existían: {existentes}."))

        # Clasificación de ejemplo para los reportes segmentados (T3.2/T3.3). Solo completa la que falte.
        clasificadas = 0
        for codigo, datos in CLASIFICACION.items():
            cuenta = Cuenta.objects.filter(codigo=codigo).first()
            if cuenta is None:
                continue
            pendientes = {c: v for c, v in datos.items() if getattr(cuenta, c) in (None, "")}
            if pendientes:
                services.actualizar_cuenta(cuenta, usuario=autor, datos=pendientes)
                clasificadas += 1
        self.stdout.write(f"Cuentas clasificadas para reportes: {clasificadas}.")
