from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import (
    BaseProrrateoViewSet,
    CentroCostoViewSet,
    CopiarMedidasView,
    EjecucionProrrateoViewSet,
    MedidasView,
    ReglaAsignacionViewSet,
    ReglaProrrateoViewSet,
)

router = SimpleRouter()
router.register("centros-costo", CentroCostoViewSet, basename="centro-costo")
router.register("reglas-asignacion", ReglaAsignacionViewSet, basename="regla-asignacion")
router.register("prorrateo/bases", BaseProrrateoViewSet, basename="base-prorrateo")
router.register("prorrateo/reglas", ReglaProrrateoViewSet, basename="regla-prorrateo")
router.register("prorrateo/ejecuciones", EjecucionProrrateoViewSet, basename="ejecucion-prorrateo")

urlpatterns = [
    path("prorrateo/medidas/", MedidasView.as_view(), name="medidas-prorrateo"),
    path("prorrateo/medidas/copiar/", CopiarMedidasView.as_view(), name="copiar-medidas-prorrateo"),
    *router.urls,
]
