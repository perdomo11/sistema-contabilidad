"""Triggers de Oracle de la distribución del presupuesto (T4.2).

Topes (triggers de sentencia, que sí pueden leer su propia tabla):
- TRG_ASIG_PPTO_TOPE: Σ asignaciones ≤ monto institucional y Σ detalle ≤ asignación.
- TRG_DET_PPTO_TOPE: Σ detalle de cada asignación ≤ su monto.
- TRG_PPTO_TOPE_DISTRIBUIDO: el monto institucional no queda por debajo de lo distribuido.
Reglas por fila:
- TRG_ASIG_PPTO_REGLAS / TRG_DET_PPTO_REGLAS: un presupuesto cerrado no admite cambios en su distribución.
- TRG_CAMBIO_DIST_INMUTABLE: el historial de la distribución no se modifica ni se elimina.

Se ejecutan con el cursor nativo de oracledb porque el cursor de Django recorta el ';' final.
"""
from django.db import migrations

TRIGGERS = (
    "TRG_ASIG_PPTO_TOPE", "TRG_DET_PPTO_TOPE", "TRG_PPTO_TOPE_DISTRIBUIDO",
    "TRG_ASIG_PPTO_REGLAS", "TRG_DET_PPTO_REGLAS", "TRG_CAMBIO_DIST_INMUTABLE",
)


def _tablas(apps):
    tabla = lambda modelo: apps.get_model("presupuesto", modelo)._meta.db_table.upper()  # noqa: E731
    return {
        "ppto": tabla("PresupuestoInstitucional"),
        "asig": tabla("AsignacionPresupuesto"),
        "det": tabla("DetallePresupuesto"),
        "cambio": tabla("CambioDistribucion"),
    }


def _sentencias(t):
    exceso_institucional = f"""SELECT COUNT(*) INTO v_n FROM {t['ppto']} p
     WHERE p.MONTO < (SELECT NVL(SUM(a.MONTO), 0) FROM {t['asig']} a WHERE a.PRESUPUESTO_ID = p.ID);
    IF v_n > 0 THEN
      RAISE_APPLICATION_ERROR(-20040, 'La distribución a departamentos excede el monto institucional.');
    END IF;"""
    exceso_departamento = f"""SELECT COUNT(*) INTO v_n FROM {t['asig']} a
     WHERE a.MONTO < (SELECT NVL(SUM(d.MONTO), 0) FROM {t['det']} d WHERE d.ASIGNACION_ID = a.ID);
    IF v_n > 0 THEN
      RAISE_APPLICATION_ERROR(-20041, 'El detalle por cuenta y mes excede lo asignado al departamento.');
    END IF;"""
    cerrado = "RAISE_APPLICATION_ERROR(-20042, 'El presupuesto está cerrado: su distribución no admite cambios.');"
    return [
        f"""CREATE OR REPLACE TRIGGER TRG_ASIG_PPTO_TOPE
AFTER INSERT OR UPDATE ON {t['asig']}
DECLARE
  v_n NUMBER;
BEGIN
  {exceso_institucional}
  {exceso_departamento}
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_DET_PPTO_TOPE
AFTER INSERT OR UPDATE ON {t['det']}
DECLARE
  v_n NUMBER;
BEGIN
  {exceso_departamento}
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_PPTO_TOPE_DISTRIBUIDO
AFTER UPDATE OF MONTO ON {t['ppto']}
DECLARE
  v_n NUMBER;
BEGIN
  {exceso_institucional}
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_ASIG_PPTO_REGLAS
BEFORE INSERT OR UPDATE OR DELETE ON {t['asig']}
FOR EACH ROW
DECLARE
  v_estado VARCHAR2(10);
BEGIN
  SELECT ESTADO INTO v_estado FROM {t['ppto']} WHERE ID = NVL(:NEW.PRESUPUESTO_ID, :OLD.PRESUPUESTO_ID);
  IF v_estado = 'CERRADO' THEN
    {cerrado}
  END IF;
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_DET_PPTO_REGLAS
BEFORE INSERT OR UPDATE OR DELETE ON {t['det']}
FOR EACH ROW
DECLARE
  v_estado VARCHAR2(10);
BEGIN
  SELECT p.ESTADO INTO v_estado FROM {t['ppto']} p JOIN {t['asig']} a ON a.PRESUPUESTO_ID = p.ID
   WHERE a.ID = NVL(:NEW.ASIGNACION_ID, :OLD.ASIGNACION_ID);
  IF v_estado = 'CERRADO' THEN
    {cerrado}
  END IF;
END;""",
        f"""CREATE OR REPLACE TRIGGER TRG_CAMBIO_DIST_INMUTABLE
BEFORE UPDATE OR DELETE ON {t['cambio']}
FOR EACH ROW
BEGIN
  RAISE_APPLICATION_ERROR(-20043, 'El historial de la distribución del presupuesto es inmutable.');
END;""",
    ]


def crear_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for sql in _sentencias(_tablas(apps)):
            cursor.execute(sql)


def borrar_triggers(apps, schema_editor):
    if schema_editor.connection.vendor != "oracle":
        return
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for nombre in TRIGGERS:
            cursor.execute(f"DROP TRIGGER {nombre}")


class Migration(migrations.Migration):
    dependencies = [("presupuesto", "0003_distribucion")]

    operations = [migrations.RunPython(crear_triggers, borrar_triggers)]
