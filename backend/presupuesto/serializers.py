from rest_framework import serializers

from .models import PresupuestoInstitucional, VersionPresupuesto


class VersionPresupuestoSerializer(serializers.ModelSerializer):
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    registrado_por = serializers.CharField(source="registrado_por.username", read_only=True)
    variacion = serializers.SerializerMethodField()

    class Meta:
        model = VersionPresupuesto
        fields = [
            "id", "numero", "tipo", "tipo_display", "monto", "monto_anterior", "variacion",
            "motivo", "referencia", "registrado_por", "registrado_en",
        ]
        read_only_fields = fields

    def get_variacion(self, obj):
        return None if obj.monto_anterior is None else f"{obj.monto - obj.monto_anterior:.2f}"


class PresupuestoSerializer(serializers.ModelSerializer):
    estado_display = serializers.CharField(source="get_estado_display", read_only=True)
    aprobado_por = serializers.CharField(source="aprobado_por.username", read_only=True, default=None)
    creado_por = serializers.CharField(source="creado_por.username", read_only=True)
    modificado_por = serializers.CharField(source="modificado_por.username", read_only=True)

    class Meta:
        model = PresupuestoInstitucional
        fields = [
            "id", "anio", "monto", "version", "estado", "estado_display", "descripcion",
            "referencia_aprobacion", "aprobado_por", "aprobado_en",
            "creado_por", "creado_en", "modificado_por", "modificado_en",
        ]
        read_only_fields = fields


class PresupuestoDetalleSerializer(PresupuestoSerializer):
    versiones = VersionPresupuestoSerializer(many=True, read_only=True)

    class Meta(PresupuestoSerializer.Meta):
        fields = PresupuestoSerializer.Meta.fields + ["versiones"]
        read_only_fields = fields


class PresupuestoCrearSerializer(serializers.Serializer):
    anio = serializers.IntegerField()
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    descripcion = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class PresupuestoActualizarSerializer(serializers.Serializer):
    descripcion = serializers.CharField(max_length=500, allow_blank=True)


class CambiarMontoSerializer(serializers.Serializer):
    monto = serializers.DecimalField(max_digits=18, decimal_places=2)
    motivo = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    referencia = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class AprobarSerializer(serializers.Serializer):
    referencia = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
