from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios import roles
from usuarios.permissions import TieneRol

from . import prorrateo, services
from .models import BaseProrrateo, CentroCosto, EjecucionProrrateo, ReglaAsignacion, ReglaProrrateo
from .serializers import (
    AnularSerializer,
    BaseActualizarSerializer,
    BaseCrearSerializer,
    BaseProrrateoSerializer,
    CentroActualizarSerializer,
    CentroCostoSerializer,
    CentroCrearSerializer,
    EjecucionSerializer,
    FiltroCentrosSerializer,
    FiltroMedidasSerializer,
    FiltroReglasSerializer,
    GuardarMedidasSerializer,
    PeriodoSerializer,
    ReglaActualizarSerializer,
    ReglaAsignacionSerializer,
    ReglaCrearSerializer,
    ReglaPeriodoSerializer,
    ReglaProrrateoActualizarSerializer,
    ReglaProrrateoEntradaSerializer,
    ReglaProrrateoSerializer,
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


# =============================================================================
# Prorrateo (T2.3). Lectura: autenticados. Configuración, ejecución y anulación: Contador.
# =============================================================================


class _SoloContadorEscribe:
    acciones_lectura = ("list", "retrieve", "previsualizar")

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS") or getattr(self, "action", None) in self.acciones_lectura:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR)()]


class BaseProrrateoViewSet(_SoloContadorEscribe, viewsets.GenericViewSet):
    serializer_class = BaseProrrateoSerializer
    queryset = BaseProrrateo.objects.order_by("codigo")
    pagination_class = None

    def list(self, request):
        return Response(BaseProrrateoSerializer(self.get_queryset(), many=True).data)

    def create(self, request):
        entrada = BaseCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        base = prorrateo.crear_base(usuario=request.user, request=request, **entrada.validated_data)
        return Response(BaseProrrateoSerializer(base).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = BaseActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        base = prorrateo.actualizar_base(self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request)
        return Response(BaseProrrateoSerializer(base).data)

    def destroy(self, request, pk=None):
        prorrateo.eliminar_base(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MedidasView(_SoloContadorEscribe, APIView):
    """Cuadrícula de medidas de una base en un periodo."""

    def get(self, request):
        filtros = FiltroMedidasSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        return Response(prorrateo.cuadricula_medidas(**filtros.validated_data))

    def put(self, request):
        entrada = GuardarMedidasSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return Response(prorrateo.guardar_medidas(usuario=request.user, request=request, **entrada.validated_data))


class CopiarMedidasView(_SoloContadorEscribe, APIView):
    def post(self, request):
        entrada = FiltroMedidasSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        copiadas, cuadricula = prorrateo.copiar_medidas(usuario=request.user, request=request, **entrada.validated_data)
        return Response({**cuadricula, "copiadas": copiadas})


class ReglaProrrateoViewSet(_SoloContadorEscribe, viewsets.GenericViewSet):
    serializer_class = ReglaProrrateoSerializer
    queryset = ReglaProrrateo.objects.select_related("centro_origen", "base").prefetch_related("cuentas", "destinos")
    pagination_class = None

    def list(self, request):
        return Response(ReglaProrrateoSerializer(self.get_queryset().order_by("orden", "id"), many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ReglaProrrateoSerializer(self.get_object()).data)

    def create(self, request):
        entrada = ReglaProrrateoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        regla = prorrateo.crear_regla(usuario=request.user, request=request, **entrada.validated_data)
        return Response(ReglaProrrateoSerializer(self.get_queryset().get(pk=regla.pk)).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = ReglaProrrateoActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        regla = prorrateo.actualizar_regla(self.get_object(), usuario=request.user, datos=dict(entrada.validated_data), request=request)
        return Response(ReglaProrrateoSerializer(self.get_queryset().get(pk=regla.pk)).data)

    def destroy(self, request, pk=None):
        prorrateo.eliminar_regla(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EjecucionProrrateoViewSet(_SoloContadorEscribe, viewsets.GenericViewSet):
    serializer_class = EjecucionSerializer
    queryset = EjecucionProrrateo.objects.select_related(
        "regla", "periodo", "asiento", "asiento__reversion", "ejecutado_por", "anulado_por"
    )

    def list(self, request):
        """Estado del periodo: cada regla con su ejecución vigente y su historial."""
        filtros = PeriodoSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        resultado = []
        for regla, ejecuciones in prorrateo.estado_periodo(filtros.validated_data["periodo"]):
            vigente = next((e for e in ejecuciones if e.estado == EjecucionProrrateo.Estado.EJECUTADA), None)
            resultado.append({
                "regla": {
                    "id": regla.pk, "nombre": regla.nombre, "orden": regla.orden, "activa": regla.activa,
                    "centro_origen_codigo": regla.centro_origen.codigo, "centro_origen_nombre": regla.centro_origen.nombre,
                    "base_nombre": regla.base.nombre,
                },
                "estado": "EJECUTADA" if vigente else ("ANULADA" if ejecuciones else "PENDIENTE"),
                "vigente": EjecucionSerializer(vigente).data if vigente else None,
                "historial": EjecucionSerializer(ejecuciones, many=True).data,
            })
        return Response(resultado)

    def retrieve(self, request, pk=None):
        return Response(EjecucionSerializer(self.get_object()).data)

    @action(detail=False)
    def previsualizar(self, request):
        entrada = ReglaPeriodoSerializer(data=request.query_params)
        entrada.is_valid(raise_exception=True)
        return Response(prorrateo.previsualizar(entrada.validated_data["regla"], entrada.validated_data["periodo"]))

    def create(self, request):
        entrada = ReglaPeriodoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ejecucion = prorrateo.ejecutar(usuario=request.user, request=request, **entrada.validated_data)
        return Response(EjecucionSerializer(self.get_queryset().get(pk=ejecucion.pk)).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"])
    def pendientes(self, request):
        entrada = PeriodoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return Response(prorrateo.ejecutar_pendientes(usuario=request.user, request=request, **entrada.validated_data))

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        entrada = AnularSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ejecucion = prorrateo.anular(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return Response(EjecucionSerializer(self.get_queryset().get(pk=ejecucion.pk)).data)
