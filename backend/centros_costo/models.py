from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q


class TipoCentro(models.TextChoices):
    """Tipos de centro de responsabilidad (documento base, sección 2.4)."""

    COSTO = "COSTO", "Centro de costo"
    INGRESO = "INGRESO", "Centro de ingreso"
    UTILIDAD = "UTILIDAD", "Centro de utilidad"
    INVERSION = "INVERSION", "Centro de inversión"


class ClaseCentro(models.TextChoices):
    """Dimensión organizativa (documento base, sección 2.5)."""

    SUCURSAL = "SUCURSAL", "Sucursal"
    DEPARTAMENTO = "DEPARTAMENTO", "Departamento"
    PROYECTO = "PROYECTO", "Proyecto"
    AREA = "AREA", "Área"


class CentroCosto(models.Model):
    """Unidad de responsabilidad. Árbol de profundidad variable con vigencia temporal.

    Las reglas viven en `centros_costo/services.py`.
    """

    Tipo = TipoCentro
    Clase = ClaseCentro

    codigo = models.CharField(
        max_length=20,
        unique=True,
        validators=[
            RegexValidator(r"^[A-Z0-9][A-Z0-9-]*$", "El código admite mayúsculas, dígitos y guiones.")
        ],
    )
    nombre = models.CharField(max_length=150)
    padre = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="hijos")
    nivel = models.PositiveSmallIntegerField(editable=False)
    tipo = models.CharField(max_length=10, choices=TipoCentro.choices)
    clase = models.CharField(max_length=12, choices=ClaseCentro.choices)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="centros_a_cargo"
    )
    acepta_movimientos = models.BooleanField(
        default=True, help_text="Unidad de detalle (imputable). Las de agrupación consolidan a sus subunidades."
    )
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "centro de costo"
        verbose_name_plural = "centros de costo"
        ordering = ["codigo"]
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=TipoCentro.values), name="centro_tipo_valido"),
            models.CheckConstraint(condition=Q(clase__in=ClaseCentro.values), name="centro_clase_valida"),
            models.CheckConstraint(condition=Q(nivel__gte=1), name="centro_nivel_minimo"),
            models.CheckConstraint(
                condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=F("vigente_desde")),
                name="centro_vigencia_valida",
            ),
        ]

    def vigente_en(self, fecha):
        return self.vigente_desde <= fecha and (self.vigente_hasta is None or self.vigente_hasta >= fecha)

    def __str__(self):
        return f"{self.codigo} {self.nombre}"
