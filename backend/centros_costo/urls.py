from rest_framework.routers import SimpleRouter

from .views import CentroCostoViewSet

router = SimpleRouter()
router.register("centros-costo", CentroCostoViewSet, basename="centro-costo")

urlpatterns = router.urls
