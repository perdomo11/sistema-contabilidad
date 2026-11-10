from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import User

from . import services
from .models import Bitacora


admin.site.unregister(User)


@admin.register(User)
class UsuarioAdmin(UserAdmin):
    """Admin de usuarios que deja constancia en la bitácora de altas, cambios y bajas."""

    def save_model(self, request, obj, form, change):
        # Estado anterior leído de la base antes de guardar (los roles se guardan en save_related).
        request._bitacora_antes = (
            services.instantanea_usuario(User.objects.get(pk=obj.pk)) if change else None
        )
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        usuario = form.instance
        antes = getattr(request, "_bitacora_antes", None)
        despues = services.instantanea_usuario(usuario)
        if change and antes == despues:
            return
        services.registrar_evento(
            Bitacora.Accion.MODIFICAR if change else Bitacora.Accion.CREAR,
            usuario=request.user,
            entidad="usuario",
            objeto_id=usuario.pk,
            descripcion=f"{'Modificación' if change else 'Alta'} del usuario {usuario.username}",
            valor_anterior=antes,
            valor_nuevo=despues,
            request=request,
        )

    def delete_model(self, request, obj):
        antes = services.instantanea_usuario(obj)
        pk = obj.pk
        super().delete_model(request, obj)
        services.registrar_evento(
            Bitacora.Accion.ELIMINAR,
            usuario=request.user,
            entidad="usuario",
            objeto_id=pk,
            descripcion=f"Baja del usuario {antes['username']}",
            valor_anterior=antes,
            request=request,
        )


@admin.register(Bitacora)
class BitacoraAdmin(admin.ModelAdmin):
    list_display = ("fecha", "nombre_usuario", "accion", "entidad", "objeto_id", "descripcion", "ip")
    list_filter = ("accion", "entidad")
    search_fields = ("nombre_usuario", "descripcion", "objeto_id")
    date_hierarchy = "fecha"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
