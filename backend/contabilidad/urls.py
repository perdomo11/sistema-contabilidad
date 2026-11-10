from rest_framework.routers import SimpleRouter

from .views import AsientoViewSet, CuentaViewSet, LibrosViewSet, PeriodoViewSet

router = SimpleRouter()
router.register("cuentas", CuentaViewSet, basename="cuenta")
router.register("periodos", PeriodoViewSet, basename="periodo")
router.register("asientos", AsientoViewSet, basename="asiento")
router.register("libros", LibrosViewSet, basename="libros")

urlpatterns = router.urls
