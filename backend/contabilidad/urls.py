from rest_framework.routers import SimpleRouter

from .views import CuentaViewSet

router = SimpleRouter()
router.register("cuentas", CuentaViewSet, basename="cuenta")

urlpatterns = router.urls
