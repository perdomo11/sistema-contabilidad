from rest_framework.routers import SimpleRouter

from .views import CuentaPorPagarViewSet, ProveedorViewSet

router = SimpleRouter()
router.register("proveedores", ProveedorViewSet, basename="proveedor")
router.register("cuentas-por-pagar", CuentaPorPagarViewSet, basename="cuenta-por-pagar")

urlpatterns = router.urls
