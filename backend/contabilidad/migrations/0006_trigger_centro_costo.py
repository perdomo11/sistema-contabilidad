"""Amplía TRG_ASIENTO_REGLAS con la regla 3 (centro de costo) a nivel de base de datos.

Al contabilizar un asiento (salvo reversiones, que reflejan un hecho ya válido):
- toda línea de cuenta NO exenta debe tener centro de costo;
- todo centro usado debe ser de detalle y estar vigente en la fecha del asiento.
"""
import importlib

from django.db import migrations

TRIGGER_ASIENTO = """CREATE OR REPLACE TRIGGER TRG_ASIENTO_REGLAS
BEFORE INSERT OR UPDATE OR DELETE ON CONTABILIDAD_ASIENTO
FOR EACH ROW
DECLARE
  v_debe       NUMBER(18,2);
  v_haber      NUMBER(18,2);
  v_lineas     NUMBER;
  v_periodo    VARCHAR2(10);
  v_sin_centro NUMBER;
  v_centro_mal NUMBER;
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

    IF :NEW.TIPO <> 'REVERSION' THEN
      SELECT COUNT(*) INTO v_sin_centro
        FROM CONTABILIDAD_LINEAASIENTO l
        JOIN CONTABILIDAD_CUENTA c ON c.ID = l.CUENTA_ID
       WHERE l.ASIENTO_ID = :NEW.ID
         AND l.CENTRO_COSTO_ID IS NULL
         AND c.EXENTA_CENTRO_COSTO = 0;
      IF v_sin_centro > 0 THEN
        RAISE_APPLICATION_ERROR(-20016, 'Toda línea de una cuenta no exenta debe llevar centro de costo.');
      END IF;

      SELECT COUNT(*) INTO v_centro_mal
        FROM CONTABILIDAD_LINEAASIENTO l
        JOIN CENTROS_COSTO_CENTROCOSTO cc ON cc.ID = l.CENTRO_COSTO_ID
       WHERE l.ASIENTO_ID = :NEW.ID
         AND (cc.ACEPTA_MOVIMIENTOS = 0
              OR cc.VIGENTE_DESDE > :NEW.FECHA
              OR (cc.VIGENTE_HASTA IS NOT NULL AND cc.VIGENTE_HASTA < :NEW.FECHA));
      IF v_centro_mal > 0 THEN
        RAISE_APPLICATION_ERROR(-20017, 'Hay líneas con centros de costo de agrupación o no vigentes en la fecha del asiento.');
      END IF;
    END IF;
  END IF;
END;"""


def _ejecutar(schema_editor, sql):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        cursor.execute(sql)


def crear(apps, schema_editor):
    _ejecutar(schema_editor, TRIGGER_ASIENTO)


def restaurar(apps, schema_editor):
    anterior = importlib.import_module("contabilidad.migrations.0004_triggers_asientos")
    _ejecutar(schema_editor, anterior.TRIGGER_ASIENTO)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidad", "0005_linea_centro_costo"),
        ("centros_costo", "0001_initial"),
    ]

    operations = [migrations.RunPython(crear, restaurar)]
