from django.urls import path

from . import views

urlpatterns = [
    path("estado-resultados/", views.estado_resultados, name="estado-resultados"),
]
