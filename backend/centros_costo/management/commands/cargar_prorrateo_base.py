from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from centros_costo import prorrateo
from centros_costo.models import BaseProrrateo, CentroCosto, MedidaBase, ReglaProrrateo
from contabilidad.models import Cuenta, PeriodoContable

BASES = [
    ("METROS2", "Metros cuadrados", "m²"),
    ("PERSONAL", "Personal ocupado", "personas"),
    ("TRANSACCIONES", "Volumen de transacciones", "transacciones"),
]

# Medidas de EJEMPLO por centro de detalle: (m², personal, transacciones mensuales).
MEDIDAS = {
    "01-01": (180, 6, 0),
    "01-02": (120, 8, 0),
    "01-03": (150, 10, 0),
    "01-04": (60, 4, 0),
    "01-05": (140, 12, 2500),
    "01-06": (80, 5, 0),
    "02-01": (220, 14, 18000),
    "02-02": (90, 6, 3200),
    "03-01": (160, 9, 11000),
    "03-02": (70, 4, 2100),
    "04-01": (150, 8, 9500),
    "04-02": (60, 3, 1800),
    "90-01": (40, 5, 0),
}

AGENCIAS = ["02-01", "02-02", "03-01", "03-02", "04-01", "04-02"]

# (orden, nombre, origen, cuentas, base, destinos)
REGLAS = [
    (1, "Gastos generales de Gerencia general por m²", "01-01", ["5202"], "METROS2",
     ["01-02", "01-03", "01-04", "01-05", "01-06"] + AGENCIAS),
    (2, "Gastos de Tecnología por volumen de transacciones", "01-03", ["5202"], "TRANSACCIONES",
     ["01-05"] + AGENCIAS),
    (3, "Gastos de personal de Recursos humanos por personal ocupado", "01-04", ["5201"], "PERSONAL",
     ["01-02", "01-05", "01-06"] + AGENCIAS),
]


def _valor(codigo_base, centro, mes):
    m2, personal, transacciones = MEDIDAS[centro]
    if codigo_base == "METROS2":
        return Decimal(m2)
    if codigo_base == "PERSONAL":
        return Decimal(personal)
    # El volumen de transacciones varía un poco de mes a mes.
    return (Decimal(transacciones) * (1 + Decimal(mes % 3) / 20)).quantize(Decimal("1"))


class Command(BaseCommand):
    help = "Carga bases, medidas y reglas de prorrateo de ejemplo (requiere catálogo, centros y ejercicio). Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda registrado como autor.")
        parser.add_argument("--anio", type=int, default=None, help="Ejercicio para las medidas (por defecto, el actual).")

    @transaction.atomic
    def handle(self, *args, usuario, anio, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{usuario}'.")
        anio = anio or timezone.localdate().year
        periodos = list(PeriodoContable.objects.filter(anio=anio))
        if not periodos:
            raise CommandError(f"No existe el ejercicio {anio}: créelo en Periodos contables.")
        centros = {c.codigo: c for c in CentroCosto.objects.filter(codigo__in=MEDIDAS)}
        if len(centros) != len(MEDIDAS):
            raise CommandError("Faltan centros: ejecute antes cargar_centros_base.")

        bases = {}
        for codigo, nombre, unidad in BASES:
            bases[codigo] = BaseProrrateo.objects.filter(codigo=codigo).first() or prorrateo.crear_base(
                usuario=autor, codigo=codigo, nombre=nombre, unidad=unidad
            )

        existentes = set(
            MedidaBase.objects.filter(periodo__in=periodos).values_list("base_id", "centro_costo_id", "periodo_id")
        )
        nuevas = [
            MedidaBase(base=base, centro_costo=centro, periodo=p, valor=_valor(codigo, cc, p.mes), modificado_por=autor)
            for codigo, base in bases.items()
            for cc, centro in centros.items()
            for p in periodos
            if (base.pk, centro.pk, p.pk) not in existentes
        ]
        MedidaBase.objects.bulk_create(nuevas)
        self.stdout.write(f"Bases: {len(bases)}. Medidas creadas: {len(nuevas)} ({anio}).")

        creadas = 0
        for orden, nombre, origen, cuentas, base, destinos in REGLAS:
            if ReglaProrrateo.objects.filter(nombre=nombre).exists():
                continue
            try:
                lista_cuentas = [Cuenta.objects.get(codigo=c) for c in cuentas]
            except Cuenta.DoesNotExist:
                raise CommandError("Faltan cuentas: ejecute antes cargar_catalogo_base.")
            prorrateo.crear_regla(
                usuario=autor,
                nombre=nombre,
                orden=orden,
                centro_origen=centros[origen],
                base=bases[base],
                cuentas=lista_cuentas,
                destinos=[centros[d] for d in destinos],
            )
            creadas += 1
        self.stdout.write(self.style.SUCCESS(f"Reglas creadas: {creadas}. Ya existían: {len(REGLAS) - creadas}."))
