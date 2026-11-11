from django.contrib import admin

from .models import Cliente, DocumentoVenta


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ("nombre", "tipo", "nit", "nrc", "activo")
    list_filter = ("tipo", "activo")
    search_fields = ("nombre", "nit", "nrc")


@admin.register(DocumentoVenta)
class DocumentoVentaAdmin(admin.ModelAdmin):
    """Solo consulta: los documentos se emiten y se anulan desde la aplicación."""

    list_display = ("tipo_documento", "numero_documento", "fecha_emision", "cliente", "total", "estado")
    list_filter = ("tipo_documento", "estado")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
