from rest_framework import serializers

from .models import Proveedor


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
