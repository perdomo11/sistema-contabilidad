from rest_framework import serializers

from .models import Bitacora


class BitacoraSerializer(serializers.ModelSerializer):
    accion_display = serializers.CharField(source="get_accion_display", read_only=True)

    class Meta:
        model = Bitacora
        fields = [
            "id",
            "fecha",
            "usuario",
            "nombre_usuario",
            "accion",
            "accion_display",
            "entidad",
            "objeto_id",
            "descripcion",
            "valor_anterior",
            "valor_nuevo",
            "ip",
        ]
        read_only_fields = fields


class FiltroBitacoraSerializer(serializers.Serializer):
    usuario = serializers.CharField(required=False, allow_blank=True)
    accion = serializers.ChoiceField(choices=Bitacora.Accion.choices, required=False, allow_blank=True)
    desde = serializers.DateField(required=False)
    hasta = serializers.DateField(required=False)
