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


class ReglaAsignacion(models.Model):
    """Asignación automática de centro de costo por cuenta y/o proveedor (T2.2).

    Se aplica a las líneas que no traen centro (la asignación directa prevalece).
    Resolución y validaciones en `centros_costo/services.py`.
    """

    cuenta = models.ForeignKey(
        "contabilidad.Cuenta", null=True, blank=True, on_delete=models.PROTECT, related_name="reglas_asignacion",
        help_text="Si es de agrupación, la regla aplica a todas sus subcuentas.",
    )
    proveedor = models.ForeignKey(
        "tesoreria.Proveedor", null=True, blank=True, on_delete=models.PROTECT, related_name="reglas_asignacion"
    )
    centro_costo = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, related_name="reglas_asignacion")
    descripcion = models.CharField(max_length=200, blank=True)
    vigente_desde = models.DateField()
    vigente_hasta = models.DateField(null=True, blank=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "regla de asignación"
        verbose_name_plural = "reglas de asignación"
        ordering = ["-vigente_desde", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(cuenta__isnull=False) | Q(proveedor__isnull=False), name="regla_cuenta_o_proveedor"
            ),
            models.CheckConstraint(
                condition=Q(vigente_hasta__isnull=True) | Q(vigente_hasta__gte=F("vigente_desde")),
                name="regla_vigencia_valida",
            ),
        ]

    def vigente_en(self, fecha):
        return self.vigente_desde <= fecha and (self.vigente_hasta is None or self.vigente_hasta >= fecha)

    @property
    def criterio(self):
        partes = []
        if self.proveedor_id:
            partes.append(f"proveedor {self.proveedor.nombre}")
        if self.cuenta_id:
            partes.append(f"cuenta {self.cuenta.codigo}")
        return " + ".join(partes)

    def __str__(self):
        return f"{self.criterio} → {self.centro_costo.codigo}"


# =============================================================================
# Prorrateo (T2.3). Reglas y cálculo en `centros_costo/prorrateo.py`.
# =============================================================================

MEDIDA = {"max_digits": 18, "decimal_places": 4}


class BaseProrrateo(models.Model):
    """Base de distribución configurable (m², personal ocupado, transacciones…)."""

    codigo = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[A-Z0-9_]+$", "El código admite mayúsculas, dígitos y guion bajo.")],
    )
    nombre = models.CharField(max_length=100)
    unidad = models.CharField(max_length=30)
    activa = models.BooleanField(default=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "base de prorrateo"
        verbose_name_plural = "bases de prorrateo"
        ordering = ["codigo"]

    def __str__(self):
        return f"{self.nombre} ({self.unidad})"


class MedidaBase(models.Model):
    """Valor de una base para un centro en un periodo contable."""

    base = models.ForeignKey(BaseProrrateo, on_delete=models.PROTECT, related_name="medidas")
    centro_costo = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, related_name="medidas_base")
    periodo = models.ForeignKey("contabilidad.PeriodoContable", on_delete=models.PROTECT, related_name="medidas_base")
    valor = models.DecimalField(**MEDIDA)

    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "medida de base"
        verbose_name_plural = "medidas de base"
        constraints = [
            models.UniqueConstraint(fields=["base", "centro_costo", "periodo"], name="medida_base_unica"),
            models.CheckConstraint(condition=Q(valor__gte=0), name="medida_valor_no_negativo"),
        ]

    def __str__(self):
        return f"{self.base.codigo} {self.centro_costo.codigo} {self.periodo_id}: {self.valor}"


class ReglaProrrateo(models.Model):
    """Distribuye los costos de un centro de servicio (origen) hacia sus centros receptores."""

    nombre = models.CharField(max_length=150)
    orden = models.PositiveSmallIntegerField(
        default=1, help_text="Método escalonado: se ejecutan de menor a mayor orden."
    )
    centro_origen = models.ForeignKey(CentroCosto, on_delete=models.PROTECT, related_name="prorrateos_origen")
    cuentas = models.ManyToManyField(
        "contabilidad.Cuenta", related_name="reglas_prorrateo", help_text="Una cuenta de agrupación incluye sus subcuentas."
    )
    base = models.ForeignKey(BaseProrrateo, on_delete=models.PROTECT, related_name="reglas")
    destinos = models.ManyToManyField(CentroCosto, related_name="prorrateos_destino")
    activa = models.BooleanField(default=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "regla de prorrateo"
        verbose_name_plural = "reglas de prorrateo"
        ordering = ["orden", "id"]

    def __str__(self):
        return self.nombre


class EstadoEjecucion(models.TextChoices):
    EJECUTADA = "EJECUTADA", "Ejecutada"
    ANULADA = "ANULADA", "Anulada"


class EjecucionProrrateo(models.Model):
    """Resultado de aplicar una regla en un periodo: el asiento generado y los datos usados."""

    Estado = EstadoEjecucion

    regla = models.ForeignKey(ReglaProrrateo, on_delete=models.PROTECT, related_name="ejecuciones")
    periodo = models.ForeignKey("contabilidad.PeriodoContable", on_delete=models.PROTECT, related_name="prorrateos")
    asiento = models.OneToOneField(
        "contabilidad.Asiento", on_delete=models.PROTECT, related_name="ejecucion_prorrateo"
    )
    estado = models.CharField(max_length=10, choices=EstadoEjecucion.choices, default=EstadoEjecucion.EJECUTADA)
    total_distribuido = models.DecimalField(max_digits=18, decimal_places=2)
    detalle = models.JSONField(help_text="Base, medidas y porcentajes usados en el cálculo.")
    ejecutado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    ejecutado_en = models.DateTimeField(auto_now_add=True)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=250, blank=True)

    class Meta:
        verbose_name = "ejecución de prorrateo"
        verbose_name_plural = "ejecuciones de prorrateo"
        ordering = ["-ejecutado_en", "-id"]
        constraints = [
            models.CheckConstraint(condition=Q(estado__in=EstadoEjecucion.values), name="ejecucion_estado_valido"),
            models.CheckConstraint(
                condition=Q(estado=EstadoEjecucion.EJECUTADA) | Q(anulado_por__isnull=False, anulado_en__isnull=False),
                name="ejecucion_anulada_con_responsable",
            ),
        ]

    def __str__(self):
        return f"{self.regla} {self.periodo_id} {self.estado}"
