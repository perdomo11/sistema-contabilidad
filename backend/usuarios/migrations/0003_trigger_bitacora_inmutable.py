"""Trigger de Oracle que impide UPDATE y DELETE sobre la bitácora de auditoría.

Se ejecuta con el cursor nativo de oracledb porque el cursor de Django recorta
el ';' final, que el bloque PL/SQL necesita.
"""
from django.db import migrations

TRIGGER = "TRG_BITACORA_INMUTABLE"


def crear_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    tabla = apps.get_model("usuarios", "Bitacora")._meta.db_table.upper()
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        cursor.execute(
            f"""CREATE OR REPLACE TRIGGER {TRIGGER}
BEFORE UPDATE OR DELETE ON {tabla}
FOR EACH ROW
BEGIN
  RAISE_APPLICATION_ERROR(-20001, 'La bitácora de auditoría es inmutable.');
END;"""
        )


def borrar_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        cursor.execute(f"DROP TRIGGER {TRIGGER}")


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0002_roles")]

    operations = [migrations.RunPython(crear_trigger, borrar_trigger)]
