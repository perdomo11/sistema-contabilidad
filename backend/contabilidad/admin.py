from django.contrib import admin

from .models import Cuenta, PeriodoContable


@admin.register(Cuenta)
class CuentaAdmin(admin.ModelAdmin):
    """Solo consulta: las altas y cambios pasan por la API para aplicar las reglas y la bitácora."""

    list_display = ("codigo", "nombre", "nivel", "tipo", "naturaleza", "acepta_movimientos", "exenta_centro_costo", "activa")
    list_filter = ("tipo", "activa", "acepta_movimientos", "exenta_centro_costo")
    search_fields = ("codigo", "nombre")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PeriodoContable)
class PeriodoContableAdmin(admin.ModelAdmin):
    """Solo consulta: la apertura y el cierre pasan por la API (reglas y bitácora)."""

    list_display = ("anio", "mes", "fecha_inicio", "fecha_fin", "estado", "cerrado_por", "cerrado_en")
    list_filter = ("anio", "estado")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
