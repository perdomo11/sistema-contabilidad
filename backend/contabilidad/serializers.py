from rest_framework import serializers

from centros_costo.models import CentroCosto
from tesoreria.models import Proveedor

from .models import Asiento, Cuenta, LineaAsiento, PeriodoContable


class CuentaSerializer(serializers.ModelSerializer):
    padre_codigo = serializers.CharField(source="padre.codigo", read_only=True, default=None)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    naturaleza_display = serializers.CharField(source="get_naturaleza_display", read_only=True)
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)

    class Meta:
        model = Cuenta
        fields = [
            "id",
            "codigo",
            "nombre",
            "padre",
            "padre_codigo",
            "nivel",
            "tipo",
            "tipo_display",
            "naturaleza",
            "naturaleza_display",
            "acepta_movimientos",
            "exenta_centro_costo",
            "activa",
            "creado_por",
            "creado_en",
            "modificado_por",
            "modificado_en",
        ]
        read_only_fields = fields


class CuentaCrearSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)
    nombre = serializers.CharField(max_length=200)
    padre = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False, allow_null=True)
    tipo = serializers.ChoiceField(choices=Cuenta.Tipo.choices, required=False, allow_null=True)
    naturaleza = serializers.ChoiceField(choices=Cuenta.Naturaleza.choices, required=False, allow_null=True)
    acepta_movimientos = serializers.BooleanField(default=True)
    exenta_centro_costo = serializers.BooleanField(default=False)


class CuentaActualizarSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=200, required=False)
    naturaleza = serializers.ChoiceField(choices=Cuenta.Naturaleza.choices, required=False)
    acepta_movimientos = serializers.BooleanField(required=False)
    exenta_centro_costo = serializers.BooleanField(required=False)
    activa = serializers.BooleanField(required=False)

    def validate(self, attrs):
        inmutables = {"codigo", "padre", "tipo", "nivel"} & set(self.initial_data)
        if inmutables:
            raise serializers.ValidationError(
                {campo: "No se puede modificar después de crear la cuenta." for campo in sorted(inmutables)}
            )
        return attrs


class FiltroCuentasSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=Cuenta.Tipo.choices, required=False)
    activa = serializers.BooleanField(required=False, allow_null=True, default=None)
    acepta_movimientos = serializers.BooleanField(required=False, allow_null=True, default=None)
    q = serializers.CharField(required=False, allow_blank=True)


class PeriodoSerializer(serializers.ModelSerializer):
    nombre = serializers.CharField(read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    cerrado_por = serializers.CharField(source="cerrado_por.username", read_only=True, default=None)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)

    class Meta:
        model = PeriodoContable
        fields = [
            "id",
            "anio",
            "mes",
            "nombre",
            "fecha_inicio",
            "fecha_fin",
            "estado",
            "estado_display",
            "cerrado_por",
            "cerrado_en",
            "modificado_por",
            "modificado_en",
        ]
        read_only_fields = fields


class CrearEjercicioSerializer(serializers.Serializer):
    anio = serializers.IntegerField()


class ReabrirPeriodoSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=400, allow_blank=True, required=False, default="")


class FiltroPeriodosSerializer(serializers.Serializer):
    anio = serializers.IntegerField(required=False)


# =============================================================================
# Asientos (T1.3)
# =============================================================================


class AsientoResumenSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    codigo = serializers.CharField()


class LineaAsientoSerializer(serializers.ModelSerializer):
    cuenta_codigo = serializers.CharField(source="cuenta.codigo", read_only=True)
    cuenta_nombre = serializers.CharField(source="cuenta.nombre", read_only=True)
    cuenta_exenta_centro_costo = serializers.BooleanField(source="cuenta.exenta_centro_costo", read_only=True)
    centro_codigo = serializers.CharField(source="centro_costo.codigo", read_only=True, default=None)
    centro_nombre = serializers.CharField(source="centro_costo.nombre", read_only=True, default=None)
    asignacion = serializers.CharField(read_only=True)
    origen_asiento = serializers.IntegerField(source="linea_origen.asiento_id", read_only=True, default=None)
    origen_asiento_codigo = serializers.CharField(source="linea_origen.asiento.codigo", read_only=True, default=None)

    class Meta:
        model = LineaAsiento
        fields = [
            "id", "numero_linea", "cuenta", "cuenta_codigo", "cuenta_nombre", "cuenta_exenta_centro_costo",
            "centro_costo", "centro_codigo", "centro_nombre", "regla_asignacion", "asignacion", "descripcion", "debe",
            "haber", "linea_origen", "origen_asiento", "origen_asiento_codigo",
        ]
        read_only_fields = fields


class AsientoSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(read_only=True)
    periodo_nombre = serializers.CharField(source="periodo.nombre", read_only=True)
    periodo_estado = serializers.CharField(source="periodo.estado", read_only=True)
    proveedor_nombre = serializers.CharField(source="proveedor.nombre", read_only=True, default=None)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    cuadrado = serializers.SerializerMethodField()
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)
    contabilizado_por = serializers.CharField(source="contabilizado_por.username", read_only=True, default=None)
    reversion_de = serializers.SerializerMethodField()
    revertido_por = serializers.SerializerMethodField()

    class Meta:
        model = Asiento
        fields = [
            "id",
            "codigo",
            "ejercicio",
            "numero",
            "fecha",
            "periodo",
            "periodo_nombre",
            "periodo_estado",
            "concepto",
            "referencia",
            "proveedor",
            "proveedor_nombre",
            "tipo",
            "tipo_display",
            "estado",
            "estado_display",
            "total_debe",
            "total_haber",
            "cuadrado",
            "reversion_de",
            "revertido_por",
            "creado_por",
            "creado_en",
            "modificado_por",
            "modificado_en",
            "contabilizado_por",
            "contabilizado_en",
        ]
        read_only_fields = fields

    def get_cuadrado(self, obj):
        return obj.total_debe == obj.total_haber and obj.total_debe > 0

    def get_reversion_de(self, obj):
        original = obj.reversion_de
        return {"id": original.pk, "codigo": original.codigo} if original else None

    def get_revertido_por(self, obj):
        reversion = getattr(obj, "reversion", None)
        return {"id": reversion.pk, "codigo": reversion.codigo} if reversion else None


class AsientoDetalleSerializer(AsientoSerializer):
    lineas = LineaAsientoSerializer(many=True, read_only=True)

    class Meta(AsientoSerializer.Meta):
        fields = AsientoSerializer.Meta.fields + ["lineas"]
        read_only_fields = fields


class LineaEntradaSerializer(serializers.Serializer):
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), allow_null=True)
    centro_costo = serializers.PrimaryKeyRelatedField(
        queryset=CentroCosto.objects.all(), required=False, allow_null=True, default=None
    )
    descripcion = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    # Se reciben como texto y se validan en el servicio (2 decimales, no negativos, máximo NUMBER(18,2)).
    debe = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="0")
    haber = serializers.CharField(required=False, allow_blank=True, allow_null=True, default="0")


class AsientoEntradaSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    concepto = serializers.CharField(max_length=300, allow_blank=True)
    referencia = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")
    proveedor = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.all(), required=False, allow_null=True, default=None
    )
    lineas = LineaEntradaSerializer(many=True, allow_empty=True)


class RevertirAsientoSerializer(serializers.Serializer):
    fecha = serializers.DateField(required=False, allow_null=True, default=None)
    motivo = serializers.CharField(max_length=250, required=False, allow_blank=True, default="")


class FiltroAsientosSerializer(serializers.Serializer):
    estado = serializers.ChoiceField(choices=Asiento.Estado.choices, required=False)
    tipo = serializers.ChoiceField(choices=Asiento.Tipo.choices, required=False)
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False)
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all(), required=False)
    q = serializers.CharField(required=False, allow_blank=True)


# =============================================================================
# Libros (T1.4)
# =============================================================================


class RangoFechasSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()


class FiltroMayorSerializer(RangoFechasSerializer):
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all())


class FiltroBalanzaSerializer(RangoFechasSerializer):
    nivel = serializers.IntegerField(required=False, allow_null=True, min_value=1, default=None)
    incluir_sin_movimiento = serializers.BooleanField(required=False, default=False)


class AsientoDiarioSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(read_only=True)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    lineas = LineaAsientoSerializer(many=True, read_only=True)

    class Meta:
        model = Asiento
        fields = ["id", "codigo", "fecha", "concepto", "referencia", "tipo", "tipo_display", "total_debe", "total_haber", "lineas"]
        read_only_fields = fields
