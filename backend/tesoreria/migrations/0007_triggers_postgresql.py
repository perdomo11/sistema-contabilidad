"""Equivalente PostgreSQL de TRG_CXP_REGLAS (versión de 0006) y TRG_PAGO_CXP_REGLAS (0003).

- trg_cxp_reglas: un documento no se elimina; uno anulado no se modifica; proveedor, documento, fechas,
  montos (incluido el desglose fiscal), cuenta y asiento de registro no cambian.
- trg_pago_cxp_reglas: un pago no se elimina; uno anulado no se modifica; documento, fecha, monto,
  cuenta de banco y asiento no cambian.

Las comparaciones usan <> como en Oracle (un cambio desde o hacia NULL no se considera). Mismos mensajes.
En otros motores (SQLite) no hace nada.
"""
from django.db import migrations

CXP = """CREATE OR REPLACE FUNCTION fn_trg_cxp_reglas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un documento por pagar no se elimina; anúlelo.';
  END IF;
  IF OLD.estado = 'ANULADA' THEN
    RAISE EXCEPTION 'El documento está anulado: no admite cambios.';
  END IF;
  IF NEW.monto_total <> OLD.monto_total OR NEW.proveedor_id <> OLD.proveedor_id
     OR NEW.numero_documento <> OLD.numero_documento OR NEW.tipo_documento <> OLD.tipo_documento
     OR NEW.fecha_emision <> OLD.fecha_emision OR NEW.fecha_vencimiento <> OLD.fecha_vencimiento
     OR NEW.cuenta_pasivo_id <> OLD.cuenta_pasivo_id OR NEW.asiento_id <> OLD.asiento_id
     OR NEW.compras_gravadas <> OLD.compras_gravadas OR NEW.compras_exentas <> OLD.compras_exentas
     OR NEW.iva_credito_fiscal <> OLD.iva_credito_fiscal OR NEW.iva_retenido <> OLD.iva_retenido THEN
    RAISE EXCEPTION 'Los datos de un documento registrado no se modifican; anúlelo y regístrelo de nuevo.';
  END IF;
  RETURN NEW;
END;
$$"""

PAGO = """CREATE OR REPLACE FUNCTION fn_trg_pago_cxp_reglas() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'Un pago no se elimina; anúlelo.';
  END IF;
  IF OLD.estado = 'ANULADO' THEN
    RAISE EXCEPTION 'El pago está anulado: no admite cambios.';
  END IF;
  IF NEW.monto <> OLD.monto OR NEW.fecha <> OLD.fecha OR NEW.cuenta_por_pagar_id <> OLD.cuenta_por_pagar_id
     OR NEW.cuenta_banco_id <> OLD.cuenta_banco_id OR NEW.asiento_id <> OLD.asiento_id THEN
    RAISE EXCEPTION 'Los datos de un pago registrado no se modifican; anúlelo.';
  END IF;
  RETURN NEW;
END;
$$"""


def _tablas(apps):
    return {
        "trg_cxp_reglas": apps.get_model("tesoreria", "CuentaPorPagar")._meta.db_table,
        "trg_pago_cxp_reglas": apps.get_model("tesoreria", "PagoCuentaPorPagar")._meta.db_table,
    }


def crear(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    schema_editor.execute(CXP, None)
    schema_editor.execute(PAGO, None)
    for nombre, tabla in _tablas(apps).items():
        schema_editor.execute(
            f'CREATE TRIGGER {nombre} BEFORE UPDATE OR DELETE ON "{tabla}" FOR EACH ROW EXECUTE FUNCTION fn_{nombre}()',
            None,
        )


def borrar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for nombre, tabla in _tablas(apps).items():
        schema_editor.execute(f'DROP TRIGGER IF EXISTS {nombre} ON "{tabla}"', None)
        schema_editor.execute(f"DROP FUNCTION IF EXISTS fn_{nombre}()", None)


class Migration(migrations.Migration):
    dependencies = [("tesoreria", "0006_iva_compras")]

    operations = [migrations.RunPython(crear, borrar)]
