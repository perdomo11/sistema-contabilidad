from rest_framework.routers import SimpleRouter

from .views import CuentaViewSet, PeriodoViewSet

router = SimpleRouter()
router.register("cuentas", CuentaViewSet, basename="cuenta")
router.register("periodos", PeriodoViewSet, basename="periodo")

urlpatterns = router.urls
