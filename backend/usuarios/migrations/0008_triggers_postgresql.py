"""Equivalente PostgreSQL de TRG_BITACORA_INMUTABLE (0003, solo Oracle).

La bitácora de auditoría no admite UPDATE ni DELETE, ni siquiera por SQL directo.
En otros motores (SQLite) no hace nada.
"""
from django.db import migrations


def crear(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tabla = apps.get_model("usuarios", "Bitacora")._meta.db_table
    schema_editor.execute(
        """CREATE OR REPLACE FUNCTION fn_trg_bitacora_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'La bitácora de auditoría es inmutable.';
END;
$$""",
        None,
    )
    schema_editor.execute(
        f"""CREATE TRIGGER trg_bitacora_inmutable
BEFORE UPDATE OR DELETE ON "{tabla}"
FOR EACH ROW EXECUTE FUNCTION fn_trg_bitacora_inmutable()""",
        None,
    )


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tabla = apps.get_model("usuarios", "Bitacora")._meta.db_table
    schema_editor.execute(f'DROP TRIGGER IF EXISTS trg_bitacora_inmutable ON "{tabla}"', None)
    schema_editor.execute("DROP FUNCTION IF EXISTS fn_trg_bitacora_inmutable()", None)


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0007_alter_bitacora_accion")]

    operations = [migrations.RunPython(crear, borrar)]
