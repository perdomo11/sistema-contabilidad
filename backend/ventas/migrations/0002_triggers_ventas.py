"""Trigger de Oracle de los documentos de venta (T7.3).

TRG_DOC_VENTA_REGLAS: un documento no se elimina; uno anulado no se modifica; cliente, tipo, número, fecha,
montos, cuenta de cobro y asiento de registro no cambian (la única modificación válida es la anulación).

Se ejecuta con el cursor nativo de oracledb porque el cursor de Django recorta el ';' final.
"""
from django.db import migrations

TRIGGER = """CREATE OR REPLACE TRIGGER TRG_DOC_VENTA_REGLAS
BEFORE UPDATE OR DELETE ON {tabla}
FOR EACH ROW
BEGIN
  IF DELETING THEN
    RAISE_APPLICATION_ERROR(-20060, 'Un documento de venta no se elimina; anúlelo.');
  END IF;
  IF :OLD.ESTADO = 'ANULADO' THEN
    RAISE_APPLICATION_ERROR(-20061, 'El documento de venta está anulado: no admite cambios.');
  END IF;
  IF :NEW.CLIENTE_ID <> :OLD.CLIENTE_ID OR :NEW.TIPO_DOCUMENTO <> :OLD.TIPO_DOCUMENTO
     OR :NEW.NUMERO_DOCUMENTO <> :OLD.NUMERO_DOCUMENTO OR :NEW.FECHA_EMISION <> :OLD.FECHA_EMISION
     OR :NEW.VENTAS_GRAVADAS <> :OLD.VENTAS_GRAVADAS OR :NEW.VENTAS_EXENTAS <> :OLD.VENTAS_EXENTAS
     OR :NEW.IVA_DEBITO_FISCAL <> :OLD.IVA_DEBITO_FISCAL OR :NEW.TOTAL <> :OLD.TOTAL
     OR :NEW.CUENTA_COBRO_ID <> :OLD.CUENTA_COBRO_ID OR :NEW.ASIENTO_ID <> :OLD.ASIENTO_ID THEN
    RAISE_APPLICATION_ERROR(-20062, 'Los datos de un documento de venta emitido no se modifican; anúlelo y emita otro.');
  END IF;
END;"""


def crear_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    tabla = apps.get_model("ventas", "DocumentoVenta")._meta.db_table.upper()
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        cursor.execute(TRIGGER.format(tabla=tabla))


def borrar_trigger(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        cursor.execute("DROP TRIGGER TRG_DOC_VENTA_REGLAS")


class Migration(migrations.Migration):
    dependencies = [("ventas", "0001_initial")]

    operations = [migrations.RunPython(crear_trigger, borrar_trigger)]
