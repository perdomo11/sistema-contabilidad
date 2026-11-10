from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services
from .serializers import FiltroEstadoResultadosSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def estado_resultados(request):
    """Estado de resultados por centro, costeo absorbente (T3.1)."""
    filtros = FiltroEstadoResultadosSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return Response(services.estado_resultados(**filtros.validated_data))
