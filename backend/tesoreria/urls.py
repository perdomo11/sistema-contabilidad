from rest_framework.routers import SimpleRouter

from .views import ProveedorViewSet

router = SimpleRouter()
router.register("proveedores", ProveedorViewSet, basename="proveedor")

urlpatterns = router.urls
