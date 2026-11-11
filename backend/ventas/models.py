"""Ventas (T7.3): clientes y documentos de venta (CCF y factura de consumidor final).

Las reglas viven en `ventas/services.py` (clientes) y `ventas/documentos.py` (documentos de venta).
"""
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F, Q

_solo_digitos = RegexValidator(r"^[0-9][0-9-]*[0-9]$", "Admite dígitos y guiones.")


class Cliente(models.Model):
    """Cliente del banco. Un contribuyente inscrito en IVA (NIT y NRC) recibe CCF; un consumidor final, factura."""

    class Tipo(models.TextChoices):
        CONTRIBUYENTE = "CONTRIBUYENTE", "Contribuyente"
        CONSUMIDOR_FINAL = "CONSUMIDOR_FINAL", "Consumidor final"

    nombre = models.CharField(max_length=200)
    tipo = models.CharField(max_length=16, choices=Tipo.choices)
    # En Oracle un texto vacío es NULL: varios clientes sin NIT no chocan con la unicidad.
    nit = models.CharField("NIT", max_length=20, blank=True, null=True, unique=True, validators=[_solo_digitos])
    nrc = models.CharField("NRC", max_length=20, blank=True, validators=[RegexValidator(r"^[0-9][0-9-]*$", "El NRC admite dígitos y guiones.")])
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "cliente"
        verbose_name_plural = "clientes"
        ordering = ["nombre"]
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=["CONTRIBUYENTE", "CONSUMIDOR_FINAL"]), name="cliente_tipo_valido"),
            # Un contribuyente necesita NIT y NRC (en Oracle '' = NULL).
            models.CheckConstraint(
                condition=Q(tipo="CONSUMIDOR_FINAL") | Q(nit__isnull=False, nrc__isnull=False), name="cliente_contribuyente_nit_nrc"
            ),
        ]

    def __str__(self):
        return f"{self.nombre} ({self.nit})" if self.nit else self.nombre


class DocumentoVenta(models.Model):
    """CCF o factura de consumidor final emitido por el banco. Su registro genera un asiento contabilizado."""

    class TipoDocumento(models.TextChoices):
        CCF = "CCF", "Comprobante de crédito fiscal"
        FACTURA = "FACTURA", "Factura de consumidor final"

    class Estado(models.TextChoices):
        VIGENTE = "VIGENTE", "Vigente"
        ANULADO = "ANULADO", "Anulado"

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT, related_name="documentos")
    tipo_documento = models.CharField(max_length=8, choices=TipoDocumento.choices)
    numero_documento = models.CharField(max_length=40)
    fecha_emision = models.DateField()
    concepto = models.CharField(max_length=300)
    ventas_gravadas = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    ventas_exentas = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    iva_debito_fiscal = models.DecimalField("IVA débito fiscal", max_digits=18, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=2)
    cuenta_cobro = models.ForeignKey("contabilidad.Cuenta", on_delete=models.PROTECT, related_name="+")
    estado = models.CharField(max_length=8, choices=Estado.choices, default=Estado.VIGENTE)
    asiento = models.OneToOneField("contabilidad.Asiento", on_delete=models.PROTECT, related_name="documento_venta")
    asiento_anulacion = models.OneToOneField(
        "contabilidad.Asiento", null=True, blank=True, on_delete=models.PROTECT, related_name="anulacion_documento_venta"
    )
    motivo_anulacion = models.CharField(max_length=300, blank=True)
    anulado_por = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    anulado_en = models.DateTimeField(null=True, blank=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "documento de venta"
        verbose_name_plural = "documentos de venta"
        ordering = ["fecha_emision", "tipo_documento", "numero_documento"]
        indexes = [models.Index(fields=["tipo_documento", "fecha_emision"], name="doc_venta_tipo_fecha_idx")]
        constraints = [
            # Un número emitido no se reutiliza, aunque el documento se anule.
            models.UniqueConstraint(fields=["tipo_documento", "numero_documento"], name="doc_venta_numero_unico"),
            models.CheckConstraint(condition=Q(tipo_documento__in=["CCF", "FACTURA"]), name="doc_venta_tipo_valido"),
            models.CheckConstraint(condition=Q(estado__in=["VIGENTE", "ANULADO"]), name="doc_venta_estado_valido"),
            models.CheckConstraint(
                condition=Q(ventas_gravadas__gte=0, ventas_exentas__gte=0, iva_debito_fiscal__gte=0, total__gt=0),
                name="doc_venta_montos_validos",
            ),
            models.CheckConstraint(
                condition=Q(total=F("ventas_gravadas") + F("ventas_exentas") + F("iva_debito_fiscal")), name="doc_venta_total_cuadra"
            ),
            models.CheckConstraint(
                condition=Q(estado="VIGENTE") | Q(asiento_anulacion__isnull=False, anulado_por__isnull=False),
                name="doc_venta_anulacion_completa",
            ),
        ]

    def __str__(self):
        return f"{self.tipo_documento} {self.numero_documento} · {self.cliente.nombre}"
