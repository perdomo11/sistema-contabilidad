from datetime import date

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from centros_costo import services
from centros_costo.models import CentroCosto

T, C = CentroCosto.Tipo, CentroCosto.Clase

# Estructura de EJEMPLO de un banco: (código, nombre, tipo, clase). Las de agrupación
# se deducen (tienen subunidades en la lista).
ESTRUCTURA = [
    ("01", "Casa matriz", T.UTILIDAD, C.SUCURSAL),
    ("01-01", "Gerencia general", T.COSTO, C.DEPARTAMENTO),
    ("01-02", "Contabilidad y finanzas", T.COSTO, C.DEPARTAMENTO),
    ("01-03", "Tecnología de información", T.COSTO, C.DEPARTAMENTO),
    ("01-04", "Recursos humanos", T.COSTO, C.DEPARTAMENTO),
    ("01-05", "Créditos", T.UTILIDAD, C.DEPARTAMENTO),
    ("01-06", "Tesorería e inversiones", T.INVERSION, C.DEPARTAMENTO),
    ("02", "Agencia San Salvador Centro", T.UTILIDAD, C.SUCURSAL),
    ("02-01", "Caja y servicio al cliente", T.COSTO, C.AREA),
    ("02-02", "Negocios", T.INGRESO, C.AREA),
    ("03", "Agencia Santa Ana", T.UTILIDAD, C.SUCURSAL),
    ("03-01", "Caja y servicio al cliente", T.COSTO, C.AREA),
    ("03-02", "Negocios", T.INGRESO, C.AREA),
    ("04", "Agencia San Miguel", T.UTILIDAD, C.SUCURSAL),
    ("04-01", "Caja y servicio al cliente", T.COSTO, C.AREA),
    ("04-02", "Negocios", T.INGRESO, C.AREA),
    ("90", "Proyectos", T.COSTO, C.PROYECTO),
    ("90-01", "Transformación digital", T.COSTO, C.PROYECTO),
]

INICIO = date(2026, 1, 1)


class Command(BaseCommand):
    help = "Carga una estructura de centros de costo de ejemplo. Idempotente."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda registrado como autor.")

    def handle(self, *args, usuario, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist:
            raise CommandError(f"No existe el usuario '{usuario}'.")
        responsable = User.objects.filter(username="jefe", is_active=True).first()
        codigos = [c for c, *_ in ESTRUCTURA]
        creados = existentes = 0
        for codigo, nombre, tipo, clase in ESTRUCTURA:
            if CentroCosto.objects.filter(codigo=codigo).exists():
                existentes += 1
                continue
            padre_codigo = codigo.rsplit("-", 1)[0] if "-" in codigo else None
            try:
                services.crear_centro(
                    usuario=autor,
                    codigo=codigo,
                    nombre=nombre,
                    tipo=tipo,
                    clase=clase,
                    padre=CentroCosto.objects.get(codigo=padre_codigo) if padre_codigo else None,
                    responsable=responsable if codigo == "01-02" else None,
                    acepta_movimientos=not any(c.startswith(codigo + "-") for c in codigos),
                    vigente_desde=INICIO,
                )
                creados += 1
            except ValidationError as exc:
                self.stderr.write(f"  {codigo} {nombre}: {'; '.join(exc.messages)}")
        self.stdout.write(self.style.SUCCESS(f"Centros creados: {creados}. Ya existían: {existentes}."))
