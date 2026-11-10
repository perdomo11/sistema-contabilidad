from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q


class TipoCuenta(models.TextChoices):
    ACTIVO = "ACTIVO", "Activo"
    PASIVO = "PASIVO", "Pasivo"
    PATRIMONIO = "PATRIMONIO", "Patrimonio"
    INGRESO = "INGRESO", "Ingreso"
    GASTO = "GASTO", "Gasto"
    ORDEN = "ORDEN", "Cuentas de orden y contingentes"


class NaturalezaCuenta(models.TextChoices):
    DEUDORA = "DEUDORA", "Deudora"
    ACREEDORA = "ACREEDORA", "Acreedora"


# Tipos de balance: los únicos que pueden quedar exentos de centro de costo.
TIPOS_BALANCE = (TipoCuenta.ACTIVO, TipoCuenta.PASIVO, TipoCuenta.PATRIMONIO, TipoCuenta.ORDEN)


class Cuenta(models.Model):
    """Cuenta del catálogo contable. Árbol padre-hijo de profundidad variable.

    Las reglas de negocio (prefijo del código, herencia del tipo, cuentas de
    detalle, campos inmutables) viven en `contabilidad/services.py`.
    """

    Tipo = TipoCuenta
    Naturaleza = NaturalezaCuenta
    TIPOS_BALANCE = TIPOS_BALANCE

    codigo = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^\d+$", "El código solo puede contener dígitos.")],
    )
    nombre = models.CharField(max_length=200)
    padre = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="hijos"
    )
    nivel = models.PositiveSmallIntegerField(editable=False)
    tipo = models.CharField(max_length=12, choices=TipoCuenta.choices)
    naturaleza = models.CharField(max_length=10, choices=NaturalezaCuenta.choices)
    acepta_movimientos = models.BooleanField(
        default=True, help_text="Cuenta de detalle (imputable). Las de agrupación no reciben asientos."
    )
    exenta_centro_costo = models.BooleanField(
        default=False, help_text="Solo cuentas de balance: sus líneas de asiento no exigen centro de costo."
    )
    activa = models.BooleanField(default=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cuenta"
        verbose_name_plural = "catálogo de cuentas"
        ordering = ["codigo"]
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=TipoCuenta.values), name="cuenta_tipo_valido"),
            models.CheckConstraint(
                condition=Q(naturaleza__in=NaturalezaCuenta.values), name="cuenta_naturaleza_valida"
            ),
            models.CheckConstraint(condition=Q(nivel__gte=1), name="cuenta_nivel_minimo"),
            # Regla 3: solo las cuentas de balance pueden quedar exentas de centro de costo.
            models.CheckConstraint(
                condition=Q(exenta_centro_costo=False) | Q(tipo__in=[t.value for t in TIPOS_BALANCE]),
                name="cuenta_exencion_solo_balance",
            ),
        ]

    def __str__(self):
        return f"{self.codigo} {self.nombre}"


MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


class EstadoPeriodo(models.TextChoices):
    ABIERTO = "ABIERTO", "Abierto"
    CERRADO = "CERRADO", "Cerrado"


class PeriodoContable(models.Model):
    """Periodo mensual de un ejercicio (año calendario).

    Las reglas de apertura, cierre secuencial y reapertura viven en
    `contabilidad/services.py`.
    """

    Estado = EstadoPeriodo

    anio = models.PositiveSmallIntegerField()
    mes = models.PositiveSmallIntegerField()
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField()
    estado = models.CharField(max_length=10, choices=EstadoPeriodo.choices, default=EstadoPeriodo.ABIERTO)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    cerrado_en = models.DateTimeField(null=True, blank=True)

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "periodo contable"
        verbose_name_plural = "periodos contables"
        ordering = ["anio", "mes"]
        constraints = [
            models.UniqueConstraint(fields=["anio", "mes"], name="periodo_anio_mes_unico"),
            models.CheckConstraint(condition=Q(mes__gte=1, mes__lte=12), name="periodo_mes_valido"),
            models.CheckConstraint(condition=Q(anio__gte=2000, anio__lte=2100), name="periodo_anio_valido"),
            models.CheckConstraint(condition=Q(estado__in=EstadoPeriodo.values), name="periodo_estado_valido"),
            models.CheckConstraint(condition=Q(fecha_fin__gte=models.F("fecha_inicio")), name="periodo_fechas_validas"),
            models.CheckConstraint(
                condition=~Q(estado=EstadoPeriodo.CERRADO) | Q(cerrado_por__isnull=False, cerrado_en__isnull=False),
                name="periodo_cerrado_con_responsable",
            ),
        ]

    @property
    def nombre(self):
        return f"{MESES[self.mes - 1].capitalize()} {self.anio}"

    def __str__(self):
        return self.nombre
