"""Equivalente PostgreSQL de TRG_ASIENTO_REGLAS (versión de 0006) y TRG_LINEA_ASIENTO_INMUTABLE (0004).

- trg_asiento_reglas: un asiento contabilizado no se modifica ni se elimina; al contabilizar exige
  partida doble (≥ 2 líneas, cargos = abonos > 0, totales coherentes), periodo abierto y, salvo
  reversiones, centro de costo en cuentas no exentas y centros de detalle vigentes en la fecha.
- trg_linea_asiento_inmutable: las líneas de un asiento contabilizado no se insertan, modifican ni eliminan.

Mismos mensajes que los triggers de Oracle. En otros motores (SQLite) no hace nada.
"""
from django.db import migrations


def _tablas(apps):
    tabla = lambda app, modelo: apps.get_model(app, modelo)._meta.db_table  # noqa: E731
    return {
        "asiento": tabla("contabilidad", "Asiento"),
        "linea": tabla("contabilidad", "LineaAsiento"),
        "periodo": tabla("contabilidad", "PeriodoContable"),
        "cuenta": tabla("contabilidad", "Cuenta"),
        "centro": tabla("centros_costo", "CentroCosto"),
    }


def _sentencias(t):
    return [
        f"""CREATE OR REPLACE FUNCTION fn_trg_asiento_reglas() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  v_debe       NUMERIC(18,2);
  v_haber      NUMERIC(18,2);
  v_lineas     INTEGER;
  v_periodo    VARCHAR(10);
  v_sin_centro INTEGER;
  v_centro_mal INTEGER;
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.estado = 'CONTABILIZADO' THEN
      RAISE EXCEPTION 'Un asiento contabilizado no se puede eliminar; registre un asiento de reversión.';
    END IF;
    RETURN OLD;
  END IF;

  IF TG_OP = 'UPDATE' AND OLD.estado = 'CONTABILIZADO' THEN
    RAISE EXCEPTION 'Un asiento contabilizado es inmutable; registre un asiento de reversión.';
  END IF;

  IF NEW.estado = 'CONTABILIZADO' THEN
    SELECT COALESCE(SUM(debe), 0), COALESCE(SUM(haber), 0), COUNT(*)
      INTO v_debe, v_haber, v_lineas
      FROM "{t['linea']}"
     WHERE asiento_id = NEW.id;
    IF v_lineas < 2 OR v_debe <> v_haber OR v_debe = 0 THEN
      RAISE EXCEPTION 'Partida doble: el total de cargos debe ser igual al total de abonos.';
    END IF;
    IF v_debe <> NEW.total_debe OR v_haber <> NEW.total_haber THEN
      RAISE EXCEPTION 'Los totales del asiento no coinciden con sus líneas.';
    END IF;
    SELECT estado INTO v_periodo FROM "{t['periodo']}" WHERE id = NEW.periodo_id;
    IF v_periodo IS DISTINCT FROM 'ABIERTO' THEN
      RAISE EXCEPTION 'El periodo contable está cerrado.';
    END IF;

    IF NEW.tipo <> 'REVERSION' THEN
      SELECT COUNT(*) INTO v_sin_centro
        FROM "{t['linea']}" l
        JOIN "{t['cuenta']}" c ON c.id = l.cuenta_id
       WHERE l.asiento_id = NEW.id
         AND l.centro_costo_id IS NULL
         AND NOT c.exenta_centro_costo;
      IF v_sin_centro > 0 THEN
        RAISE EXCEPTION 'Toda línea de una cuenta no exenta debe llevar centro de costo.';
      END IF;

      SELECT COUNT(*) INTO v_centro_mal
        FROM "{t['linea']}" l
        JOIN "{t['centro']}" cc ON cc.id = l.centro_costo_id
       WHERE l.asiento_id = NEW.id
         AND (NOT cc.acepta_movimientos
              OR cc.vigente_desde > NEW.fecha
              OR (cc.vigente_hasta IS NOT NULL AND cc.vigente_hasta < NEW.fecha));
      IF v_centro_mal > 0 THEN
        RAISE EXCEPTION 'Hay líneas con centros de costo de agrupación o no vigentes en la fecha del asiento.';
      END IF;
    END IF;
  END IF;
  RETURN NEW;
END;
$$""",
        f"""CREATE TRIGGER trg_asiento_reglas
BEFORE INSERT OR UPDATE OR DELETE ON "{t['asiento']}"
FOR EACH ROW EXECUTE FUNCTION fn_trg_asiento_reglas()""",
        f"""CREATE OR REPLACE FUNCTION fn_trg_linea_asiento_inmutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP IN ('INSERT', 'UPDATE') AND EXISTS (
       SELECT 1 FROM "{t['asiento']}" WHERE id = NEW.asiento_id AND estado = 'CONTABILIZADO') THEN
    RAISE EXCEPTION 'Las líneas de un asiento contabilizado no se modifican.';
  END IF;
  IF TG_OP IN ('DELETE', 'UPDATE') AND EXISTS (
       SELECT 1 FROM "{t['asiento']}" WHERE id = OLD.asiento_id AND estado = 'CONTABILIZADO') THEN
    RAISE EXCEPTION 'Las líneas de un asiento contabilizado no se modifican.';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$""",
        f"""CREATE TRIGGER trg_linea_asiento_inmutable
BEFORE INSERT OR UPDATE OR DELETE ON "{t['linea']}"
FOR EACH ROW EXECUTE FUNCTION fn_trg_linea_asiento_inmutable()""",
    ]


def crear(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for sql in _sentencias(_tablas(apps)):
        schema_editor.execute(sql, None)


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    t = _tablas(apps)
    for trigger, tabla in (("trg_asiento_reglas", t["asiento"]), ("trg_linea_asiento_inmutable", t["linea"])):
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {trigger} ON "{tabla}"', None)
        schema_editor.execute(f"DROP FUNCTION IF EXISTS fn_{trigger}()", None)


class Migration(migrations.Migration):
    dependencies = [
        ("contabilidad", "0009_clasificacion_resultados"),
        ("centros_costo", "0003_prorrateo"),
    ]

    operations = [migrations.RunPython(crear, borrar)]
