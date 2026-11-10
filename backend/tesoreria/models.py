from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models


class Proveedor(models.Model):
    """Catálogo básico de proveedores (T2.2). T5.1 agrega cuentas por pagar y vencimientos.

    Las reglas viven en `tesoreria/services.py`.
    """

    nit = models.CharField(
        "NIT",
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[0-9][0-9-]*[0-9]$", "El NIT admite dígitos y guiones.")],
    )
    nombre = models.CharField(max_length=200)
    nrc = models.CharField(
        "NRC",
        max_length=20,
        blank=True,
        validators=[RegexValidator(r"^[0-9][0-9-]*$", "El NRC admite dígitos y guiones.")],
    )
    activo = models.BooleanField(default=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "proveedor"
        verbose_name_plural = "proveedores"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.nit})"
