from django.contrib import admin

from .models import PresupuestoInstitucional


@admin.register(PresupuestoInstitucional)
class PresupuestoInstitucionalAdmin(admin.ModelAdmin):
    """Solo consulta: los cambios pasan por la API (versiones y bitácora)."""

    list_display = ("anio", "monto", "version", "estado")
    list_filter = ("estado",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
