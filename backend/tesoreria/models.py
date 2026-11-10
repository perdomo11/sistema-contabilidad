from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q


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


# =============================================================================
# T5.1: cuentas por pagar con vencimientos
# =============================================================================

class CuentaPorPagar(models.Model):
    """Documento por pagar a un proveedor. Su registro y sus pagos generan asientos contabilizados.

    Las reglas viven en `tesoreria/cuentas_por_pagar.py`.
    """

    class TipoDocumento(models.TextChoices):
        FACTURA = "FACTURA", "Factura"
        CCF = "CCF", "Comprobante de crédito fiscal"
        RECIBO = "RECIBO", "Recibo"
        OTRO = "OTRO", "Otro"

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        PARCIAL = "PARCIAL", "Pago parcial"
        PAGADA = "PAGADA", "Pagada"
        ANULADA = "ANULADA", "Anulada"

    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, related_name="cuentas_por_pagar")
    tipo_documento = models.CharField(max_length=10, choices=TipoDocumento.choices)
    numero_documento = models.CharField(max_length=40)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    # T5.2: política interna de programación; la proyección usa esta fecha si existe, si no el vencimiento.
    fecha_pago_programada = models.DateField(null=True, blank=True)
    concepto = models.CharField(max_length=300)
    monto_total = models.DecimalField(max_digits=18, decimal_places=2)
    saldo = models.DecimalField(max_digits=18, decimal_places=2)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    cuenta_pasivo = models.ForeignKey("contabilidad.Cuenta", on_delete=models.PROTECT, related_name="+")
    asiento = models.OneToOneField("contabilidad.Asiento", on_delete=models.PROTECT, related_name="cuenta_por_pagar")
    asiento_anulacion = models.OneToOneField(
        "contabilidad.Asiento", null=True, blank=True, on_delete=models.PROTECT, related_name="anulacion_cuenta_por_pagar"
    )
    motivo_anulacion = models.CharField(max_length=300, blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    anulado_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cuenta por pagar"
        verbose_name_plural = "cuentas por pagar"
        ordering = ["fecha_vencimiento", "id"]
        indexes = [models.Index(fields=["estado", "fecha_vencimiento"], name="cxp_estado_vence_idx")]
        constraints = [
            models.CheckConstraint(condition=Q(monto_total__gt=0), name="cxp_monto_positivo"),
            models.CheckConstraint(condition=Q(saldo__gte=0, saldo__lte=F("monto_total")), name="cxp_saldo_valido"),
            models.CheckConstraint(condition=Q(fecha_vencimiento__gte=F("fecha_emision")), name="cxp_vencimiento_valido"),
            models.CheckConstraint(
                condition=Q(fecha_pago_programada__isnull=True) | Q(fecha_pago_programada__gte=F("fecha_emision")),
                name="cxp_programada_valida",
            ),
            models.CheckConstraint(
                condition=Q(estado__in=["PENDIENTE", "PARCIAL", "PAGADA", "ANULADA"]), name="cxp_estado_valido"
            ),
            models.CheckConstraint(
                condition=Q(tipo_documento__in=["FACTURA", "CCF", "RECIBO", "OTRO"]), name="cxp_tipo_valido"
            ),
            # Estado coherente con el saldo.
            models.CheckConstraint(
                condition=Q(estado="ANULADA")
                | Q(estado="PAGADA", saldo=0)
                | Q(estado="PENDIENTE", saldo=F("monto_total"))
                | Q(estado="PARCIAL", saldo__gt=0, saldo__lt=F("monto_total")),
                name="cxp_estado_saldo",
            ),
            models.CheckConstraint(
                condition=~Q(estado="ANULADA") | Q(asiento_anulacion__isnull=False, anulado_por__isnull=False),
                name="cxp_anulacion_completa",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_documento_display()} {self.numero_documento} · {self.proveedor.nombre}"


class PagoCuentaPorPagar(models.Model):
    """Pago (total o parcial) de un documento por pagar; genera su asiento contabilizado."""

    class Estado(models.TextChoices):
        VIGENTE = "VIGENTE", "Vigente"
        ANULADO = "ANULADO", "Anulado"

    cuenta_por_pagar = models.ForeignKey(CuentaPorPagar, on_delete=models.PROTECT, related_name="pagos")
    fecha = models.DateField()
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    cuenta_banco = models.ForeignKey("contabilidad.Cuenta", on_delete=models.PROTECT, related_name="+")
    referencia = models.CharField(max_length=60, blank=True)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.VIGENTE)
    asiento = models.OneToOneField("contabilidad.Asiento", on_delete=models.PROTECT, related_name="pago_cxp")
    asiento_anulacion = models.OneToOneField(
        "contabilidad.Asiento", null=True, blank=True, on_delete=models.PROTECT, related_name="anulacion_pago_cxp"
    )
    motivo_anulacion = models.CharField(max_length=300, blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    anulado_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "pago de cuenta por pagar"
        verbose_name_plural = "pagos de cuentas por pagar"
        ordering = ["fecha", "id"]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="pago_cxp_monto_positivo"),
            models.CheckConstraint(condition=Q(estado__in=["VIGENTE", "ANULADO"]), name="pago_cxp_estado_valido"),
            models.CheckConstraint(
                condition=Q(estado="VIGENTE") | Q(asiento_anulacion__isnull=False, anulado_por__isnull=False),
                name="pago_cxp_anulacion_completa",
            ),
        ]


# =============================================================================
# T5.2: egresos programados (obligaciones de fecha conocida que no son facturas)
# =============================================================================

class EgresoProgramado(models.Model):
    """Planilla, impuestos, alquileres, cuotas de préstamos, inversiones… para la proyección de egresos.

    Dato de planificación (no contable): se edita y elimina, con bitácora.
    """

    class Categoria(models.TextChoices):
        PLANILLA = "PLANILLA", "Planilla"
        IMPUESTOS = "IMPUESTOS", "Impuestos"
        ALQUILERES = "ALQUILERES", "Alquileres"
        SERVICIOS = "SERVICIOS", "Servicios"
        PRESTAMOS = "PRESTAMOS", "Préstamos"
        INVERSION = "INVERSION", "Inversión"
        OTROS = "OTROS", "Otros"

    class Frecuencia(models.TextChoices):
        UNICA = "UNICA", "Única"
        MENSUAL = "MENSUAL", "Mensual"

    concepto = models.CharField(max_length=200)
    categoria = models.CharField(max_length=12, choices=Categoria.choices)
    monto = models.DecimalField(max_digits=18, decimal_places=2)
    frecuencia = models.CharField(max_length=8, choices=Frecuencia.choices)
    fecha_inicio = models.DateField()
    fecha_fin = models.DateField(null=True, blank=True)
    dia_mes = models.PositiveSmallIntegerField(null=True, blank=True)
    proveedor = models.ForeignKey(Proveedor, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "egreso programado"
        verbose_name_plural = "egresos programados"
        ordering = ["categoria", "concepto"]
        constraints = [
            models.CheckConstraint(condition=Q(monto__gt=0), name="egreso_prog_monto_positivo"),
            models.CheckConstraint(
                condition=Q(categoria__in=["PLANILLA", "IMPUESTOS", "ALQUILERES", "SERVICIOS", "PRESTAMOS", "INVERSION", "OTROS"]),
                name="egreso_prog_categoria_valida",
            ),
            # Única: sin día ni fin. Mensual: día 1-31.
            models.CheckConstraint(
                condition=Q(frecuencia="UNICA", dia_mes__isnull=True, fecha_fin__isnull=True)
                | Q(frecuencia="MENSUAL", dia_mes__gte=1, dia_mes__lte=31),
                name="egreso_prog_frecuencia_valida",
            ),
            models.CheckConstraint(
                condition=Q(fecha_fin__isnull=True) | Q(fecha_fin__gte=F("fecha_inicio")), name="egreso_prog_vigencia_valida"
            ),
        ]

    def __str__(self):
        return self.concepto
