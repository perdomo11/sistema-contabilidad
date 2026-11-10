from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import TieneRol

from . import services
from .models import CentroCosto, ReglaAsignacion
from .serializers import (
    CentroActualizarSerializer,
    CentroCostoSerializer,
    CentroCrearSerializer,
    FiltroCentrosSerializer,
    FiltroReglasSerializer,
    ReglaActualizarSerializer,
    ReglaAsignacionSerializer,
    ReglaCrearSerializer,
    ResolverReglasSerializer,
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


class ReglaAsignacionViewSet(viewsets.GenericViewSet):
    """Reglas de asignación cuenta/proveedor → centro (T2.2). Lectura: autenticados. Escritura: Contador."""

    serializer_class = ReglaAsignacionSerializer
    queryset = ReglaAsignacion.objects.select_related("cuenta", "proveedor", "centro_costo")

    def get_permissions(self):
        if self.action in ("list", "retrieve", "resolver"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]

    def list(self, request):
        filtros = FiltroReglasSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        reglas = services.consultar_reglas(**filtros.validated_data).annotate(lineas_aplicadas=Count("lineas"))
        pagina = self.paginate_queryset(reglas)
        return self.get_paginated_response(ReglaAsignacionSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ReglaAsignacionSerializer(self.get_object()).data)

    def create(self, request):
        entrada = ReglaCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        regla = services.crear_regla(usuario=request.user, request=request, **entrada.validated_data)
        return Response(ReglaAsignacionSerializer(regla).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = ReglaActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        regla = services.actualizar_regla(
            self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request
        )
        return Response(ReglaAsignacionSerializer(regla).data)

    def destroy(self, request, pk=None):
        services.eliminar_regla(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False)
    def resolver(self, request):
        """Vista previa para el editor: centro que se asignaría por regla a cada cuenta.

        Respuesta: {id_cuenta: {regla, criterio, centro_costo, centro_codigo, centro_nombre} | null}.
        """
        entrada = ResolverReglasSerializer(data=request.query_params)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        resultado = {}
        for cuenta in datos["cuentas"]:
            regla = services.resolver_regla(cuenta, datos["proveedor"], datos["fecha"])
            resultado[cuenta.pk] = regla and {
                "regla": regla.pk,
                "criterio": regla.criterio,
                "centro_costo": regla.centro_costo_id,
                "centro_codigo": regla.centro_costo.codigo,
                "centro_nombre": regla.centro_costo.nombre,
            }
        return Response(resultado)
