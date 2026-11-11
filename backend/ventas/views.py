from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from config.excel import respuesta_excel
from tesoreria.serializers import FiltroLibroMesSerializer
from usuarios import roles
from usuarios.permissions import TieneRol

from . import documentos, exportacion, services
from .libro import libro_ventas as libro_ventas_servicio
from .models import Cliente, DocumentoVenta
from .serializers import (
    AnularSerializer,
    ClienteActualizarSerializer,
    ClienteCrearSerializer,
    ClienteSerializer,
    DocumentoVentaCrearSerializer,
    DocumentoVentaDetalleSerializer,
    DocumentoVentaSerializer,
    FiltroClientesSerializer,
    FiltroDocumentosSerializer,
)


class _EscrituraVentas:
    """Lectura: autenticados. Escritura: Contador o Tesorero."""

    def get_permissions(self):
        if self.action in ("list", "retrieve"):
            return [IsAuthenticated()]
        return [IsAuthenticated(), TieneRol(roles.CONTADOR, roles.TESORERO)()]


class ClienteViewSet(_EscrituraVentas, viewsets.GenericViewSet):
    serializer_class = ClienteSerializer
    queryset = Cliente.objects.select_related("creado_por", "modificado_por")

    def list(self, request):
        filtros = FiltroClientesSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        qs = services.consultar_clientes(**filtros.validated_data).select_related("creado_por", "modificado_por")
        pagina = self.paginate_queryset(qs)
        return self.get_paginated_response(ClienteSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return Response(ClienteSerializer(self.get_object()).data)

    def create(self, request):
        entrada = ClienteCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cliente = services.crear_cliente(usuario=request.user, request=request, **entrada.validated_data)
        return Response(ClienteSerializer(cliente).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        entrada = ClienteActualizarSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        cliente = services.actualizar_cliente(self.get_object(), usuario=request.user, datos=entrada.validated_data, request=request)
        return Response(ClienteSerializer(cliente).data)

    def destroy(self, request, pk=None):
        services.eliminar_cliente(self.get_object(), usuario=request.user, request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentoVentaViewSet(_EscrituraVentas, viewsets.GenericViewSet):
    serializer_class = DocumentoVentaSerializer
    queryset = DocumentoVenta.objects.select_related("cliente", "asiento", "cuenta_cobro")

    def _detalle(self, doc, codigo=status.HTTP_200_OK):
        doc = self.get_queryset().select_related("asiento_anulacion", "creado_por", "anulado_por").get(pk=doc.pk)
        return Response(DocumentoVentaDetalleSerializer(doc).data, status=codigo)

    def list(self, request):
        filtros = FiltroDocumentosSerializer(data=request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(documentos.consultar_documentos(**filtros.validated_data))
        return self.get_paginated_response(DocumentoVentaSerializer(pagina, many=True).data)

    def retrieve(self, request, pk=None):
        return self._detalle(self.get_object())

    def create(self, request):
        entrada = DocumentoVentaCrearSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        doc = documentos.registrar_documento_venta(usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(doc, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        entrada = AnularSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        doc = documentos.anular_documento_venta(self.get_object(), usuario=request.user, request=request, **entrada.validated_data)
        return self._detalle(doc)


def _filtro_mes(request):
    filtros = FiltroLibroMesSerializer(data=request.query_params)
    filtros.is_valid(raise_exception=True)
    return filtros.validated_data


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def libro_ventas(request):
    """Libro de ventas del mes (?anio=&mes=): contribuyentes (CCF) y consumidor final (facturas por día)."""
    return Response(libro_ventas_servicio(**_filtro_mes(request)))


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def libro_ventas_exportar(request):
    """Libro de ventas del mes en Excel (una hoja por libro)."""
    f = _filtro_mes(request)
    contenido = exportacion.libro_ventas_xlsx(usuario=request.user, **f)
    return respuesta_excel(f"libro_ventas_{f['anio']}_{f['mes']:02d}.xlsx", contenido)
