"""Triggers de Oracle de las cuentas por pagar (T5.1).

- TRG_CXP_REGLAS: un documento no se elimina; uno anulado no se modifica; proveedor, documento, fechas,
  monto total, cuenta y asiento de registro no cambian.
- TRG_PAGO_CXP_REGLAS: un pago no se elimina; uno anulado no se modifica; documento, fecha, monto,
  cuenta de banco y asiento no cambian.

Se ejecutan con el cursor nativo de oracledb porque el cursor de Django recorta el ';' final.
"""
from django.db import migrations

TRIGGERS = ("TRG_CXP_REGLAS", "TRG_PAGO_CXP_REGLAS")


def crear_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    cxp = apps.get_model("tesoreria", "CuentaPorPagar")._meta.db_table.upper()
    pago = apps.get_model("tesoreria", "PagoCuentaPorPagar")._meta.db_table.upper()
    sentencias = [
        f"""CREATE OR REPLACE TRIGGER TRG_CXP_REGLAS
BEFORE UPDATE OR DELETE ON {cxp}
FOR EACH ROW
BEGIN
  IF DELETING THEN
    RAISE_APPLICATION_ERROR(-20050, 'Un documento por pagar no se elimina; anúlelo.');
  END IF;
  IF :OLD.ESTADO = 'ANULADA' THEN
    RAISE_APPLICATION_ERROR(-20051, 'El documento está anulado: no admite cambios.');
  END IF;
  IF :NEW.MONTO_TOTAL <> :OLD.MONTO_TOTAL OR :NEW.PROVEEDOR_ID <> :OLD.PROVEEDOR_ID
     OR :NEW.NUMERO_DOCUMENTO <> :OLD.NUMERO_DOCUMENTO OR :NEW.TIPO_DOCUMENTO <> :OLD.TIPO_DOCUMENTO
     OR :NEW.FECHA_EMISION <> :OLD.FECHA_EMISION OR :NEW.FECHA_VENCIMIENTO <> :OLD.FECHA_VENCIMIENTO
     OR :NEW.CUENTA_PASIVO_ID <> :OLD.CUENTA_PASIVO_ID OR :NEW.ASIENTO_ID <> :OLD.ASIENTO_ID THEN
    RAISE_APPLICATION_ERROR(-20052, 'Los datos de un documento registrado no se modifican; anúlelo y regístrelo de nuevo.');
  END IF;
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_PAGO_CXP_REGLAS
BEFORE UPDATE OR DELETE ON {pago}
FOR EACH ROW
BEGIN
  IF DELETING THEN
    RAISE_APPLICATION_ERROR(-20053, 'Un pago no se elimina; anúlelo.');
  END IF;
  IF :OLD.ESTADO = 'ANULADO' THEN
    RAISE_APPLICATION_ERROR(-20054, 'El pago está anulado: no admite cambios.');
  END IF;
  IF :NEW.MONTO <> :OLD.MONTO OR :NEW.FECHA <> :OLD.FECHA OR :NEW.CUENTA_POR_PAGAR_ID <> :OLD.CUENTA_POR_PAGAR_ID
     OR :NEW.CUENTA_BANCO_ID <> :OLD.CUENTA_BANCO_ID OR :NEW.ASIENTO_ID <> :OLD.ASIENTO_ID THEN
    RAISE_APPLICATION_ERROR(-20055, 'Los datos de un pago registrado no se modifican; anúlelo.');
  END IF;
END;""",
    ]
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for sql in sentencias:
            cursor.execute(sql)


def borrar_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for nombre in TRIGGERS:
            cursor.execute(f"DROP TRIGGER {nombre}")


class Migration(migrations.Migration):
    dependencies = [("tesoreria", "0002_cuentas_por_pagar")]

    operations = [migrations.RunPython(crear_triggers, borrar_triggers)]
