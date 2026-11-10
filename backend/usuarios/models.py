from django.conf import settings
from django.db import models


class BitacoraInmutableError(Exception):
    """Se intentó modificar o borrar un registro de la bitácora de auditoría."""


class BitacoraQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise BitacoraInmutableError("La bitácora de auditoría no se puede modificar.")

    def delete(self):
        raise BitacoraInmutableError("La bitácora de auditoría no se puede borrar.")


class Bitacora(models.Model):
    """Registro inmutable de acciones sensibles: quién, qué, cuándo y valores anterior/nuevo.

    La inmutabilidad se garantiza en el modelo (save/delete/queryset) y en la
    base de datos con el trigger TRG_BITACORA_INMUTABLE (migración 0003).
    """

    class Accion(models.TextChoices):
        LOGIN = "LOGIN", "Inicio de sesión"
        LOGIN_FALLIDO = "LOGIN_FALLIDO", "Inicio de sesión fallido"
        LOGOUT = "LOGOUT", "Cierre de sesión"
        CREAR = "CREAR", "Creación"
        MODIFICAR = "MODIFICAR", "Modificación"
        ELIMINAR = "ELIMINAR", "Eliminación"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="eventos_bitacora",
        help_text="Usuario que realizó la acción (vacío si no se autenticó).",
    )
    nombre_usuario = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nombre de usuario en el momento del evento (o el intentado en un login fallido).",
    )
    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    accion = models.CharField(max_length=20, choices=Accion.choices, db_index=True)
    entidad = models.CharField(max_length=100, blank=True, help_text="Modelo o recurso afectado.")
    objeto_id = models.CharField(max_length=64, blank=True)
    descripcion = models.CharField(max_length=500, blank=True)
    valor_anterior = models.JSONField(null=True, blank=True)
    valor_nuevo = models.JSONField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    objects = BitacoraQuerySet.as_manager()

    class Meta:
        verbose_name = "registro de bitácora"
        verbose_name_plural = "bitácora de auditoría"
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return f"{self.fecha:%Y-%m-%d %H:%M:%S} {self.nombre_usuario or '-'} {self.accion}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise BitacoraInmutableError("La bitácora de auditoría no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise BitacoraInmutableError("La bitácora de auditoría no se puede borrar.")
