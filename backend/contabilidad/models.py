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
