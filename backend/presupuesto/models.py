"""Presupuesto top-down (Bloque 4). Las reglas viven en `presupuesto/services.py`."""
from django.conf import settings
from django.db import models
from django.db.models import Q

ANIO_MINIMO, ANIO_MAXIMO = 2000, 2100


class PresupuestoInstitucional(models.Model):
    """Monto institucional de egresos que fija la gerencia para un ejercicio (T4.1).

    `monto` y `version` reflejan siempre la última `VersionPresupuesto` (lo verifica un trigger Oracle).
    T4.2 lo distribuye a los departamentos.
    """

    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        APROBADO = "APROBADO", "Aprobado"
        CERRADO = "CERRADO", "Cerrado"

    anio = models.PositiveSmallIntegerField("ejercicio", unique=True)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    version = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.BORRADOR)
    descripcion = models.CharField(max_length=500, blank=True)

    referencia_aprobacion = models.CharField(max_length=200, blank=True)
    aprobado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    aprobado_en = models.DateTimeField(null=True, blank=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "presupuesto institucional"
        verbose_name_plural = "presupuestos institucionales"
        ordering = ["-anio"]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="presupuesto_monto_positivo"),
            models.CheckConstraint(condition=Q(version__gte=1), name="presupuesto_version_valida"),
            models.CheckConstraint(
                condition=Q(anio__gte=ANIO_MINIMO, anio__lte=ANIO_MAXIMO), name="presupuesto_anio_valido"
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["BORRADOR", "APROBADO", "CERRADO"]), name="presupuesto_estado_valido"
            ),
            # Aprobado o cerrado: debe constar quién lo aprobó y con qué documento.
            models.CheckConstraint(
                condition=Q(estado="BORRADOR")
                | (Q(aprobado_por__isnull=False, aprobado_en__isnull=False) & ~Q(referencia_aprobacion="")
                   & Q(referencia_aprobacion__isnull=False)),
                name="presupuesto_aprobacion_completa",
            ),
        ]

    def __str__(self):
        return f"Presupuesto {self.anio}"


class VersionPresupuesto(models.Model):
    """Historial inmutable de los cambios del monto institucional (trigger Oracle)."""

    class Tipo(models.TextChoices):
        INICIAL = "INICIAL", "Inicial"
        AJUSTE = "AJUSTE", "Ajuste en borrador"
        APROBACION = "APROBACION", "Aprobación"
        MODIFICACION = "MODIFICACION", "Modificación presupuestaria"

    presupuesto = models.ForeignKey(PresupuestoInstitucional, on_delete=models.PROTECT, related_name="versiones")
    numero = models.PositiveIntegerField()
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    monto_anterior = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    motivo = models.CharField(max_length=500, blank=True)
    referencia = models.CharField(max_length=200, blank=True)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    registrado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "versión de presupuesto"
        verbose_name_plural = "versiones de presupuesto"
        ordering = ["presupuesto", "numero"]
        constraints = [
            models.UniqueConstraint(fields=["presupuesto", "numero"], name="version_presupuesto_unica"),
            models.CheckConstraint(condition=Q(monto__gt=0), name="version_presupuesto_monto_positivo"),
            models.CheckConstraint(
                condition=Q(tipo__in=["INICIAL", "AJUSTE", "APROBACION", "MODIFICACION"]), name="version_presupuesto_tipo_valido"
            ),
            models.CheckConstraint(
                condition=(Q(tipo="INICIAL") & Q(monto_anterior__isnull=True))
                | (~Q(tipo="INICIAL") & Q(monto_anterior__isnull=False)),
                name="version_presupuesto_anterior",
            ),
        ]

    def __str__(self):
        return f"{self.presupuesto} v{self.numero}"
