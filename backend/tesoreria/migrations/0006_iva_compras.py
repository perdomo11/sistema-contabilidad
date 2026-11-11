"""T7.2: desglose fiscal de las cuentas por pagar (IVA en compras).

- Campos compras_gravadas, compras_exentas, iva_credito_fiscal e iva_retenido.
- Los documentos anteriores no tenían desglose: facturas y CCF quedan como compras gravadas por su total
  (sin crédito fiscal, porque su asiento no lo registró) y recibos u otros como exentas/no sujetas.
  Para actualizarlos se desactiva un momento TRG_CXP_REGLAS (los anulados no admiten cambios).
- Restricciones CHECK: montos no negativos, total = gravadas + exentas + IVA − retención, e IVA y
  retención solo en CCF.
- TRG_CXP_REGLAS pasa a proteger también el desglose fiscal.
"""
from django.db import migrations, models
from django.db.models import F


TRIGGER_ANTERIOR = """CREATE OR REPLACE TRIGGER TRG_CXP_REGLAS
BEFORE UPDATE OR DELETE ON {tabla}
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
END;"""

TRIGGER_NUEVO = """CREATE OR REPLACE TRIGGER TRG_CXP_REGLAS
BEFORE UPDATE OR DELETE ON {tabla}
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
     OR :NEW.CUENTA_PASIVO_ID <> :OLD.CUENTA_PASIVO_ID OR :NEW.ASIENTO_ID <> :OLD.ASIENTO_ID
     OR :NEW.COMPRAS_GRAVADAS <> :OLD.COMPRAS_GRAVADAS OR :NEW.COMPRAS_EXENTAS <> :OLD.COMPRAS_EXENTAS
     OR :NEW.IVA_CREDITO_FISCAL <> :OLD.IVA_CREDITO_FISCAL OR :NEW.IVA_RETENIDO <> :OLD.IVA_RETENIDO THEN
    RAISE_APPLICATION_ERROR(-20052, 'Los datos de un documento registrado no se modifican; anúlelo y regístrelo de nuevo.');
  END IF;
END;"""


def _ejecutar(schema_editor, *sentencias):
    # Cursor nativo de oracledb: el de Django recorta el ';' final del PL/SQL.
    schema_editor.connection.ensure_connection()
    with schema_editor.connection.connection.cursor() as cursor:
        for sql in sentencias:
            cursor.execute(sql)


def desglosar_existentes(apps, schema_editor):
    CuentaPorPagar = apps.get_model("tesoreria", "CuentaPorPagar")
    oracle = schema_editor.connection.vendor == "oracle"
    if oracle:
        _ejecutar(schema_editor, "ALTER TRIGGER TRG_CXP_REGLAS DISABLE")
    try:
        CuentaPorPagar.objects.filter(tipo_documento__in=["FACTURA", "CCF"]).update(compras_gravadas=F("monto_total"))
        CuentaPorPagar.objects.exclude(tipo_documento__in=["FACTURA", "CCF"]).update(compras_exentas=F("monto_total"))
    finally:
        if oracle:
            _ejecutar(schema_editor, "ALTER TRIGGER TRG_CXP_REGLAS ENABLE")


def _trigger(plantilla):
    def aplicar(apps, schema_editor):
        if schema_editor.connection.vendor != "oracle":
            return
        tabla = apps.get_model("tesoreria", "CuentaPorPagar")._meta.db_table.upper()
        _ejecutar(schema_editor, plantilla.format(tabla=tabla))

    return aplicar


class Migration(migrations.Migration):
    dependencies = [("tesoreria", "0005_flujo_efectivo")]

    operations = [
        migrations.AddField(
            model_name="cuentaporpagar",
            name="compras_exentas",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name="cuentaporpagar",
            name="compras_gravadas",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18),
        ),
        migrations.AddField(
            model_name="cuentaporpagar",
            name="iva_credito_fiscal",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="IVA crédito fiscal"),
        ),
        migrations.AddField(
            model_name="cuentaporpagar",
            name="iva_retenido",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=18, verbose_name="retención de IVA 1 %"),
        ),
        migrations.RunPython(desglosar_existentes, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="cuentaporpagar",
            constraint=models.CheckConstraint(
                condition=models.Q(compras_exentas__gte=0, compras_gravadas__gte=0, iva_credito_fiscal__gte=0, iva_retenido__gte=0),
                name="cxp_desglose_no_negativo",
            ),
        ),
        migrations.AddConstraint(
            model_name="cuentaporpagar",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    monto_total=F("compras_gravadas") + F("compras_exentas") + F("iva_credito_fiscal") - F("iva_retenido")
                ),
                name="cxp_desglose_cuadra",
            ),
        ),
        migrations.AddConstraint(
            model_name="cuentaporpagar",
            constraint=models.CheckConstraint(
                condition=models.Q(tipo_documento="CCF") | models.Q(iva_credito_fiscal=0, iva_retenido=0),
                name="cxp_iva_solo_ccf",
            ),
        ),
        migrations.RunPython(_trigger(TRIGGER_NUEVO), _trigger(TRIGGER_ANTERIOR)),
    ]
