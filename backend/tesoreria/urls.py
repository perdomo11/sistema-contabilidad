from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ClasificacionFlujoViewSet,
    ConfiguracionTesoreriaView,
    CuentaPorPagarViewSet,
    EgresoProgramadoViewSet,
    ProveedorViewSet,
    dashboard,
    flujo_efectivo,
    flujo_proyectado,
    libro_compras,
    libro_compras_exportar,
    proyeccion_egresos,
)

router = SimpleRouter()
router.register("proveedores", ProveedorViewSet, basename="proveedor")
router.register("cuentas-por-pagar", CuentaPorPagarViewSet, basename="cuenta-por-pagar")
router.register("egresos-programados", EgresoProgramadoViewSet, basename="egreso-programado")
router.register("tesoreria/clasificacion-flujo", ClasificacionFlujoViewSet, basename="clasificacion-flujo")

urlpatterns = [
    path("tesoreria/proyeccion-egresos/", proyeccion_egresos, name="proyeccion-egresos"),
    path("tesoreria/flujo-efectivo/", flujo_efectivo, name="flujo-efectivo"),
    path("tesoreria/flujo-proyectado/", flujo_proyectado, name="flujo-proyectado"),
    path("tesoreria/configuracion/", ConfiguracionTesoreriaView.as_view(), name="configuracion-tesoreria"),
    path("tesoreria/dashboard/", dashboard, name="dashboard-tesoreria"),
    path("tesoreria/libro-compras/", libro_compras, name="libro-compras"),
    path("tesoreria/libro-compras/exportar/", libro_compras_exportar, name="libro-compras-exportar"),
    *router.urls,
]
