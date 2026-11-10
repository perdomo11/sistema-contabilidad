from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from contabilidad.models import Cuenta
from tesoreria import flujo
from tesoreria.models import ClasificacionFlujo


class Command(BaseCommand):
    help = "Clasificación de ejemplo para el flujo de efectivo (T5.3): 11 efectivo, actividades por grupo. No pisa lo existente."

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuario que queda como autor de los cambios.")

    def handle(self, *args, usuario, **options):
        try:
            autor = User.objects.get(username=usuario)
        except User.DoesNotExist as exc:
            raise CommandError(f"No existe el usuario {usuario}.") from exc
        creadas = omitidas = 0
        for codigo, actividad in flujo.EJEMPLO.items():
            cuenta = Cuenta.objects.filter(codigo=codigo).first()
            if cuenta is None:
                self.stderr.write(f"No existe la cuenta {codigo}; se omite.")
                continue
            if ClasificacionFlujo.objects.filter(cuenta=cuenta).exists():
                omitidas += 1
                continue
            flujo.asignar_actividad(usuario=autor, cuenta=cuenta, actividad=actividad)
            creadas += 1
        flujo.configuracion()
        self.stdout.write(self.style.SUCCESS(f"Clasificación de flujo: {creadas} asignada(s), {omitidas} ya existente(s)."))
