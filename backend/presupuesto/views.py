from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from usuarios import roles
from usuarios.permissions import TieneRol

from . import services
from .models import PresupuestoInstitucional
from .serializers import (
    AprobarSerializer,
    CambiarMontoSerializer,
    PresupuestoActualizarSerializer,
    PresupuestoCrearSerializer,
    PresupuestoDetalleSerializer,
    PresupuestoSerializer,
)


class PresupuestoViewSet(viewsets.GenericViewSet):
    """Presupuesto institucional (T4.1). Lectura: autenticados. Escritura: Contador."""

    serializer_class = PresupuestoSerializer
    queryset = PresupuestoInstitucional.objects.select_related("aprobado_por", "creado_por", "modificado_por")
    pagination_class = None

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
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
