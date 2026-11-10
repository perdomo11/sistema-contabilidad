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


# =============================================================================
# Asientos contables (T1.3)
# =============================================================================


class TipoAsiento(models.TextChoices):
    DIARIO = "DIARIO", "Diario"
    REVERSION = "REVERSION", "Reversión"


class EstadoAsiento(models.TextChoices):
    BORRADOR = "BORRADOR", "Borrador"
    CONTABILIZADO = "CONTABILIZADO", "Contabilizado"


MONTO = {"max_digits": 18, "decimal_places": 2}


class Asiento(models.Model):
    """Asiento de diario. Inmutable una vez contabilizado (servicio + triggers de Oracle,
    migración 0004). Las reglas viven en `contabilidad/services.py`."""

    Tipo = TipoAsiento
    Estado = EstadoAsiento

    ejercicio = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Asignado al contabilizar.")
    numero = models.PositiveIntegerField(null=True, blank=True, help_text="Correlativo por ejercicio.")
    fecha = models.DateField()
    periodo = models.ForeignKey(PeriodoContable, on_delete=models.PROTECT, related_name="asientos")
    concepto = models.CharField(max_length=300)
    referencia = models.CharField(max_length=50, blank=True, help_text="Documento fuente (factura, cheque, etc.).")
    tipo = models.CharField(max_length=12, choices=TipoAsiento.choices, default=TipoAsiento.DIARIO)
    estado = models.CharField(max_length=15, choices=EstadoAsiento.choices, default=EstadoAsiento.BORRADOR)
    total_debe = models.DecimalField(**MONTO, default=0)
    total_haber = models.DecimalField(**MONTO, default=0)
    reversion_de = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversion",
        help_text="Asiento original que esta reversión anula.",
    )

    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    creado_en = models.DateTimeField(auto_now_add=True)
    modificado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    modificado_en = models.DateTimeField(auto_now=True)
    contabilizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    contabilizado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "asiento"
        verbose_name_plural = "asientos"
        ordering = ["-fecha", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["ejercicio", "numero"], name="asiento_numero_unico"),
            models.CheckConstraint(condition=Q(tipo__in=TipoAsiento.values), name="asiento_tipo_valido"),
            models.CheckConstraint(condition=Q(estado__in=EstadoAsiento.values), name="asiento_estado_valido"),
            models.CheckConstraint(condition=Q(total_debe__gte=0, total_haber__gte=0), name="asiento_totales_no_negativos"),
            # Partida doble: un asiento contabilizado tiene número, responsable y totales iguales.
            models.CheckConstraint(
                condition=~Q(estado=EstadoAsiento.CONTABILIZADO)
                | Q(
                    ejercicio__isnull=False,
                    numero__isnull=False,
                    contabilizado_por__isnull=False,
                    contabilizado_en__isnull=False,
                    total_debe=models.F("total_haber"),
                    total_debe__gt=0,
                ),
                name="asiento_contabilizado_cuadrado",
            ),
            models.CheckConstraint(
                condition=Q(reversion_de__isnull=True) | Q(tipo=TipoAsiento.REVERSION),
                name="asiento_reversion_tipo",
            ),
        ]

    @property
    def codigo(self):
        if self.numero is None:
            return f"Borrador {self.pk}"
        return f"{self.ejercicio}-{self.numero:06d}"

    def __str__(self):
        return f"{self.codigo} {self.concepto}"


class LineaAsiento(models.Model):
    asiento = models.ForeignKey(Asiento, on_delete=models.CASCADE, related_name="lineas")
    numero_linea = models.PositiveSmallIntegerField()
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="lineas")
    descripcion = models.CharField(max_length=200, blank=True)
    debe = models.DecimalField(**MONTO, default=0)
    haber = models.DecimalField(**MONTO, default=0)
    # Trazabilidad (regla 5): línea que origina esta (reversión; en T2.3, prorrateo).
    linea_origen = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="lineas_derivadas"
    )
    # Regla 3: obligatorio salvo cuentas exentas (validado en el servicio y en TRG_ASIENTO_REGLAS).
    centro_costo = models.ForeignKey(
        "centros_costo.CentroCosto", null=True, blank=True, on_delete=models.PROTECT, related_name="lineas"
    )

    class Meta:
        verbose_name = "línea de asiento"
        verbose_name_plural = "líneas de asiento"
        ordering = ["asiento", "numero_linea"]
        constraints = [
            models.UniqueConstraint(fields=["asiento", "numero_linea"], name="linea_numero_unico"),
            models.CheckConstraint(
                condition=(Q(debe__gt=0) & Q(haber=0)) | (Q(haber__gt=0) & Q(debe=0)),
                name="linea_cargo_o_abono",
            ),
        ]

    def __str__(self):
        return f"{self.asiento_id}/{self.numero_linea} {self.cuenta_id} D{self.debe} H{self.haber}"
