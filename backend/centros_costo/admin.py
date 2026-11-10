from django.contrib import admin

from .models import CentroCosto


@admin.register(CentroCosto)
class CentroCostoAdmin(admin.ModelAdmin):
    """Solo consulta: las altas y cambios pasan por la API (reglas y bitácora)."""

    list_display = ("codigo", "nombre", "nivel", "tipo", "clase", "responsable", "acepta_movimientos", "vigente_desde", "vigente_hasta")
    list_filter = ("tipo", "clase", "acepta_movimientos")
    search_fields = ("codigo", "nombre")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
