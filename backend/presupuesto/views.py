from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response

from centros_costo.models import CentroCosto
from usuarios import roles
from usuarios.permissions import TieneRol

from . import distribucion, services
from .models import PresupuestoInstitucional
from .serializers import (
    AprobarSerializer,
    AsignarDepartamentoSerializer,
    CambiarMontoSerializer,
    CambioDistribucionSerializer,
    FiltroHistorialSerializer,
    GuardarDetalleSerializer,
    PresupuestoActualizarSerializer,
    PresupuestoCrearSerializer,
    PresupuestoDetalleSerializer,
    PresupuestoSerializer,
)


class PresupuestoViewSet(viewsets.GenericViewSet):
    """Presupuesto institucional (T4.1). Lectura: autenticados. Escritura: Contador.

    T4.2 agrega la distribución a departamentos y su detalle por cuenta y mes.
    """

    serializer_class = PresupuestoSerializer
    queryset = PresupuestoInstitucional.objects.select_related("aprobado_por", "creado_por", "modificado_por")
    pagination_class = None

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]

    def _detalle(self, presupuesto, codigo=status.HTTP_200_OK):
        presupuesto = self.get_queryset().prefetch_related("versiones__registrado_por").get(pk=presupuesto.pk)
        return Response(PresupuestoDetalleSerializer(presupuesto).data, status=codigo)

    def list(self, request):
        return Response(PresupuestoSerializer(self.get_queryset().order_by("-anio"), many=True).data)

    def retrieve(self, request, pk=None):
        return self._detalle(self.get_object())

    def create(self, request):
        entrada = PresupuestoCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        p = services.crear_presupuesto(usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(p, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = PresupuestoActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        p = services.actualizar_descripcion(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(p)

    @action(detail=True, methods=["post"], url_path="cambiar-monto")
    def cambiar_monto(self, request, pk=None):
        entrada = CambiarMontoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        p = services.cambiar_monto(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(p)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None):
        entrada = AprobarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        p = services.aprobar_presupuesto(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(p)

    @action(detail=True, methods=["post"])
    def cerrar(self, request, pk=None):
        return self._detalle(services.cerrar_presupuesto(self.get_object(), usuario=request.user, request=request))

    # ------------------------------------------------------------------
    # T4.2: distribución a departamentos
    # ------------------------------------------------------------------
    @action(detail=True, methods=["get", "post"])
    def distribucion(self, request, pk=None):
        presupuesto = self.get_object()
        if request.method == "GET":
            return Response(distribucion.resumen_distribucion(presupuesto))
        entrada = AsignarDepartamentoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return Response(
            distribucion.asignar_departamento(presupuesto, usuario=request.user, request=request, **entrada.validated_data)
        )

    @action(detail=True, methods=["get", "put"], url_path=r"distribucion/(?P<centro_id>[0-9]+)")
    def detalle_departamento(self, request, pk=None, centro_id=None):
        presupuesto = self.get_object()
        centro = get_object_or_404(CentroCosto, pk=centro_id)
        if request.method == "GET":
            return Response(distribucion.detalle_departamento(presupuesto, centro))
        entrada = GuardarDetalleSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return Response(
            distribucion.guardar_detalle(presupuesto, usuario=request.user, centro=centro, request=request, **entrada.validated_data)
        )

    @action(detail=True, methods=["get"], url_path="historial-distribucion")
    def historial_distribucion(self, request, pk=None):
        filtros = FiltroHistorialSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        cambios = distribucion.historial_distribucion(self.get_object(), **filtros.validated_data)[:500]
        return Response(CambioDistribucionSerializer(cambios, many=True).data)
