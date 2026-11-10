from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    ClasificacionFlujoViewSet,
    ConfiguracionTesoreriaView,
    CuentaPorPagarViewSet,
    EgresoProgramadoViewSet,
    ProveedorViewSet,
    flujo_efectivo,
    flujo_proyectado,
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
    *router.urls,
]
