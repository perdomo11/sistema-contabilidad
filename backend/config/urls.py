from django.contrib import admin
from django.urls import include, path

from .health import health

admin.site.site_header = "Sistema Contable: administración"
admin.site.site_title = "Sistema Contable"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", health, name="health"),
    path("api/", include("usuarios.urls")),
    path("api/", include("contabilidad.urls")),
    path("api/", include("centros_costo.urls")),
    path("api/", include("tesoreria.urls")),
    path("api/reportes/", include("reportes.urls")),
]
