"""Triggers de Oracle del presupuesto institucional (T4.1):

- TRG_PRESUPUESTO_REGLAS: un presupuesto no se elimina; uno cerrado no se modifica; si cambia el monto o
  la versión, deben coincidir con la última versión registrada (ningún cambio de monto sin versión).
- TRG_VERSION_PPTO_INMUTABLE: el historial de versiones no se modifica ni se elimina.

Se ejecutan con el cursor nativo de oracledb porque el cursor de Django recorta el ';' final que el
bloque PL/SQL necesita.
"""
from django.db import migrations

TRIGGERS = ("TRG_PRESUPUESTO_REGLAS", "TRG_VERSION_PPTO_INMUTABLE")


def crear_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    presupuesto = apps.get_model("presupuesto", "PresupuestoInstitucional")._meta.db_table.upper()
    version = apps.get_model("presupuesto", "VersionPresupuesto")._meta.db_table.upper()
    sentencias = [
        f"""CREATE OR REPLACE TRIGGER TRG_PRESUPUESTO_REGLAS
BEFORE UPDATE OR DELETE ON {presupuesto}
FOR EACH ROW
DECLARE
  v_ultima NUMBER;
  v_monto  NUMBER(18,2);
BEGIN
  IF DELETING THEN
    RAISE_APPLICATION_ERROR(-20030, 'Un presupuesto institucional no se elimina.');
  END IF;
  IF :OLD.ESTADO = 'CERRADO' THEN
    RAISE_APPLICATION_ERROR(-20031, 'El presupuesto está cerrado: no admite cambios.');
  END IF;
  IF :NEW.MONTO <> :OLD.MONTO OR :NEW.VERSION <> :OLD.VERSION THEN
    SELECT NVL(MAX(NUMERO), 0) INTO v_ultima FROM {version} WHERE PRESUPUESTO_ID = :NEW.ID;
    IF v_ultima <> :NEW.VERSION THEN
      RAISE_APPLICATION_ERROR(-20032, 'El presupuesto debe reflejar su última versión registrada.');
    END IF;
    SELECT MONTO INTO v_monto FROM {version} WHERE PRESUPUESTO_ID = :NEW.ID AND NUMERO = v_ultima;
    IF v_monto <> :NEW.MONTO THEN
      RAISE_APPLICATION_ERROR(-20033, 'Todo cambio del monto institucional debe quedar en una versión.');
    END IF;
  END IF;
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_VERSION_PPTO_INMUTABLE
BEFORE UPDATE OR DELETE ON {version}
FOR EACH ROW
BEGIN
  RAISE_APPLICATION_ERROR(-20034, 'El historial de versiones del presupuesto es inmutable.');
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
    dependencies = [("presupuesto", "0001_initial")]

    operations = [migrations.RunPython(crear_triggers, borrar_triggers)]
