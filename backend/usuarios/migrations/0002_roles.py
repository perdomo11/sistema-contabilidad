"""Crea los roles del sistema como grupos de Django."""
from django.db import migrations

ROLES = ("Contador", "Tesorero", "Jefe de área", "Auditor")


def crear_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for nombre in ROLES:
        Group.objects.get_or_create(name=nombre)


def borrar_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("usuarios", "0001_initial"),
    ]

    operations = [migrations.RunPython(crear_roles, borrar_roles)]
