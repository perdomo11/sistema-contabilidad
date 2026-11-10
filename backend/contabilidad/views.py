from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import TieneRol

from . import services
from .models import Cuenta
from .serializers import (
    CuentaActualizarSerializer,
    CuentaCrearSerializer,
    CuentaSerializer,
    FiltroCuentasSerializer,
)

ACCIONES_LECTURA = {"list", "retrieve", "arbol"}


class CuentaViewSet(viewsets.GenericViewSet):
    """Catálogo de cuentas. Lectura: cualquier usuario autenticado. Escritura: Contador."""

    serializer_class = CuentaSerializer
    queryset = Cuenta.objects.select_related("padre", "creado_por", "modificado_por")

    def get_permissions(self):
        if self.action in ACCIONES_LECTURA:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]

    def list(self, request):
        filtros = FiltroCuentasSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        qs = services.consultar_cuentas(**filtros.validated_data)
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(CuentaSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(CuentaSerializer(self.get_object()).data)

    @action(detail=False)
    def arbol(self, request):
        return Response(services.arbol_cuentas())

    def create(self, request):
        entrada = CuentaCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cuenta = services.crear_cuenta(usuario=request.user, request=request, **entrada.validated_data)
        return Response(CuentaSerializer(cuenta).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = CuentaActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cuenta = services.actualizar_cuenta(
            self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request
        )
        return Response(CuentaSerializer(cuenta).data)

    def destroy(self, request, pk=None):
        services.eliminar_cuenta(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)
