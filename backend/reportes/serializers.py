from rest_framework import serializers

from centros_costo.models import CentroCosto


class FiltroEstadoResultadosSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()
    centro = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False, allow_null=True, default=None)
    nivel_cuentas = serializers.IntegerField(required=False, min_value=1, max_value=10, default=2)
