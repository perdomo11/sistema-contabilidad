from rest_framework.routers import SimpleRouter

from .views import PresupuestoViewSet

router = SimpleRouter()
router.register("presupuestos", PresupuestoViewSet, basename="presupuesto")

urlpatterns = router.urls
