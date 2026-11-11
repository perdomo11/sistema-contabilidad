from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import SAFE_METHODS, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from config.excel import respuesta_excel
from usuarios import roles
from usuarios.permissions import TieneRol

from . import cuentas_por_pagar as cpp
from . import exportacion, flujo, proyeccion, services
from .dashboard import dashboard_tesoreria
from .libro_compras import libro_compras as libro_compras_servicio
from .models import ClasificacionFlujo, CuentaPorPagar, EgresoProgramado, PagoCuentaPorPagar, Proveedor
from .serializers import (
    AnularSerializer,
    AsignarActividadSerializer,
    ConfiguracionTesoreriaSerializer,
    CuentaPorPagarCrearSerializer,
    CuentaPorPagarDetalleSerializer,
    CuentaPorPagarSerializer,
    EgresoProgramadoEntradaSerializer,
    EgresoProgramadoSerializer,
    FiltroCuentasPorPagarSerializer,
    FiltroFlujoProyectadoSerializer,
    FiltroFlujoSerializer,
    FiltroLibroMesSerializer,
    FiltroProveedoresSerializer,
    FiltroProyeccionSerializer,
    PagoCrearSerializer,
    ProgramarPagoSerializer,
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


# =============================================================================
# T5.1: cuentas por pagar
# =============================================================================

class CuentaPorPagarViewSet(viewsets.GenericViewSet):
    """Cuentas por pagar. Lectura: autenticados. Registro, pagos y anulaciones: Contador o Tesorero."""

    serializer_class = CuentaPorPagarSerializer
    queryset = CuentaPorPagar.objects.select_related("proveedor", "asiento", "cuenta_pasivo")

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR, roles.TESORERO)()]

    def _fecha(self):
        filtros = FiltroCuentasPorPagarSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        return filtros.validated_data, filtros.validated_data.pop("fecha") or timezone.localdate()

    def _detalle(self, cxp, codigo=status.HTTP_200_OK):
        cxp = (
            self.get_queryset()
            .select_related("asiento_anulacion", "creado_por", "anulado_por")
            .prefetch_related("pagos__cuenta_banco", "pagos__asiento", "pagos__asiento_anulacion", "pagos__creado_por", "pagos__anulado_por")
            .get(pk=cxp.pk)
        )
        datos = CuentaPorPagarDetalleSerializer(cxp, context={"fecha": timezone.localdate()}).data
        return Response(datos, status=codigo)

    def list(self, request):
        filtros, fecha = self._fecha()
        pagina = self.paginate_queryset(cpp.consultar_cuentas_por_pagar(fecha=fecha, **filtros))
        return self.get_paginated_response(CuentaPorPagarSerializer(pagina, many=True, context={"fecha": fecha}).data)

    @action(detail=False, methods=["get"])
    def resumen(self, request):
        _, fecha = self._fecha()
        return Response(cpp.resumen_cuentas_por_pagar(fecha=fecha))

    def retrieve(self, request, pk=None):
        return self._detalle(self.get_object())

    def create(self, request):
        entrada = CuentaPorPagarCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cxp = cpp.registrar_cuenta_por_pagar(usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(cxp, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        entrada = AnularSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return self._detalle(cpp.anular_cuenta_por_pagar(self.get_object(), usuario=request.user, request=request, **entrada.validated_data))

    @action(detail=True, methods=["post"])
    def pagos(self, request, pk=None):
        entrada = PagoCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cxp = self.get_object()
        cpp.registrar_pago(cxp, usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(cxp, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path=r"pagos/(?P<pago_id>[0-9]+)/anular")
    def anular_pago(self, request, pk=None, pago_id=None):
        entrada = AnularSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cxp = self.get_object()
        pago = get_object_or_404(PagoCuentaPorPagar, pk=pago_id, cuenta_por_pagar=cxp)
        cpp.anular_pago(pago, usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(cxp)

    @action(detail=True, methods=["post"])
    def programar(self, request, pk=None):
        entrada = ProgramarPagoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cxp = proyeccion.programar_pago(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(cxp)


# =============================================================================
# T5.2: egresos programados y proyección de egresos
# =============================================================================

class EgresoProgramadoViewSet(viewsets.GenericViewSet):
    """Egresos programados. Lectura: autenticados. Escritura: Contador o Tesorero."""

    serializer_class = EgresoProgramadoSerializer
    queryset = EgresoProgramado.objects.select_related("proveedor", "modificado_por")
    pagination_class = None

    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR, roles.TESORERO)()]

    def _salida(self, obj, codigo=status.HTTP_200_OK, many=False):
        return Response(EgresoProgramadoSerializer(obj, many=many, context={"fecha": timezone.localdate()}).data, status=codigo)

    def list(self, request):
        return self._salida(self.get_queryset(), many=True)

    def retrieve(self, request, pk=None):
        return self._salida(self.get_object())

    def create(self, request):
        entrada = EgresoProgramadoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        egreso = proyeccion.crear_egreso_programado(usuario=request.user, request=request, **entrada.validated_data)
        return self._salida(egreso, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = EgresoProgramadoEntradaSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        datos = {k: v for k, v in entrada.validated_data.items() if k in request.data}
        egreso = proyeccion.actualizar_egreso_programado(self.get_object(), usuario=request.user, datos=datos, request=request)
        return self._salida(egreso)

    def destroy(self, request, pk=None):
        proyeccion.eliminar_egreso_programado(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def proyeccion_egresos(request):
    """Proyección de egresos a 30/60/90 días (T5.2)."""
    filtros = FiltroProyeccionSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return Response(proyeccion.proyeccion_egresos(fecha=filtros.validated_data["fecha"] or timezone.localdate()))


# =============================================================================
# T5.3: flujo de efectivo
# =============================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def flujo_efectivo(request):
    """Flujo de efectivo real del periodo, método directo (T5.3)."""
    filtros = FiltroFlujoSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return Response(flujo.flujo_efectivo(**filtros.validated_data))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def flujo_proyectado(request):
    """Flujo de efectivo proyectado a 13 semanas con alertas de déficit (T5.3)."""
    filtros = FiltroFlujoProyectadoSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    fecha = filtros.validated_data["fecha"] or timezone.localdate()
    return Response(flujo.flujo_proyectado(fecha=fecha, entradas=filtros.validated_data["entradas"]))


def _clasificacion_respuesta():
    from contabilidad.models import Cuenta

    actividades = flujo.actividades_por_cuenta()
    asignadas = ClasificacionFlujo.objects.select_related("cuenta", "modificado_por").order_by("cuenta__codigo")
    efectivo = Cuenta.objects.filter(pk__in=flujo.cuentas_efectivo(), acepta_movimientos=True).order_by("codigo")
    return {
        "asignaciones": [
            {"id": c.pk, "cuenta": {"id": c.cuenta_id, "codigo": c.cuenta.codigo, "nombre": c.cuenta.nombre},
             "actividad": c.actividad, "actividad_display": c.get_actividad_display(),
             "modificado_por": c.modificado_por.username, "modificado_en": c.modificado_en}
            for c in asignadas
        ],
        "cuentas_efectivo": [{"id": c.pk, "codigo": c.codigo, "nombre": c.nombre} for c in efectivo],
        "actividad_por_cuenta": {str(k): v[0] for k, v in actividades.items()},
        "actividades": [{"valor": v, "nombre": n} for v, n in ClasificacionFlujo.Actividad.choices],
    }


class _EscrituraTesoreria:
    def get_permissions(self):
        if self.request.method in SAFE_METHODS:
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR, roles.TESORERO)()]


class ClasificacionFlujoViewSet(_EscrituraTesoreria, viewsets.GenericViewSet):
    """Cuentas de efectivo y actividad de flujo por cuenta (con herencia)."""

    queryset = ClasificacionFlujo.objects.select_related("cuenta")
    pagination_class = None

    def list(self, request):
        return Response(_clasificacion_respuesta())

    def create(self, request):
        entrada = AsignarActividadSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        flujo.asignar_actividad(usuario=request.user, request=request, **entrada.validated_data)
        return Response(_clasificacion_respuesta(), status=status.HTTP_201_CREATED)

    def destroy(self, request, pk=None):
        flujo.quitar_actividad(self.get_object(), usuario=request.user, request=request)
        return Response(_clasificacion_respuesta())


class ConfiguracionTesoreriaView(_EscrituraTesoreria, APIView):
    """Política de liquidez: saldo mínimo y días de historia para estimar entradas."""

    def _salida(self, config):
        return Response({
            "saldo_minimo": f"{config.saldo_minimo:.2f}", "dias_historia": config.dias_historia,
            "modificado_por": config.modificado_por.username if config.modificado_por else None,
            "modificado_en": config.modificado_en,
        })

    def get(self, request):
        return self._salida(flujo.configuracion())

    def patch(self, request):
        entrada = ConfiguracionTesoreriaSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        return self._salida(flujo.actualizar_configuracion(usuario=request.user, datos=entrada.validated_data, request=request))


# =============================================================================
# T5.4: dashboard de tesorería
# =============================================================================

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def dashboard(request):
    """Dashboard de tesorería: compone cuentas por pagar, proyección de egresos y flujo de efectivo (T5.4)."""
    filtros = FiltroProyeccionSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return Response(dashboard_tesoreria(fecha=filtros.validated_data["fecha"] or timezone.localdate()))


# =============================================================================
# T7.2: libro de compras
# =============================================================================

def _filtro_mes(request):
    filtros = FiltroLibroMesSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return filtros.validated_data


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def libro_compras(request):
    """Libro de compras del mes (?anio=&mes=): CCF recibidos con su desglose fiscal."""
    return Response(libro_compras_servicio(**_filtro_mes(request)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def libro_compras_exportar(request):
    """Libro de compras del mes en Excel."""
    f = _filtro_mes(request)
    contenido = exportacion.libro_compras_xlsx(usuario=request.user, **f)
    return respuesta_excel(f"libro_compras_{f['anio']}_{f['mes']:02d}.xlsx", contenido)
