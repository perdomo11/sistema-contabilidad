from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import TieneRol

from . import services
from .models import Proveedor
from .serializers import (
    FiltroProveedoresSerializer,
    ProveedorActualizarSerializer,
    ProveedorCrearSerializer,
    ProveedorSerializer,
)


class ProveedorViewSet(viewsets.GenericViewSet):
    """Proveedores. Lectura: autenticados. Escritura: Contador o Tesorero."""

    serializer_class = ProveedorSerializer
    queryset = Proveedor.objects.select_related("creado_por", "modificado_por")

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR, roles.TESORERO)()]

    def list(self, request):
        filtros = FiltroProveedoresSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(
            services.consultar_proveedores(**filtros.validated_data).select_related("creado_por", "modificado_por")
        )
        return self.get_paginated_response(ProveedorSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ProveedorSerializer(self.get_object()).data)

    def create(self, request):
        entrada = ProveedorCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        proveedor = services.crear_proveedor(usuario=request.user, request=request, **entrada.validated_data)
        return Response(ProveedorSerializer(proveedor).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = ProveedorActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        proveedor = services.actualizar_proveedor(
            self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request
        )
        return Response(ProveedorSerializer(proveedor).data)

    def destroy(self, request, pk=None):
        services.eliminar_proveedor(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
