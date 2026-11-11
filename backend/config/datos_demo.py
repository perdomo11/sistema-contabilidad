"""Datos de demostración realistas (T7.4): varios meses de operación de una red bancaria pequeña
(casa matriz y tres agencias) en El Salvador. Los usa el comando `cargar_datos_demo`.

Todo se registra con los servicios de cada módulo (nunca con inserts directos): así se aplican las
mismas reglas que en la operación real (partida doble, periodo abierto, centro de costo en ingresos y
gastos, IVA, asientos contabilizados, bitácora) y los triggers de Oracle no rechazan nada.

Datos FICTICIOS: proveedores, clientes, NIT y NRC tienen formato válido pero son inventados.

Idempotencia: cada elemento tiene una clave estable (NIT, número de documento o referencia del asiento)
y se omite si ya existe. El plan de cada mes se genera con una semilla fija (año y mes), así que el
mismo mes produce siempre los mismos documentos y montos, cualquiera que sea el rango pedido.
"""
import calendar
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.db.models import Sum

from centros_costo import prorrateo
from centros_costo.models import CentroCosto, EjecucionProrrateo, EstadoEjecucion, ReglaProrrateo
from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta, LineaAsiento, PeriodoContable
from tesoreria import cuentas_por_pagar as cpp
from tesoreria import proyeccion
from tesoreria import services as proveedores_srv
from tesoreria.models import CuentaPorPagar, EgresoProgramado, Proveedor
from ventas import documentos as ventas_srv
from ventas import services as clientes_srv
from ventas.models import Cliente, DocumentoVenta

D = Decimal
CERO = D("0.00")
CENTAVO = D("0.01")


def _c(valor):
    return D(valor).quantize(CENTAVO, rounding=ROUND_HALF_UP)


# =============================================================================
# Catálogos ficticios
# =============================================================================

# Proveedores: los 5 de `cargar_asignacion_base` más 13 nuevos. (NIT, nombre, NRC, prefijo de sus documentos)
PROVEEDORES = [
    ("0614-150399-101-1", "Distribuidora Eléctrica del Centro, S.A. de C.V.", "12345-6", "DEC"),
    ("0614-020288-102-4", "Acueductos Metropolitanos, S.A. de C.V.", "23456-7", "ACM"),
    ("0614-110705-103-8", "Telecomunicaciones Unidas, S.A. de C.V.", "34567-8", "TUN"),
    ("0614-300610-104-2", "Seguridad Integral Salvadoreña, S.A. de C.V.", "45678-9", "SIS"),
    ("0614-051215-105-5", "Soluciones de Software Bancario, S.A. de C.V.", "56789-0", "SSB"),
    ("0614-170812-106-9", "Redes y Fibra de Occidente, S.A. de C.V.", "67891-2", "RFO"),
    ("0614-080907-107-3", "Custodia y Traslado de Valores Express, S.A. de C.V.", "78912-3", "CTV"),
    ("0614-221118-108-6", "Licencias y Nube Centroamericana, S.A. de C.V.", "89123-4", "LNC"),
    ("0614-140503-109-0", "Papelería El Escribano, S.A. de C.V.", "91234-5", "PEE"),
    ("0614-260196-110-4", "Gráficas Volcán Azul, S.A. de C.V.", "102345-6", "GVA"),
    ("0614-031009-111-7", "Mantenimiento Integral de Edificios, S.A. de C.V.", "113456-7", "MIE"),
    ("0614-190714-112-1", "Climatización Técnica Izalco, S.A. de C.V.", "124567-8", "CTI"),
    ("0614-110316-113-5", "Limpieza Profesional Brisa, S.A. de C.V.", "135678-9", "LPB"),
    ("0614-050811-114-8", "Publicidad Faro Creativo, S.A. de C.V.", "146789-0", "PFC"),
    ("0614-270619-115-2", "Medios Digitales Quetzal, S.A. de C.V.", "157891-2", "MDQ"),
    ("0614-120400-116-6", "Inmobiliaria Los Próceres, S.A. de C.V.", "168912-3", "ILP"),
    ("0614-090902-117-0", "Instituto de Formación Financiera Atlacatl, S.A. de C.V.", "179123-4", "IFA"),
    ("0614-230517-118-3", "Equipos y Cómputo del Istmo, S.A. de C.V.", "181234-5", "ECI"),
]


@dataclass(frozen=True)
class Compra:
    """Compra recurrente de un proveedor.

    lineas: (cuenta, centro | None = según regla de asignación, monto base mensual).
    meses: None = todos; si no, función (mes) → bool.
    """
    nit: str
    concepto: str
    lineas: tuple
    dia: int
    plazo: int
    tipo: str = "CCF"
    retencion: bool = False
    exenta: bool = False  # servicio exento de IVA (p. ej. educación)
    variacion: float = 0.08
    meses: object = None


COMPRAS = [
    Compra("0614-150399-101-1", "Energía eléctrica", (("520201", None, 4200), ("520201", "02-01", 1600), ("520201", "03-01", 1100), ("520201", "04-01", 950)), dia=5, plazo=15),
    Compra("0614-020288-102-4", "Servicio de agua potable", (("520202", None, 380), ("520202", "02-01", 140), ("520202", "03-01", 110), ("520202", "04-01", 95)), dia=6, plazo=15),
    Compra("0614-110705-103-8", "Enlaces de datos y telefonía", (("520203", None, 3800),), dia=3, plazo=30, variacion=0.02),
    Compra("0614-170812-106-9", "Enlaces de fibra óptica de agencias", (("520203", None, 1450),), dia=8, plazo=30, variacion=0.0),
    Compra("0614-300610-104-2", "Servicio de vigilancia", (("520206", None, 3200), ("520206", "02-01", 2400), ("520206", "03-01", 2100), ("520206", "04-01", 2100)), dia=1, plazo=30, variacion=0.0),
    Compra("0614-080907-107-3", "Traslado de valores", (("520206", "02-01", 1300), ("520206", "03-01", 1050), ("520206", "04-01", 980)), dia=2, plazo=15, retencion=True),
    Compra("0614-051215-105-5", "Mantenimiento del core bancario", (("520205", None, 6500),), dia=10, plazo=30, variacion=0.0),
    Compra("0614-221118-108-6", "Licencias de software y servicios en la nube", (("520205", "01-03", 2800), ("520205", "90-01", 1900)), dia=12, plazo=30, variacion=0.03),
    Compra("0614-140503-109-0", "Papelería y útiles de oficina", (("520207", "02-01", 420), ("520207", "03-01", 310), ("520207", "04-01", 280), ("520207", "01-02", 190)), dia=15, plazo=30, retencion=True, variacion=0.2),
    Compra("0614-260196-110-4", "Chequeras y formularios impresos", (("520207", "02-01", 820), ("520207", "03-01", 560), ("520207", "04-01", 470)), dia=16, plazo=30, retencion=True, variacion=0.1, meses=lambda m: m % 2 == 0),
    Compra("0614-031009-111-7", "Mantenimiento preventivo de instalaciones", (("520205", "01-01", 650), ("520205", "02-01", 480), ("520205", "03-01", 390), ("520205", "04-01", 350)), dia=18, plazo=30, retencion=True, variacion=0.15),
    Compra("0614-190714-112-1", "Mantenimiento de aire acondicionado", (("520205", "01-03", 1150), ("520205", "01-01", 600)), dia=20, plazo=30, retencion=True, meses=lambda m: m % 2 == 1),
    Compra("0614-110316-113-5", "Servicio de limpieza", (("520205", "01-01", 900), ("520205", "02-01", 750), ("520205", "03-01", 600), ("520205", "04-01", 550)), dia=25, plazo=15, retencion=True, variacion=0.0),
    Compra("0614-050811-114-8", "Campaña publicitaria de créditos y cuentas", (("520208", "02-02", 1500), ("520208", "03-02", 1100), ("520208", "04-02", 900), ("520208", "01-05", 2000)), dia=14, plazo=30, variacion=0.25),
    # Factura de consumidor final: el IVA forma parte del costo (no hay crédito fiscal).
    Compra("0614-270619-115-2", "Pauta en redes sociales", (("520208", "01-05", 650),), dia=22, plazo=15, tipo="FACTURA", variacion=0.2),
    Compra("0614-120400-116-6", "Alquiler de locales de agencias", (("520204", "02-01", 4500), ("520204", "03-01", 3200), ("520204", "04-01", 2900)), dia=1, plazo=9, variacion=0.0),
    # Servicio educativo: exento de IVA.
    Compra("0614-090902-117-0", "Capacitación en prevención de lavado de dinero", (("520103", None, 1800),), dia=9, plazo=30, exenta=True, variacion=0.1, meses=lambda m: m % 2 == 0),
    Compra("0614-230517-118-3", "Equipo de cómputo y periféricos", (("1504", None, 11500),), dia=11, plazo=30, variacion=0.25, meses=lambda m: m % 3 == 0),
]

# Clientes contribuyentes: (NIT, nombre, NRC, saldo de préstamo empresarial o 0, centro de negocios)
EMPRESAS = [
    ("0614-210394-101-2", "Agroindustrias El Cafetal, S.A. de C.V.", "201457-3", 1_600_000, "01-05"),
    ("0614-061187-102-6", "Distribuidora Ferretera Lempa, S.A. de C.V.", "212568-4", 1_350_000, "01-05"),
    ("0614-150802-103-9", "Constructora Valle Verde, S.A. de C.V.", "223679-5", 1_200_000, "02-02"),
    ("0614-280999-104-3", "Textiles del Pacífico Salvadoreño, S.A. de C.V.", "234781-6", 1_050_000, "03-02"),
    ("0614-110410-105-7", "Farmacéutica Santa Lucía, S.A. de C.V.", "245892-7", 900_000, "02-02"),
    ("0614-030606-106-0", "Transportes Cumbre Alta, S.A. de C.V.", "256913-8", 800_000, "04-02"),
    ("0614-191113-107-4", "Hotel y Turismo Puerta del Sol, S.A. de C.V.", "267124-9", 600_000, "03-02"),
    ("0614-240117-108-8", "Alimentos La Cosecha, S.A. de C.V.", "278235-0", 500_000, "04-02"),
    ("0614-071201-109-1", "Colegio Bilingüe Los Almendros, S.A. de C.V.", "289346-1", 0, "02-02"),
    ("0614-170908-110-5", "Clínica Médica Monte Sion, S.A. de C.V.", "291457-2", 0, "03-02"),
    ("0614-020515-111-9", "Supermercados Familia Unida, S.A. de C.V.", "302568-3", 0, "02-02"),
    ("0614-130320-112-2", "Tecnología Educativa Maya, S.A. de C.V.", "313679-4", 0, "04-02"),
]

# Consumidores finales (personas ficticias; NIT opcional) y el cliente genérico de ventanilla.
PERSONAS = [
    ("0614-120385-121-4", "María José Hernández Portillo"),
    ("0614-030790-122-8", "Carlos Alberto Martínez Rivas"),
    ("0210-251178-101-1", "Ana Gabriela Flores de Mejía"),
    ("1217-090892-102-5", "José Roberto Ayala Castillo"),
    ("", "Rosa Elena Quintanilla Guardado"),
    ("0614-171195-123-1", "Luis Fernando Orellana Pineda"),
    ("", "Karla Patricia Menjívar Romero"),
    ("1217-300483-103-9", "Mario Ernesto Chávez Linares"),
    ("0210-140688-104-2", "Sofía Alejandra Rivera Campos"),
    ("", "Juan Carlos Escobar Molina"),
    ("0614-221099-124-5", "Daniela Beatriz Aguilar Vásquez"),
    ("", "Óscar Armando Lemus Durán"),
]
CLIENTES_VARIOS = "Clientes varios (ventanilla)"

# Agencias: (sucursal, área de negocios, participación en la cartera de consumo y vivienda)
AGENCIAS = [("02", "02-02", D("0.45")), ("03", "03-02", D("0.30")), ("04", "04-02", D("0.25"))]

# Planilla: centro → (personas, salario promedio). Aportes patronales ISSS 7.5 % + AFP 8.75 %;
# descuentos al empleado ISSS 3 % + AFP 7.25 % + renta (aproximación del 7 %).
PLANILLA = {
    "01-01": (6, 2150), "01-02": (8, 1250), "01-03": (10, 1450), "01-04": (4, 1100), "01-05": (12, 1150),
    "01-06": (5, 1350), "02-01": (14, 640), "02-02": (6, 950), "03-01": (9, 620), "03-02": (4, 900),
    "04-01": (8, 610), "04-02": (3, 880), "90-01": (5, 1500),
}
TASA_PATRONAL = D("0.1625")
TASA_LABORAL = D("0.1725")

# Depreciación en línea recta (tasa anual) y su distribución por centro.
DEPRECIACION = {"1502": D("0.025"), "1503": D("0.10"), "1504": D("0.25")}
DISTRIBUCION_DEPRECIACION = [
    ("01-01", D("0.20")), ("01-02", D("0.05")), ("01-03", D("0.25")), ("01-04", D("0.03")), ("01-05", D("0.07")),
    ("01-06", D("0.05")), ("02-01", D("0.15")), ("03-01", D("0.11")), ("04-01", D("0.09")),
]

# Intereses sobre depósitos: costo de captación por centro.
DISTRIBUCION_INTERESES_DEPOSITOS = [("01-06", D("0.30")), ("02-02", D("0.30")), ("03-02", D("0.22")), ("04-02", D("0.18"))]

TASA_EMPRESARIAL = D("0.11")
CARTERA_CONSUMO, TASA_CONSUMO = D("8000000"), D("0.18")
CARTERA_VIVIENDA, TASA_VIVIENDA = D("5000000"), D("0.09")
DEPOSITOS, TASA_DEPOSITOS = D("16000000"), D("0.025")

# Saldos de apertura (balance) y aporte de capital: se registran una sola vez.
SALDOS_INICIALES = [
    ("130101", "debe", 8_000_000), ("130102", "debe", 5_000_000), ("130103", "debe", 8_000_000),
    ("1102", "debe", 2_600_000), ("110101", "debe", 450_000), ("1103", "debe", 400_000),
    ("1502", "debe", 1_800_000), ("1503", "debe", 380_000), ("1504", "debe", 520_000),
    ("2102", "haber", 8_200_000), ("2103", "haber", 5_600_000), ("2101", "haber", 2_200_000),
    ("2202", "haber", 5_000_000), ("1509", "haber", 650_000), ("31", "haber", 3_500_000),
    ("3201", "haber", 700_000), ("3301", "haber", 1_300_000),
]
APORTE_CAPITAL = D("1000000")
REF_SALDOS, REF_APORTE = "SALDOS-INICIALES-DEMO", "APORTE-CAPITAL-DEMO"

BANCO = "1103"


# =============================================================================
# Plan mensual (determinista)
# =============================================================================

def meses_entre(desde, hasta):
    anio, mes = desde.year, desde.month
    while (anio, mes) <= (hasta.year, hasta.month):
        yield anio, mes
        anio, mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)


def _fecha(anio, mes, dia):
    return date(anio, mes, min(dia, calendar.monthrange(anio, mes)[1]))


def _variar(rng, monto, variacion):
    return _c(D(monto) * (1 + D(str(rng.uniform(-variacion, variacion)))))


def _viernes(anio, mes):
    ultimo = calendar.monthrange(anio, mes)[1]
    return [date(anio, mes, d) for d in range(1, ultimo + 1) if date(anio, mes, d).weekday() == 4]


def plan_compras(anio, mes):
    rng = random.Random(f"compras-{anio}-{mes}")
    plan = []
    for compra in COMPRAS:
        variaciones = [_variar(rng, monto, compra.variacion) for _, _, monto in compra.lineas]
        if compra.meses is not None and not compra.meses(mes):
            continue
        prefijo = next(p for nit, _, _, p in PROVEEDORES if nit == compra.nit)
        emision = _fecha(anio, mes, compra.dia)
        plan.append({
            "compra": compra,
            "numero": f"{prefijo}-{anio % 100:02d}{mes:02d}{rng.randint(100, 999)}",
            "emision": emision,
            "vence": emision + timedelta(days=compra.plazo),
            "lineas": [(cuenta, centro, monto) for (cuenta, centro, _), monto in zip(compra.lineas, variaciones)],
        })
    return plan


def plan_ventas(anio, mes):
    """CCF a empresas (intereses exentos + comisiones gravadas) y facturas de consumidor final."""
    rng = random.Random(f"ventas-{anio}-{mes}")
    ccf, facturas = [], []
    for i, (nit, nombre, _, prestamo, centro) in enumerate(EMPRESAS):
        dia = 5 + (i * 3) % 21
        lineas = []
        if prestamo:
            lineas.append(("4101", centro, _c(D(prestamo) * TASA_EMPRESARIAL / 12), True, "Intereses de préstamo empresarial"))
            lineas.append(("4102", centro, _c(rng.randint(15000, 40000) / 100), False, "Comisión por manejo de línea de crédito"))
        else:
            lineas.append(("4201", centro, _c(rng.randint(25000, 90000) / 100), False, "Servicio de pago de planillas y banca empresarial"))
            lineas.append(("4202", centro, _c(rng.randint(40000, 150000) / 100), False, "Comisión por adquirencia de tarjetas (POS)"))
        ccf.append({"nit": nit, "fecha": _fecha(anio, mes, dia), "lineas": lineas, "concepto": "Intereses y comisiones del mes" if prestamo else "Servicios bancarios del mes"})

    # Cartera de consumo y vivienda: cobro semanal por agencia (cliente genérico de ventanilla).
    viernes = _viernes(anio, mes)
    interes_mes = CARTERA_CONSUMO * TASA_CONSUMO / 12 + CARTERA_VIVIENDA * TASA_VIVIENDA / 12
    for fecha in viernes:
        for sucursal, centro, participacion in AGENCIAS:
            interes = _c(interes_mes * participacion / len(viernes) * (1 + D(str(rng.uniform(-0.05, 0.05)))))
            comision = _c(D(9000) * participacion / len(viernes) * (1 + D(str(rng.uniform(-0.15, 0.15)))))
            facturas.append({"cliente": CLIENTES_VARIOS, "fecha": fecha, "concepto": f"Cobros de ventanilla de la agencia {sucursal}, semana del {fecha:%d/%m}",
                             "lineas": [("4101", centro, interes, True, "Intereses de préstamos de consumo y vivienda"),
                                        ("4201", centro, comision, False, "Comisiones por remesas, chequeras y constancias")]})
    # Servicios a personas.
    for _ in range(6):
        nit, nombre = PERSONAS[rng.randrange(len(PERSONAS))]
        _, centro, _ = AGENCIAS[rng.randrange(len(AGENCIAS))]
        if rng.random() < 0.5:
            linea = ("4202", centro, _c(rng.choice([35, 45, 60])), False, "Membresía anual de tarjeta de crédito")
        else:
            linea = ("4102", centro, _c(rng.randint(7500, 15000) / 100), False, "Comisión por apertura de préstamo personal")
        facturas.append({"cliente": nombre, "fecha": _fecha(anio, mes, rng.randint(2, 27)), "concepto": linea[4], "lineas": [linea]})

    ccf.sort(key=lambda d: (d["fecha"], d["nit"]))
    facturas.sort(key=lambda d: (d["fecha"], d["cliente"]))
    for n, d in enumerate(ccf, start=1):
        d["numero"] = f"{anio % 100:02d}{mes:02d}{n:04d}"
    for n, d in enumerate(facturas, start=1):
        d["numero"] = f"{anio % 100:02d}{mes:02d}{n:05d}"
    return ccf, facturas


def plan_planilla(anio, mes):
    rng = random.Random(f"planilla-{anio}-{mes}")
    return {centro: _c(D(personas * salario) * (1 + D(str(rng.uniform(0, 0.03))))) for centro, (personas, salario) in PLANILLA.items()}


def plan_cartera(anio, mes):
    """Desembolsos, recuperaciones y captación neta del mes."""
    rng = random.Random(f"cartera-{anio}-{mes}")
    miles = lambda a, b: D(rng.randint(a, b) * 1000)  # noqa: E731
    return {
        "desembolsos": [("130101", miles(180, 320)), ("130102", miles(60, 140)), ("130103", miles(150, 400))],
        "recuperaciones": [("130101", miles(170, 280)), ("130102", miles(40, 80)), ("130103", miles(120, 300))],
        "captacion": [("2102", miles(60, 220)), ("2101", miles(-40, 90))],
    }


def _repartir(total, distribucion):
    """Reparte `total` según proporciones; el último centro absorbe el redondeo."""
    partes, acumulado = [], CERO
    for i, (centro, proporcion) in enumerate(distribucion):
        monto = total - acumulado if i == len(distribucion) - 1 else _c(total * proporcion)
        acumulado += monto
        partes.append((centro, monto))
    return partes


# =============================================================================
# Carga
# =============================================================================

@dataclass
class Resultado:
    creados: dict = field(default_factory=dict)
    avisos: list = field(default_factory=list)

    def sumar(self, clave, n=1):
        self.creados[clave] = self.creados.get(clave, 0) + n


class CargaDemo:
    def __init__(self, *, usuario, desde, hasta, salida=None):
        self.usuario, self.desde, self.hasta = usuario, desde, hasta
        self.salida = salida or (lambda texto: None)
        self.r = Resultado()
        self.cuentas = {c.codigo: c for c in Cuenta.objects.all()}
        self.centros = {c.codigo: c for c in CentroCosto.objects.all()}

    # --- utilidades -----------------------------------------------------------

    def en_rango(self, fecha):
        return self.desde <= fecha <= self.hasta

    def asiento(self, *, referencia, fecha, concepto, lineas, clave):
        """Asiento manual contabilizado, una sola vez por referencia."""
        if Asiento.objects.filter(referencia=referencia, estado=Asiento.Estado.CONTABILIZADO).exists():
            return None
        lineas = [l for l in lineas if (l.get("debe") or l.get("haber"))]
        a = contabilidad.crear_asiento(usuario=self.usuario, fecha=fecha, concepto=concepto, referencia=referencia, lineas=lineas)
        a = contabilidad.contabilizar_asiento(a, usuario=self.usuario)
        self.r.sumar(clave)
        return a

    def linea(self, cuenta, debe=CERO, haber=CERO, centro=None, descripcion=""):
        return {"cuenta": self.cuentas[cuenta], "centro_costo": self.centros[centro] if centro else None,
                "debe": _c(debe), "haber": _c(haber), "descripcion": descripcion}

    # --- catálogos --------------------------------------------------------------

    def catalogos(self):
        for nit, nombre, nrc, _ in PROVEEDORES:
            if not Proveedor.objects.filter(nit=nit).exists():
                proveedores_srv.crear_proveedor(usuario=self.usuario, nit=nit, nombre=nombre, nrc=nrc)
                self.r.sumar("proveedores")
        for nit, nombre, nrc, _, _ in EMPRESAS:
            if not Cliente.objects.filter(nit=nit).exists():
                clientes_srv.crear_cliente(usuario=self.usuario, nombre=nombre, tipo="CONTRIBUYENTE", nit=nit, nrc=nrc)
                self.r.sumar("clientes")
        for nit, nombre in [*PERSONAS, ("", CLIENTES_VARIOS)]:
            if not Cliente.objects.filter(nombre=nombre, tipo="CONSUMIDOR_FINAL").exists():
                clientes_srv.crear_cliente(usuario=self.usuario, nombre=nombre, tipo="CONSUMIDOR_FINAL", nit=nit)
                self.r.sumar("clientes")
        self.proveedores = {p.nit: p for p in Proveedor.objects.filter(nit__in=[p[0] for p in PROVEEDORES])}
        self.clientes = {c.nit or c.nombre: c for c in Cliente.objects.all()}
        self.egresos_programados()

    def egresos_programados(self):
        """Planilla y aportes como egresos programados, para la proyección de tesorería."""
        neto = sum(plan_planilla(self.desde.year, self.desde.month).values(), CERO)
        for concepto, dia, monto in (
            ("Planilla mensual (líquido a pagar)", 28, _c(neto * (1 - TASA_LABORAL))),
            ("ISSS, AFP y renta de la planilla", 10, _c(neto * (TASA_LABORAL + TASA_PATRONAL))),
        ):
            if not EgresoProgramado.objects.filter(concepto=concepto).exists():
                proyeccion.crear_egreso_programado(
                    usuario=self.usuario, concepto=concepto, categoria=EgresoProgramado.Categoria.PLANILLA, monto=monto,
                    frecuencia=EgresoProgramado.Frecuencia.MENSUAL, fecha_inicio=self.desde, dia_mes=dia,
                )
                self.r.sumar("egresos_programados")

    # --- apertura ---------------------------------------------------------------

    def apertura(self):
        if not self.en_rango(self.desde):
            return
        self.asiento(
            referencia=REF_SALDOS, fecha=self.desde, clave="apertura",
            concepto="Saldos iniciales de cartera, depósitos, activo fijo y patrimonio (datos de demostración)",
            lineas=[self.linea(c, **{lado: D(m)}) for c, lado, m in SALDOS_INICIALES],
        )
        self.asiento(
            referencia=REF_APORTE, fecha=self.desde, clave="apertura", concepto="Aporte de capital de los accionistas",
            lineas=[self.linea(BANCO, debe=APORTE_CAPITAL), self.linea("31", haber=APORTE_CAPITAL)],
        )

    # --- compras ---------------------------------------------------------------

    def compras(self, anio, mes):
        for item in plan_compras(anio, mes):
            compra = item["compra"]
            if not self.en_rango(item["emision"]):
                continue
            proveedor = self.proveedores[compra.nit]
            existe = CuentaPorPagar.objects.filter(
                proveedor=proveedor, tipo_documento=compra.tipo, numero_documento=item["numero"]
            ).exclude(estado=CuentaPorPagar.Estado.ANULADA).exists()
            if existe:
                continue
            lineas = [{"cuenta": self.cuentas[c], "centro_costo": self.centros[cc] if cc else None, "monto": m}
                      for c, cc, m in item["lineas"]]
            base = sum((m for _, _, m in item["lineas"]), CERO)
            fiscal = {}
            if compra.tipo == "CCF":
                fiscal = {"compras_exentas": base} if compra.exenta else {"aplica_retencion": compra.retencion and base >= cpp.MINIMO_RETENCION}
            cpp.registrar_cuenta_por_pagar(
                usuario=self.usuario, proveedor=proveedor, tipo_documento=compra.tipo, numero_documento=item["numero"],
                fecha_emision=item["emision"], fecha_vencimiento=item["vence"], concepto=f"{compra.concepto} de {_mes(mes)} {anio}",
                lineas=lineas, **fiscal,
            )
            self.r.sumar("compras")

    def pagos(self):
        """Paga cada documento de los proveedores de demostración en su vencimiento (si cae en el rango)."""
        pendientes = CuentaPorPagar.objects.filter(
            proveedor__nit__in=[p[0] for p in PROVEEDORES], estado=CuentaPorPagar.Estado.PENDIENTE,
            fecha_vencimiento__lte=self.hasta, fecha_vencimiento__gte=self.desde,
        ).order_by("fecha_vencimiento", "id")
        for cxp in pendientes:
            cpp.registrar_pago(cxp, usuario=self.usuario, fecha=cxp.fecha_vencimiento, monto=cxp.saldo,
                               cuenta_banco=self.cuentas[BANCO], referencia=f"TRF-{cxp.numero_documento}")
            self.r.sumar("pagos")

    # --- ventas ----------------------------------------------------------------

    def ventas(self, anio, mes):
        ccf, facturas = plan_ventas(anio, mes)
        for tipo, docs in (("CCF", ccf), ("FACTURA", facturas)):
            for d in docs:
                if not self.en_rango(d["fecha"]):
                    continue
                if DocumentoVenta.objects.filter(tipo_documento=tipo, numero_documento=d["numero"]).exists():
                    continue
                cliente = self.clientes[d["nit"]] if tipo == "CCF" else self.clientes[next((n for n, nom in PERSONAS if nom == d["cliente"] and n), d["cliente"])]
                ventas_srv.registrar_documento_venta(
                    usuario=self.usuario, cliente=cliente, tipo_documento=tipo, numero_documento=d["numero"],
                    fecha_emision=d["fecha"], concepto=d["concepto"],
                    lineas=[{"cuenta": self.cuentas[c], "centro_costo": self.centros[cc], "monto": m, "exenta": ex, "descripcion": desc}
                            for c, cc, m, ex, desc in d["lineas"]],
                )
                self.r.sumar("ventas")

    # --- planilla, intereses, depreciación, cartera ------------------------------

    def planilla(self, anio, mes):
        fecha = _fecha(anio, mes, 28)
        if not self.en_rango(fecha):
            return
        salarios = plan_planilla(anio, mes)
        total = sum(salarios.values(), CERO)
        laboral, patronal = _c(total * TASA_LABORAL), CERO
        lineas = []
        for centro, monto in salarios.items():
            aporte = _c(monto * TASA_PATRONAL)
            patronal += aporte
            lineas.append(self.linea("520101", debe=monto, centro=centro, descripcion="Salarios"))
            lineas.append(self.linea("520102", debe=aporte, centro=centro, descripcion="Aportes patronales ISSS y AFP"))
        lineas += [
            self.linea(BANCO, haber=total - laboral, descripcion="Líquido pagado a empleados"),
            self.linea("2402", haber=laboral, descripcion="Descuentos ISSS, AFP y renta"),
            self.linea("2404", haber=patronal, descripcion="Aportes patronales por pagar"),
        ]
        self.asiento(referencia=f"PLANILLA-{anio}-{mes:02d}", fecha=fecha, clave="planillas",
                     concepto=f"Planilla de sueldos de {_mes(mes)} {anio}", lineas=lineas)

    def pago_planilla(self, anio, mes):
        """Pago de ISSS, AFP y renta de la planilla del mes, el día 10 del mes siguiente."""
        sig_anio, sig_mes = (anio + 1, 1) if mes == 12 else (anio, mes + 1)
        fecha = date(sig_anio, sig_mes, 10)
        planilla = Asiento.objects.filter(referencia=f"PLANILLA-{anio}-{mes:02d}", estado=Asiento.Estado.CONTABILIZADO).first()
        if planilla is None or not self.en_rango(fecha):
            return
        montos = {c: planilla.lineas.filter(cuenta__codigo=c).aggregate(s=Sum("haber"))["s"] or CERO for c in ("2402", "2404")}
        self.asiento(
            referencia=f"PAGO-PLANILLA-{anio}-{mes:02d}", fecha=fecha, clave="pagos_planilla",
            concepto=f"Pago de ISSS, AFP y renta de la planilla de {_mes(mes)} {anio}",
            lineas=[self.linea("2402", debe=montos["2402"]), self.linea("2404", debe=montos["2404"]),
                    self.linea(BANCO, haber=montos["2402"] + montos["2404"])],
        )

    def intereses_depositos(self, anio, mes):
        fecha = date(anio, mes, calendar.monthrange(anio, mes)[1])
        if not self.en_rango(fecha):
            return
        total = _c(DEPOSITOS * TASA_DEPOSITOS / 12)
        ahorro = _c(total * D("0.55"))
        lineas = [self.linea("5101", debe=m, centro=c) for c, m in _repartir(total, DISTRIBUCION_INTERESES_DEPOSITOS)]
        lineas += [self.linea("2102", haber=ahorro, descripcion="Capitalizados a cuentas de ahorro"),
                   self.linea("2103", haber=total - ahorro, descripcion="Capitalizados a depósitos a plazo")]
        self.asiento(referencia=f"INT-DEPOSITOS-{anio}-{mes:02d}", fecha=fecha, clave="intereses_depositos",
                     concepto=f"Intereses sobre depósitos de {_mes(mes)} {anio}", lineas=lineas)

    def depreciacion(self, anio, mes):
        fecha = date(anio, mes, calendar.monthrange(anio, mes)[1])
        if not self.en_rango(fecha):
            return
        total = CERO
        for codigo, tasa in DEPRECIACION.items():
            saldo = LineaAsiento.objects.filter(
                cuenta__codigo=codigo, asiento__estado=Asiento.Estado.CONTABILIZADO, asiento__fecha__lte=fecha,
            ).aggregate(d=Sum("debe"), h=Sum("haber"))
            total += _c(((saldo["d"] or CERO) - (saldo["h"] or CERO)) * tasa / 12)
        if total <= 0:
            return
        lineas = [self.linea("5203", debe=m, centro=c) for c, m in _repartir(total, DISTRIBUCION_DEPRECIACION)]
        lineas.append(self.linea("1509", haber=total))
        self.asiento(referencia=f"DEPRECIACION-{anio}-{mes:02d}", fecha=fecha, clave="depreciaciones",
                     concepto=f"Depreciación de activo fijo de {_mes(mes)} {anio}", lineas=lineas)

    def cartera(self, anio, mes):
        fecha = _fecha(anio, mes, 20)
        if not self.en_rango(fecha):
            return
        p = plan_cartera(anio, mes)
        desembolsos = sum((m for _, m in p["desembolsos"]), CERO)
        self.asiento(referencia=f"DESEMBOLSOS-{anio}-{mes:02d}", fecha=fecha, clave="cartera",
                     concepto=f"Desembolsos de préstamos de {_mes(mes)} {anio}",
                     lineas=[*(self.linea(c, debe=m) for c, m in p["desembolsos"]), self.linea(BANCO, haber=desembolsos)])
        recuperado = sum((m for _, m in p["recuperaciones"]), CERO)
        self.asiento(referencia=f"RECUPERACIONES-{anio}-{mes:02d}", fecha=fecha, clave="cartera",
                     concepto=f"Recuperación de capital de préstamos de {_mes(mes)} {anio}",
                     lineas=[self.linea(BANCO, debe=recuperado), *(self.linea(c, haber=m) for c, m in p["recuperaciones"])])
        lineas = [self.linea(c, haber=m) if m > 0 else self.linea(c, debe=-m) for c, m in p["captacion"]]
        neto = sum((m for _, m in p["captacion"]), CERO)
        lineas.append(self.linea(BANCO, debe=neto) if neto > 0 else self.linea(BANCO, haber=-neto))
        self.asiento(referencia=f"CAPTACION-{anio}-{mes:02d}", fecha=fecha, clave="cartera",
                     concepto=f"Captación neta de depósitos de {_mes(mes)} {anio}", lineas=lineas)

    # --- prorrateo -------------------------------------------------------------

    def prorratear(self, anio, mes, *, hubo_carga):
        """Ejecuta el prorrateo escalonado del mes, después de cargar sus gastos."""
        periodo = PeriodoContable.objects.get(anio=anio, mes=mes)
        if periodo.fecha_fin > self.hasta:
            self.r.avisos.append(f"{periodo.nombre}: el rango no cubre el mes completo; no se ejecutó el prorrateo.")
            return
        activas = ReglaProrrateo.objects.filter(activa=True)
        ejecutadas = EjecucionProrrateo.objects.filter(periodo=periodo, estado=EstadoEjecucion.EJECUTADA, regla__in=activas)
        if ejecutadas.count() == activas.count():
            if hubo_carga:
                self.r.avisos.append(
                    f"{periodo.nombre}: el prorrateo ya estaba ejecutado antes de esta carga y no incluye los gastos nuevos; "
                    "anúlelo y vuelva a ejecutarlo en Centros de costo → Prorrateo."
                )
            return
        for r in prorrateo.ejecutar_pendientes(usuario=self.usuario, periodo=periodo):
            if r["resultado"] == "EJECUTADA":
                self.r.sumar("prorrateos")

    # --- orquestación ------------------------------------------------------------

    def ejecutar(self):
        asientos_antes = Asiento.objects.count()
        with transaction.atomic():
            self.catalogos()
            self.apertura()
        for anio, mes in meses_entre(self.desde, self.hasta):
            self.salida(f"Cargando {_mes(mes)} {anio}…")
            antes_mes = Asiento.objects.count()
            with transaction.atomic():
                self.compras(anio, mes)
                self.ventas(anio, mes)
                self.planilla(anio, mes)
                self.intereses_depositos(anio, mes)
                self.depreciacion(anio, mes)
                self.cartera(anio, mes)
                self.prorratear(anio, mes, hubo_carga=Asiento.objects.count() > antes_mes)
        with transaction.atomic():
            for anio, mes in meses_entre(self.desde - timedelta(days=31), self.hasta):
                self.pago_planilla(anio, mes)
            self.pagos()
        self.r.creados["asientos"] = Asiento.objects.count() - asientos_antes
        return self.r


MESES_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")


def _mes(mes):
    return MESES_ES[mes - 1]
