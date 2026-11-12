"""Equivalente PostgreSQL de los triggers del presupuesto (0002 y 0004, solo Oracle).

Por fila:
- trg_presupuesto_reglas: no se elimina; cerrado no se modifica; monto/versión = última versión registrada.
- trg_version_ppto_inmutable y trg_cambio_dist_inmutable: historiales inmutables.
- trg_asig_ppto_reglas / trg_det_ppto_reglas: un presupuesto cerrado no admite cambios en su distribución.
De sentencia (topes):
- trg_asig_ppto_tope: Σ asignaciones ≤ institucional y Σ detalle ≤ asignación.
- trg_det_ppto_tope: Σ detalle de cada asignación ≤ su monto.
- trg_ppto_tope_distribuido: el monto institucional no queda por debajo de lo distribuido.

Mismos mensajes que en Oracle. En otros motores (SQLite) no hace nada.
"""
from django.db import migrations

# (trigger, clave de tabla)
TRIGGERS = (
    ("trg_presupuesto_reglas", "ppto"),
    ("trg_version_ppto_inmutable", "version"),
    ("trg_asig_ppto_tope", "asig"),
    ("trg_det_ppto_tope", "det"),
    ("trg_ppto_tope_distribuido", "ppto"),
    ("trg_asig_ppto_reglas", "asig"),
    ("trg_det_ppto_reglas", "det"),
    ("trg_cambio_dist_inmutable", "cambio"),
)


def _tablas(apps):
    tabla = lambda modelo: apps.get_model("presupuesto", modelo)._meta.db_table  # noqa: E731
    return {
        "ppto": tabla("PresupuestoInstitucional"),
        "version": tabla("VersionPresupuesto"),
        "asig": tabla("AsignacionPresupuesto"),
        "det": tabla("DetallePresupuesto"),
        "cambio": tabla("CambioDistribucion"),
    }


def _funcion(nombre, cuerpo, declarar=""):
    return f"""CREATE OR REPLACE FUNCTION fn_{nombre}() RETURNS trigger
LANGUAGE plpgsql AS $$
{declarar}
BEGIN
{cuerpo}
END;
$$"""


def _sentencias(t):
    exceso_institucional = f"""  IF EXISTS (SELECT 1 FROM "{t['ppto']}" p
              WHERE p.monto < (SELECT COALESCE(SUM(a.monto), 0) FROM "{t['asig']}" a WHERE a.presupuesto_id = p.id)) THEN
    RAISE EXCEPTION 'La distribución a departamentos excede el monto institucional.';
  END IF;"""
    exceso_departamento = f"""  IF EXISTS (SELECT 1 FROM "{t['asig']}" a
              WHERE a.monto < (SELECT COALESCE(SUM(d.monto), 0) FROM "{t['det']}" d WHERE d.asignacion_id = a.id)) THEN
    RAISE EXCEPTION 'El detalle por cuenta y mes excede lo asignado al departamento.';
  END IF;"""
    cerrado = "RAISE EXCEPTION 'El presupuesto está cerrado: su distribución no admite cambios.';"

    def fila(nombre, momento, tabla):
        return f"""CREATE TRIGGER {nombre}
{momento} ON "{t[tabla]}"
FOR EACH ROW EXECUTE FUNCTION fn_{nombre}()"""

    def sentencia(nombre, momento, tabla):
        return f"""CREATE TRIGGER {nombre}
{momento} ON "{t[tabla]}"
FOR EACH STATEMENT EXECUTE FUNCTION fn_{nombre}()"""

    def inmutable(mensaje):
        return f"  RAISE EXCEPTION '{mensaje}';"

    return [
        _funcion(
            "trg_presupuesto_reglas",
            f"""  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un presupuesto institucional no se elimina.';
  END IF;
  IF OLD.estado = 'CERRADO' THEN
    RAISE EXCEPTION 'El presupuesto está cerrado: no admite cambios.';
  END IF;
  IF NEW.monto <> OLD.monto OR NEW.version <> OLD.version THEN
    SELECT COALESCE(MAX(numero), 0) INTO v_ultima FROM "{t['version']}" WHERE presupuesto_id = NEW.id;
    IF v_ultima <> NEW.version THEN
      RAISE EXCEPTION 'El presupuesto debe reflejar su última versión registrada.';
    END IF;
    SELECT monto INTO v_monto FROM "{t['version']}" WHERE presupuesto_id = NEW.id AND numero = v_ultima;
    IF v_monto IS DISTINCT FROM NEW.monto THEN
      RAISE EXCEPTION 'Todo cambio del monto institucional debe quedar en una versión.';
    END IF;
  END IF;
  RETURN NEW;""",
            "DECLARE\n  v_ultima INTEGER;\n  v_monto  NUMERIC(18,2);",
        ),
        fila("trg_presupuesto_reglas", "BEFORE UPDATE OR DELETE", "ppto"),
        _funcion("trg_version_ppto_inmutable", inmutable("El historial de versiones del presupuesto es inmutable.")),
        fila("trg_version_ppto_inmutable", "BEFORE UPDATE OR DELETE", "version"),
        _funcion("trg_asig_ppto_tope", f"{exceso_institucional}\n{exceso_departamento}\n  RETURN NULL;"),
        sentencia("trg_asig_ppto_tope", "AFTER INSERT OR UPDATE", "asig"),
        _funcion("trg_det_ppto_tope", f"{exceso_departamento}\n  RETURN NULL;"),
        sentencia("trg_det_ppto_tope", "AFTER INSERT OR UPDATE", "det"),
        _funcion("trg_ppto_tope_distribuido", f"{exceso_institucional}\n  RETURN NULL;"),
        sentencia("trg_ppto_tope_distribuido", "AFTER UPDATE OF monto", "ppto"),
        _funcion(
            "trg_asig_ppto_reglas",
            f"""  IF TG_OP = 'DELETE' THEN
    v_ppto := OLD.presupuesto_id;
  ELSE
    v_ppto := NEW.presupuesto_id;
  END IF;
  SELECT estado INTO v_estado FROM "{t['ppto']}" WHERE id = v_ppto;
  IF v_estado = 'CERRADO' THEN
    {cerrado}
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;""",
            "DECLARE\n  v_ppto   BIGINT;\n  v_estado VARCHAR(10);",
        ),
        fila("trg_asig_ppto_reglas", "BEFORE INSERT OR UPDATE OR DELETE", "asig"),
        _funcion(
            "trg_det_ppto_reglas",
            f"""  IF TG_OP = 'DELETE' THEN
    v_asig := OLD.asignacion_id;
  ELSE
    v_asig := NEW.asignacion_id;
  END IF;
  SELECT p.estado INTO v_estado FROM "{t['ppto']}" p JOIN "{t['asig']}" a ON a.presupuesto_id = p.id
   WHERE a.id = v_asig;
  IF v_estado = 'CERRADO' THEN
    {cerrado}
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;""",
            "DECLARE\n  v_asig   BIGINT;\n  v_estado VARCHAR(10);",
        ),
        fila("trg_det_ppto_reglas", "BEFORE INSERT OR UPDATE OR DELETE", "det"),
        _funcion("trg_cambio_dist_inmutable", inmutable("El historial de la distribución del presupuesto es inmutable.")),
        fila("trg_cambio_dist_inmutable", "BEFORE UPDATE OR DELETE", "cambio"),
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
    for nombre, tabla in TRIGGERS:
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {nombre} ON "{t[tabla]}"', None)
        schema_editor.execute(f"DROP FUNCTION IF EXISTS fn_{nombre}()", None)


class Migration(migrations.Migration):
    dependencies = [("presupuesto", "0004_triggers_distribucion")]

    operations = [migrations.RunPython(crear, borrar)]
