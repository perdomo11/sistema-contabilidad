from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ClienteViewSet, DocumentoVentaViewSet, libro_ventas, libro_ventas_exportar

router = SimpleRouter()
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("ventas/documentos", DocumentoVentaViewSet, basename="documento-venta")

urlpatterns = [
    path("ventas/libro/", libro_ventas, name="libro-ventas"),
    path("ventas/libro/exportar/", libro_ventas_exportar, name="libro-ventas-exportar"),
    *router.urls,
]
