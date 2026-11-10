from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import TieneRol

from . import services
from .models import CentroCosto
from .serializers import (
    CentroActualizarSerializer,
    CentroCostoSerializer,
    CentroCrearSerializer,
    FiltroCentrosSerializer,
)


class CentroCostoViewSet(viewsets.GenericViewSet):
    """Centros de costo. Lectura: autenticados. Escritura: Contador."""

    serializer_class = CentroCostoSerializer
    queryset = CentroCosto.objects.select_related("padre", "responsable")

    def get_permissions(self):
        if self.action in ("list", "retrieve", "arbol"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]

    def list(self, request):
        filtros = FiltroCentrosSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(services.consultar_centros(**filtros.validated_data))
        return self.get_paginated_response(CentroCostoSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(CentroCostoSerializer(self.get_object()).data)

    @action(detail=False)
    def arbol(self, request):
        return Response(services.arbol_centros())

    def create(self, request):
        entrada = CentroCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        centro = services.crear_centro(usuario=request.user, request=request, **entrada.validated_data)
        return Response(CentroCostoSerializer(centro).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = CentroActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        centro = services.actualizar_centro(
            self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request
        )
        return Response(CentroCostoSerializer(centro).data)

    def destroy(self, request, pk=None):
        services.eliminar_centro(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
