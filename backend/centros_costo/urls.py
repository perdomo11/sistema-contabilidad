from rest_framework.routers import SimpleRouter

from .views import CentroCostoViewSet, ReglaAsignacionViewSet

router = SimpleRouter()
router.register("centros-costo", CentroCostoViewSet, basename="centro-costo")
router.register("reglas-asignacion", ReglaAsignacionViewSet, basename="regla-asignacion")

urlpatterns = router.urls
