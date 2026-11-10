from rest_framework import serializers

from centros_costo.models import CentroCosto
from contabilidad.models import Cuenta

from .models import CuentaPorPagar, PagoCuentaPorPagar, Proveedor


class ProveedorSerializer(serializers.ModelSerializer):
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)

    class Meta:
        model = Proveedor
        fields = ["id", "nit", "nombre", "nrc", "activo", "creado_por", "creado_en", "modificado_por", "modificado_en"]
        read_only_fields = fields


class ProveedorCrearSerializer(serializers.Serializer):
    nit = serializers.CharField(max_length=20)
    nombre = serializers.CharField(max_length=200)
    nrc = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    activo = serializers.BooleanField(default=True)


class ProveedorActualizarSerializer(serializers.Serializer):
    nit = serializers.CharField(max_length=20, required=False)
    nombre = serializers.CharField(max_length=200, required=False)
    nrc = serializers.CharField(max_length=20, required=False, allow_blank=True)
    activo = serializers.BooleanField(required=False)


class FiltroProveedoresSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    activo = serializers.BooleanField(required=False, allow_null=True, default=None)


# =============================================================================
# T5.1: cuentas por pagar
# =============================================================================

def _asiento(a):
    return a and {"id": a.pk, "codigo": a.codigo, "fecha": a.fecha}


class PagoSerializer(serializers.ModelSerializer):
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    cuenta_banco = serializers.SerializerMethodField()
    asiento = serializers.SerializerMethodField()
    asiento_anulacion = serializers.SerializerMethodField()
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    anulado_por = serializers.CharField(source="anulado_por.username", read_only=True, default=None)

    class Meta:
        model = PagoCuentaPorPagar
        fields = [
            "id", "fecha", "monto", "cuenta_banco", "referencia", "estado", "estado_display", "asiento",
            "asiento_anulacion", "motivo_anulacion", "creado_por", "creado_en", "anulado_por", "anulado_en",
        ]
        read_only_fields = fields

    def get_cuenta_banco(self, obj):
        return {"id": obj.cuenta_banco_id, "codigo": obj.cuenta_banco.codigo, "nombre": obj.cuenta_banco.nombre}

    def get_asiento(self, obj):
        return _asiento(obj.asiento)

    def get_asiento_anulacion(self, obj):
        return _asiento(obj.asiento_anulacion)


class CuentaPorPagarSerializer(serializers.ModelSerializer):
    proveedor = serializers.SerializerMethodField()
    tipo_documento_display = serializers.CharField(source="get_tipo_documento_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    vencimiento = serializers.SerializerMethodField()
    dias = serializers.SerializerMethodField()
    asiento = serializers.SerializerMethodField()

    class Meta:
        model = CuentaPorPagar
        fields = [
            "id", "proveedor", "tipo_documento", "tipo_documento_display", "numero_documento", "fecha_emision",
            "fecha_vencimiento", "concepto", "monto_total", "saldo", "estado", "estado_display", "vencimiento", "dias", "asiento",
        ]
        read_only_fields = fields

    def _situacion(self, obj):
        from .cuentas_por_pagar import situacion_vencimiento

        return situacion_vencimiento(obj, self.context["fecha"])

    def get_proveedor(self, obj):
        return {"id": obj.proveedor_id, "nombre": obj.proveedor.nombre, "nit": obj.proveedor.nit}

    def get_vencimiento(self, obj):
        return self._situacion(obj)[0]

    def get_dias(self, obj):
        return self._situacion(obj)[1]

    def get_asiento(self, obj):
        return _asiento(obj.asiento)


class CuentaPorPagarDetalleSerializer(CuentaPorPagarSerializer):
    cuenta_pasivo = serializers.SerializerMethodField()
    lineas = serializers.SerializerMethodField()
    pagos = PagoSerializer(many=True, read_only=True)
    asiento_anulacion = serializers.SerializerMethodField()
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    anulado_por = serializers.CharField(source="anulado_por.username", read_only=True, default=None)

    class Meta(CuentaPorPagarSerializer.Meta):
        fields = CuentaPorPagarSerializer.Meta.fields + [
            "cuenta_pasivo", "lineas", "pagos", "asiento_anulacion", "motivo_anulacion", "creado_por", "creado_en",
            "anulado_por", "anulado_en",
        ]
        read_only_fields = fields

    def get_cuenta_pasivo(self, obj):
        return {"id": obj.cuenta_pasivo_id, "codigo": obj.cuenta_pasivo.codigo, "nombre": obj.cuenta_pasivo.nombre}

    def get_lineas(self, obj):
        """Imputación: las líneas de cargo del asiento de registro."""
        return [
            {
                "cuenta": {"codigo": l.cuenta.codigo, "nombre": l.cuenta.nombre},
                "centro_costo": l.centro_costo and {"codigo": l.centro_costo.codigo, "nombre": l.centro_costo.nombre},
                "descripcion": l.descripcion,
                "monto": f"{l.debe:.2f}",
            }
            for l in obj.asiento.lineas.select_related("cuenta", "centro_costo").order_by("numero_linea")
            if l.debe > 0
        ]

    def get_asiento_anulacion(self, obj):
        return _asiento(obj.asiento_anulacion)


class LineaImputacionSerializer(serializers.Serializer):
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all())
    centro_costo = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False, allow_null=True, default=None)
    descripcion = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)


class CuentaPorPagarCrearSerializer(serializers.Serializer):
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all())
    tipo_documento = serializers.ChoiceField(choices=CuentaPorPagar.TipoDocumento.choices)
    numero_documento = serializers.CharField(max_length=40)
    fecha_emision = serializers.DateField()
    fecha_vencimiento = serializers.DateField()
    concepto = serializers.CharField(max_length=300)
    cuenta_pasivo = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False, allow_null=True, default=None)
    lineas = LineaImputacionSerializer(many=True)


class PagoCrearSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    cuenta_banco = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all())
    referencia = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")


class AnularSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    fecha = serializers.DateField(required=False, allow_null=True, default=None)


class FiltroCuentasPorPagarSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False, allow_null=True, default=None)
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all(), required=False, allow_null=True, default=None)
    estado = serializers.ChoiceField(
        choices=[*CuentaPorPagar.Estado.choices, ("CON_SALDO", "Con saldo")], required=False, allow_blank=True, default=""
    )
    vencimiento = serializers.ChoiceField(
        choices=[("VENCIDA", "Vencida"), ("POR_VENCER", "Por vencer"), ("AL_DIA", "Al día")], required=False, allow_blank=True, default=""
    )
    q = serializers.CharField(required=False, allow_blank=True, default="")
