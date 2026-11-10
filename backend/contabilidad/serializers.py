from rest_framework import serializers

from .models import Cuenta, PeriodoContable


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
