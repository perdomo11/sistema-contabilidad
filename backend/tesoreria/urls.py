from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import CuentaPorPagarViewSet, EgresoProgramadoViewSet, ProveedorViewSet, proyeccion_egresos

router = SimpleRouter()
router.register("proveedores", ProveedorViewSet, basename="proveedor")
router.register("cuentas-por-pagar", CuentaPorPagarViewSet, basename="cuenta-por-pagar")
router.register("egresos-programados", EgresoProgramadoViewSet, basename="egreso-programado")

urlpatterns = [
    path("tesoreria/proyeccion-egresos/", proyeccion_egresos, name="proyeccion-egresos"),
    *router.urls,
]
