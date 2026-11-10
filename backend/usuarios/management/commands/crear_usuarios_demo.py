from django.conf import settings
from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError

from usuarios import roles

CONTRASENA_DEMO = "Demo_2026!"

USUARIOS_DEMO = [
    ("contador", "Carla", "Contadora", roles.CONTADOR),
    ("tesorero", "Tomás", "Tesorero", roles.TESORERO),
    ("jefe", "Julia", "Jefa de Área", roles.JEFE_AREA),
    ("auditor", "Andrés", "Auditor", roles.AUDITOR),
]


class Command(BaseCommand):
    help = "Crea (o restablece) un usuario de prueba por cada rol. Solo con DEBUG=True."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Este comando solo se permite con DEBUG=True.")
        for username, nombre, apellido, rol in USUARIOS_DEMO:
            usuario, creado = User.objects.get_or_create(username=username)
            usuario.first_name = nombre
            usuario.last_name = apellido
            usuario.is_active = True
            usuario.set_password(CONTRASENA_DEMO)
            usuario.save()
            usuario.groups.set([Group.objects.get(name=rol)])
            estado = "creado" if creado else "restablecido"
            self.stdout.write(f"  {username:<10} rol {rol:<13} {estado}")
        self.stdout.write(self.style.SUCCESS(f"Contraseña de todos los usuarios demo: {CONTRASENA_DEMO}"))
