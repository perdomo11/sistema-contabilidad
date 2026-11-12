"""Equivalente PostgreSQL de TRG_DOC_VENTA_REGLAS (0002, solo Oracle).

Un documento de venta no se elimina; uno anulado no se modifica; cliente, tipo, número, fecha, montos,
cuenta de cobro y asiento de registro no cambian (la única modificación válida es la anulación).
Comparaciones con <> como en Oracle. En otros motores (SQLite) no hace nada.
"""
from django.db import migrations

FUNCION = """CREATE OR REPLACE FUNCTION fn_trg_doc_venta_reglas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un documento de venta no se elimina; anúlelo.';
  END IF;
  IF OLD.estado = 'ANULADO' THEN
    RAISE EXCEPTION 'El documento de venta está anulado: no admite cambios.';
  END IF;
  IF NEW.cliente_id <> OLD.cliente_id OR NEW.tipo_documento <> OLD.tipo_documento
     OR NEW.numero_documento <> OLD.numero_documento OR NEW.fecha_emision <> OLD.fecha_emision
     OR NEW.ventas_gravadas <> OLD.ventas_gravadas OR NEW.ventas_exentas <> OLD.ventas_exentas
     OR NEW.iva_debito_fiscal <> OLD.iva_debito_fiscal OR NEW.total <> OLD.total
     OR NEW.cuenta_cobro_id <> OLD.cuenta_cobro_id OR NEW.asiento_id <> OLD.asiento_id THEN
    RAISE EXCEPTION 'Los datos de un documento de venta emitido no se modifican; anúlelo y emita otro.';
  END IF;
  RETURN NEW;
END;
$$"""


def crear(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tabla = apps.get_model("ventas", "DocumentoVenta")._meta.db_table
    schema_editor.execute(FUNCION, None)
    schema_editor.execute(
        f'CREATE TRIGGER trg_doc_venta_reglas BEFORE UPDATE OR DELETE ON "{tabla}" '
        "FOR EACH ROW EXECUTE FUNCTION fn_trg_doc_venta_reglas()",
        None,
    )


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    tabla = apps.get_model("ventas", "DocumentoVenta")._meta.db_table
    schema_editor.execute(f'DROP TRIGGER IF EXISTS trg_doc_venta_reglas ON "{tabla}"', None)
    schema_editor.execute("DROP FUNCTION IF EXISTS fn_trg_doc_venta_reglas()", None)


class Migration(migrations.Migration):
    dependencies = [("ventas", "0002_triggers_ventas")]

    operations = [migrations.RunPython(crear, borrar)]
