from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import EsSuperusuario, TieneRol

from . import libros, services
from .models import Asiento, Cuenta, PeriodoContable
from .serializers import (
    AsientoDiarioSerializer,
    FiltroBalanzaSerializer,
    FiltroMayorSerializer,
    RangoFechasSerializer,
    AsientoDetalleSerializer,
    AsientoEntradaSerializer,
    AsientoSerializer,
    FiltroAsientosSerializer,
    RevertirAsientoSerializer,
    CrearEjercicioSerializer,
    CuentaActualizarSerializer,
    CuentaCrearSerializer,
    CuentaSerializer,
    FiltroCuentasSerializer,
    FiltroPeriodosSerializer,
    PeriodoSerializer,
    ReabrirPeriodoSerializer,
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


class PeriodoViewSet(viewsets.GenericViewSet):
    """Periodos contables. Lectura: autenticados. Crear ejercicio y cerrar: Contador. Reabrir: superusuario."""

    serializer_class = PeriodoSerializer
    queryset = PeriodoContable.objects.select_related("cerrado_por", "modificado_por")
    pagination_class = None

    def get_permissions(self):
        if self.action == "reabrir":
            return [EsSuperusuario()]
        if self.action == "cerrar" or (self.action == "ejercicios" and self.request.method == "POST"):
            return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]
        return [IsAuthenticated()]

    def list(self, request):
        filtros = FiltroPeriodosSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(PeriodoSerializer(services.consultar_periodos(**filtros.validated_data), many=True).data)

    @action(detail=False, methods=["get", "post"])
    def ejercicios(self, request):
        if request.method == "GET":
            return Response(services.resumen_ejercicios())
        entrada = CrearEjercicioSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        periodos = services.crear_ejercicio(usuario=request.user, request=request, **entrada.validated_data)
        return Response(PeriodoSerializer(periodos, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        periodo = services.cerrar_periodo(self.get_object(), usuario=request.user, request=request)
        return Response(PeriodoSerializer(periodo).data)

    @action(detail=True, methods=["post"])
    def reabrir(self, request, pk=None):
        entrada = ReabrirPeriodoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        periodo = services.reabrir_periodo(
            self.get_object(), usuario=request.user, request=request, **entrada.validated_data
        )
        return Response(PeriodoSerializer(periodo).data)


class AsientoViewSet(viewsets.GenericViewSet):
    """Asientos contables. Lectura: autenticados. Escritura, contabilización y reversión: Contador."""

    serializer_class = AsientoSerializer
    queryset = Asiento.objects.select_related(
        "periodo", "proveedor", "creado_por", "modificado_por", "contabilizado_por", "reversion_de", "reversion"
    )

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]

    def _detalle(self, asiento, codigo=status.HTTP_200_OK):
        asiento = self.get_queryset().prefetch_related("lineas__cuenta", "lineas__centro_costo", "lineas__linea_origen__asiento").get(pk=asiento.pk)
        return Response(AsientoDetalleSerializer(asiento).data, status=codigo)

    def list(self, request):
        filtros = FiltroAsientosSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(services.consultar_asientos(**filtros.validated_data))
        return self.get_paginated_response(AsientoSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return self._detalle(self.get_object())

    def create(self, request):
        entrada = AsientoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        asiento = services.crear_asiento(usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(asiento, status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        entrada = AsientoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        asiento = services.actualizar_asiento(
            self.get_object(), usuario=request.user, request=request, **entrada.validated_data
        )
        return self._detalle(asiento)

    def destroy(self, request, pk=None):
        services.eliminar_asiento(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def contabilizar(self, request, pk=None):
        asiento = services.contabilizar_asiento(self.get_object(), usuario=request.user, request=request)
        return self._detalle(asiento)

    @action(detail=True, methods=["post"])
    def revertir(self, request, pk=None):
        entrada = RevertirAsientoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        reversion = services.revertir_asiento(
            self.get_object(), usuario=request.user, request=request, **entrada.validated_data
        )
        return self._detalle(reversion, status.HTTP_201_CREATED)


class LibrosViewSet(viewsets.GenericViewSet):
    """Libros contables de solo lectura sobre asientos contabilizados. Cualquier usuario autenticado."""

    permission_classes = [IsAuthenticated]
    serializer_class = AsientoDiarioSerializer

    @action(detail=False)
    def diario(self, request):
        filtros = RangoFechasSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        asientos, totales = libros.libro_diario(**filtros.validated_data)
        pagina = self.paginate_queryset(asientos)
        respuesta = self.get_paginated_response(AsientoDiarioSerializer(pagina, many=True).data)
        respuesta.data["totales"] = totales
        return respuesta

    @action(detail=False)
    def mayor(self, request):
        filtros = FiltroMayorSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(libros.libro_mayor(**filtros.validated_data))

    @action(detail=False)
    def balanza(self, request):
        filtros = FiltroBalanzaSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(libros.balanza_comprobacion(**filtros.validated_data))
