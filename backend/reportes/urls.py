from django.urls import path

from . import views

urlpatterns = [
    path("estado-resultados/", views.estado_resultados, name="estado-resultados"),
    path("enfoque-contribucion/", views.enfoque_contribucion, name="enfoque-contribucion"),
    path("indicadores/", views.indicadores_rentabilidad, name="indicadores-rentabilidad"),
]
