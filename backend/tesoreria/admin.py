from django.contrib import admin

from .models import Proveedor


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    """Solo consulta: las altas y cambios pasan por la API (reglas y bitácora)."""

    list_display = ("nombre", "nit", "nrc", "activo")
    list_filter = ("activo",)
    search_fields = ("nombre", "nit", "nrc")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
