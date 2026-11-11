from rest_framework import serializers

from centros_costo.models import CentroCosto
from contabilidad.models import Cuenta

from .models import Cliente, DocumentoVenta


def _asiento(a):
    return a and {"id": a.pk, "codigo": a.codigo, "fecha": a.fecha}


# --- Clientes ----------------------------------------------------------------

class ClienteSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    nit = serializers.SerializerMethodField()
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)

    class Meta:
        model = Cliente
        fields = ["id", "nombre", "tipo", "tipo_display", "nit", "nrc", "activo", "creado_por", "creado_en", "modificado_por", "modificado_en"]
        read_only_fields = fields

    def get_nit(self, obj):
        return obj.nit or ""


class ClienteCrearSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=200)
    tipo = serializers.ChoiceField(choices=Cliente.Tipo.choices)
    nit = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    nrc = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    activo = serializers.BooleanField(default=True)


class ClienteActualizarSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=200, required=False)
    tipo = serializers.ChoiceField(choices=Cliente.Tipo.choices, required=False)
    nit = serializers.CharField(max_length=20, required=False, allow_blank=True)
    nrc = serializers.CharField(max_length=20, required=False, allow_blank=True)
    activo = serializers.BooleanField(required=False)


class FiltroClientesSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    activo = serializers.BooleanField(required=False, allow_null=True, default=None)
    tipo = serializers.ChoiceField(choices=Cliente.Tipo.choices, required=False, allow_blank=True, default="")


# --- Documentos de venta -----------------------------------------------------

class DocumentoVentaSerializer(serializers.ModelSerializer):
    cliente = serializers.SerializerMethodField()
    tipo_documento_display = serializers.CharField(source="get_tipo_documento_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    asiento = serializers.SerializerMethodField()

    class Meta:
        model = DocumentoVenta
        fields = [
            "id", "cliente", "tipo_documento", "tipo_documento_display", "numero_documento", "fecha_emision", "concepto",
            "ventas_gravadas", "ventas_exentas", "iva_debito_fiscal", "total", "estado", "estado_display", "asiento",
        ]
        read_only_fields = fields

    def get_cliente(self, obj):
        c = obj.cliente
        return {"id": c.pk, "nombre": c.nombre, "nit": c.nit or "", "nrc": c.nrc or "", "tipo": c.tipo}

    def get_asiento(self, obj):
        return _asiento(obj.asiento)


class DocumentoVentaDetalleSerializer(DocumentoVentaSerializer):
    cuenta_cobro = serializers.SerializerMethodField()
    lineas = serializers.SerializerMethodField()
    asiento_anulacion = serializers.SerializerMethodField()
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    anulado_por = serializers.CharField(source="anulado_por.username", read_only=True, default=None)

    class Meta(DocumentoVentaSerializer.Meta):
        fields = DocumentoVentaSerializer.Meta.fields + [
            "cuenta_cobro", "lineas", "asiento_anulacion", "motivo_anulacion", "creado_por", "creado_en", "anulado_por", "anulado_en",
        ]
        read_only_fields = fields

    def get_cuenta_cobro(self, obj):
        return {"id": obj.cuenta_cobro_id, "codigo": obj.cuenta_cobro.codigo, "nombre": obj.cuenta_cobro.nombre}

    def get_lineas(self, obj):
        """Líneas de ingreso: los abonos del asiento a cuentas de ingreso."""
        return [
            {
                "cuenta": {"codigo": l.cuenta.codigo, "nombre": l.cuenta.nombre},
                "centro_costo": l.centro_costo and {"codigo": l.centro_costo.codigo, "nombre": l.centro_costo.nombre},
                "descripcion": l.descripcion,
                "monto": f"{l.haber:.2f}",
            }
            for l in obj.asiento.lineas.select_related("cuenta", "centro_costo").order_by("numero_linea")
            if l.haber > 0 and l.cuenta.tipo == Cuenta.Tipo.INGRESO
        ]

    def get_asiento_anulacion(self, obj):
        return _asiento(obj.asiento_anulacion)


class LineaVentaSerializer(serializers.Serializer):
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all())
    centro_costo = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False, allow_null=True, default=None)
    descripcion = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    exenta = serializers.BooleanField(required=False, default=False)


class DocumentoVentaCrearSerializer(serializers.Serializer):
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all())
    tipo_documento = serializers.ChoiceField(choices=DocumentoVenta.TipoDocumento.choices)
    numero_documento = serializers.CharField(max_length=40)
    fecha_emision = serializers.DateField()
    concepto = serializers.CharField(max_length=300)
    cuenta_cobro = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False, allow_null=True, default=None)
    lineas = LineaVentaSerializer(many=True)


class AnularSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False, allow_null=True, default=None)


class FiltroDocumentosSerializer(serializers.Serializer):
    desde = serializers.DateField(required=False, allow_null=True, default=None)
    hasta = serializers.DateField(required=False, allow_null=True, default=None)
    tipo_documento = serializers.ChoiceField(choices=DocumentoVenta.TipoDocumento.choices, required=False, allow_blank=True, default="")
    estado = serializers.ChoiceField(choices=DocumentoVenta.Estado.choices, required=False, allow_blank=True, default="")
    cliente = serializers.PrimaryKeyRelatedField(queryset=Cliente.objects.all(), required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True, default="")
