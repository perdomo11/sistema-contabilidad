from django.contrib.auth.models import User
from rest_framework import serializers

from .models import CentroCosto

INMUTABLES = {"codigo", "padre", "nivel"}


class CentroCostoSerializer(serializers.ModelSerializer):
    padre_codigo = serializers.CharField(source="padre.codigo", read_only=True, default=None)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    clase_display = serializers.CharField(source="get_clase_display", read_only=True)
    responsable_nombre = serializers.SerializerMethodField()

    class Meta:
        model = CentroCosto
        fields = [
            "id", "codigo", "nombre", "padre", "padre_codigo", "nivel", "tipo", "tipo_display", "clase",
            "clase_display", "responsable", "responsable_nombre", "acepta_movimientos", "vigente_desde",
            "vigente_hasta", "creado_en", "modificado_en",
        ]
        read_only_fields = fields

    def get_responsable_nombre(self, obj):
        r = obj.responsable
        return (r.get_full_name() or r.username) if r else None


class CentroCrearSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)
    nombre = serializers.CharField(max_length=150)
    padre = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False, allow_null=True)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices)
    responsable = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    acepta_movimientos = serializers.BooleanField(default=True)
    vigente_desde = serializers.DateField()
    vigente_hasta = serializers.DateField(required=False, allow_null=True)


class CentroActualizarSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150, required=False)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices, required=False)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices, required=False)
    responsable = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    acepta_movimientos = serializers.BooleanField(required=False)
    vigente_desde = serializers.DateField(required=False)
    vigente_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        prohibidos = INMUTABLES & set(self.initial_data)
        if prohibidos:
            raise serializers.ValidationError(
                {c: "No se puede modificar; cierre la vigencia y cree una unidad nueva." for c in sorted(prohibidos)}
            )
        return attrs


class FiltroCentrosSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices, required=False)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices, required=False)
    acepta_movimientos = serializers.BooleanField(required=False, allow_null=True, default=None)
    vigente_en = serializers.DateField(required=False)
