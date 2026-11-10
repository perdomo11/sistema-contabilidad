"""Triggers de Oracle que garantizan, a nivel de base de datos, las reglas de los asientos:

- TRG_ASIENTO_REGLAS: al pasar un asiento a CONTABILIZADO verifica partida doble
  (≥ 2 líneas, cargos = abonos > 0, totales coherentes con las líneas) y que el
  periodo esté abierto. Un asiento contabilizado no se modifica ni se elimina.
- TRG_LINEA_ASIENTO_INMUTABLE: las líneas de un asiento contabilizado no se
  insertan, modifican ni eliminan.

Se ejecutan con el cursor nativo de oracledb porque el cursor de Django recorta
el ';' final que el bloque PL/SQL necesita.
"""
from django.db import migrations

TRIGGER_ASIENTO = """CREATE OR REPLACE TRIGGER TRG_ASIENTO_REGLAS
BEFORE INSERT OR UPDATE OR DELETE ON CONTABILIDAD_ASIENTO
FOR EACH ROW
DECLARE
  v_debe    NUMBER(18,2);
  v_haber   NUMBER(18,2);
  v_lineas  NUMBER;
  v_periodo VARCHAR2(10);
BEGIN
  IF DELETING THEN
    IF :OLD.ESTADO = 'CONTABILIZADO' THEN
      RAISE_APPLICATION_ERROR(-20010, 'Un asiento contabilizado no se puede eliminar; registre un asiento de reversión.');
    END IF;
    RETURN;
  END IF;

  IF UPDATING AND :OLD.ESTADO = 'CONTABILIZADO' THEN
    RAISE_APPLICATION_ERROR(-20011, 'Un asiento contabilizado es inmutable; registre un asiento de reversión.');
  END IF;

  IF :NEW.ESTADO = 'CONTABILIZADO' THEN
    SELECT NVL(SUM(DEBE), 0), NVL(SUM(HABER), 0), COUNT(*)
      INTO v_debe, v_haber, v_lineas
      FROM CONTABILIDAD_LINEAASIENTO
     WHERE ASIENTO_ID = :NEW.ID;
    IF v_lineas < 2 OR v_debe <> v_haber OR v_debe = 0 THEN
      RAISE_APPLICATION_ERROR(-20012, 'Partida doble: el total de cargos debe ser igual al total de abonos.');
    END IF;
    IF v_debe <> :NEW.TOTAL_DEBE OR v_haber <> :NEW.TOTAL_HABER THEN
      RAISE_APPLICATION_ERROR(-20013, 'Los totales del asiento no coinciden con sus líneas.');
    END IF;
    SELECT ESTADO INTO v_periodo FROM CONTABILIDAD_PERIODOCONTABLE WHERE ID = :NEW.PERIODO_ID;
    IF v_periodo <> 'ABIERTO' THEN
      RAISE_APPLICATION_ERROR(-20014, 'El periodo contable está cerrado.');
    END IF;
  END IF;
END;"""

TRIGGER_LINEA = """CREATE OR REPLACE TRIGGER TRG_LINEA_ASIENTO_INMUTABLE
BEFORE INSERT OR UPDATE OR DELETE ON CONTABILIDAD_LINEAASIENTO
FOR EACH ROW
DECLARE
  v_estado VARCHAR2(15);

  PROCEDURE verificar(p_asiento NUMBER) IS
  BEGIN
    SELECT ESTADO INTO v_estado FROM CONTABILIDAD_ASIENTO WHERE ID = p_asiento;
    IF v_estado = 'CONTABILIZADO' THEN
      RAISE_APPLICATION_ERROR(-20015, 'Las líneas de un asiento contabilizado no se modifican.');
    END IF;
  END;
BEGIN
  IF INSERTING OR UPDATING THEN
    verificar(:NEW.ASIENTO_ID);
  END IF;
  IF DELETING OR UPDATING THEN
    verificar(:OLD.ASIENTO_ID);
  END IF;
END;"""

TRIGGERS = {"TRG_ASIENTO_REGLAS": TRIGGER_ASIENTO, "TRG_LINEA_ASIENTO_INMUTABLE": TRIGGER_LINEA}


def _ejecutar(schema_editor, sentencias):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for sql in sentencias:
            cursor.execute(sql)


def crear(apps, schema_editor):
    _ejecutar(schema_editor, TRIGGERS.values())


def borrar(apps, schema_editor):
    _ejecutar(schema_editor, [f"DROP TRIGGER {nombre}" for nombre in TRIGGERS])


class Migration(migrations.Migration):
    dependencies = [("contabilidad", "0003_asientos")]

    operations = [migrations.RunPython(crear, borrar)]
