from django.contrib.auth.models import User
from rest_framework import serializers

from contabilidad.models import Cuenta
from tesoreria.models import Proveedor

from .models import CentroCosto, ReglaAsignacion

INMUTABLES = {"codigo", "padre", "nivel"}


class CentroCostoSerializer(serializers.ModelSerializer):
    padre_codigo = serializers.CharField(source="padre.codigo", read_only=True, default=None)
    tipo_display = serializers.CharField(source="get_tipo_display", read_only=True)
    clase_display = serializers.CharField(source="get_clase_display", read_only=True)
    responsable_nombre = serializers.SerializerMethodField()

    class Meta:
        model = CentroCosto
        fields = [
            "id", "codigo", "nombre", "padre", "padre_codigo", "nivel", "tipo", "tipo_display", "clase",
            "clase_display", "responsable", "responsable_nombre", "acepta_movimientos", "vigente_desde",
            "vigente_hasta", "creado_en", "modificado_en",
        ]
        read_only_fields = fields

    def get_responsable_nombre(self, obj):
        r = obj.responsable
        return (r.get_full_name() or r.username) if r else None


class CentroCrearSerializer(serializers.Serializer):
    codigo = serializers.CharField(max_length=20)
    nombre = serializers.CharField(max_length=150)
    padre = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False, allow_null=True)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices)
    responsable = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    acepta_movimientos = serializers.BooleanField(default=True)
    vigente_desde = serializers.DateField()
    vigente_hasta = serializers.DateField(required=False, allow_null=True)


class CentroActualizarSerializer(serializers.Serializer):
    nombre = serializers.CharField(max_length=150, required=False)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices, required=False)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices, required=False)
    responsable = serializers.PrimaryKeyRelatedField(queryset=User.objects.all(), required=False, allow_null=True)
    acepta_movimientos = serializers.BooleanField(required=False)
    vigente_desde = serializers.DateField(required=False)
    vigente_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        prohibidos = INMUTABLES & set(self.initial_data)
        if prohibidos:
            raise serializers.ValidationError(
                {c: "No se puede modificar; cierre la vigencia y cree una unidad nueva." for c in sorted(prohibidos)}
            )
        return attrs


class FiltroCentrosSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    tipo = serializers.ChoiceField(choices=CentroCosto.Tipo.choices, required=False)
    clase = serializers.ChoiceField(choices=CentroCosto.Clase.choices, required=False)
    acepta_movimientos = serializers.BooleanField(required=False, allow_null=True, default=None)
    vigente_en = serializers.DateField(required=False)


# =============================================================================
# Reglas de asignación (T2.2)
# =============================================================================


class ReglaAsignacionSerializer(serializers.ModelSerializer):
    cuenta_codigo = serializers.CharField(source="cuenta.codigo", read_only=True, default=None)
    cuenta_nombre = serializers.CharField(source="cuenta.nombre", read_only=True, default=None)
    proveedor_nombre = serializers.CharField(source="proveedor.nombre", read_only=True, default=None)
    proveedor_nit = serializers.CharField(source="proveedor.nit", read_only=True, default=None)
    centro_codigo = serializers.CharField(source="centro_costo.codigo", read_only=True)
    centro_nombre = serializers.CharField(source="centro_costo.nombre", read_only=True)
    criterio = serializers.CharField(read_only=True)
    aplicada = serializers.SerializerMethodField()

    class Meta:
        model = ReglaAsignacion
        fields = [
            "id", "cuenta", "cuenta_codigo", "cuenta_nombre", "proveedor", "proveedor_nombre", "proveedor_nit",
            "centro_costo", "centro_codigo", "centro_nombre", "criterio", "descripcion", "vigente_desde",
            "vigente_hasta", "aplicada", "creado_en", "modificado_en",
        ]
        read_only_fields = fields

    def get_aplicada(self, obj):
        """Si ya se aplicó a alguna línea (entonces no se puede eliminar)."""
        anotada = getattr(obj, "lineas_aplicadas", None)
        return anotada > 0 if anotada is not None else obj.lineas.exists()


class ReglaCrearSerializer(serializers.Serializer):
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False, allow_null=True, default=None)
    proveedor = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.all(), required=False, allow_null=True, default=None
    )
    centro_costo = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all())
    descripcion = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    vigente_desde = serializers.DateField()
    vigente_hasta = serializers.DateField(required=False, allow_null=True, default=None)


class ReglaActualizarSerializer(serializers.Serializer):
    descripcion = serializers.CharField(max_length=200, required=False, allow_blank=True)
    vigente_desde = serializers.DateField(required=False)
    vigente_hasta = serializers.DateField(required=False, allow_null=True)

    def validate(self, attrs):
        prohibidos = {"cuenta", "proveedor", "centro_costo"} & set(self.initial_data)
        if prohibidos:
            raise serializers.ValidationError(
                {c: "No se puede modificar; cierre la vigencia y cree otra regla." for c in sorted(prohibidos)}
            )
        return attrs


class FiltroReglasSerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.all(), required=False)
    proveedor = serializers.PrimaryKeyRelatedField(queryset=Proveedor.objects.all(), required=False)
    centro_costo = serializers.PrimaryKeyRelatedField(queryset=CentroCosto.objects.all(), required=False)
    vigente_en = serializers.DateField(required=False)


class ResolverReglasSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    proveedor = serializers.PrimaryKeyRelatedField(
        queryset=Proveedor.objects.all(), required=False, allow_null=True, default=None
    )
    cuentas = serializers.CharField()

    def validate_cuentas(self, valor):
        try:
            ids = {int(x) for x in valor.split(",") if x.strip()}
        except ValueError:
            raise serializers.ValidationError("Lista de ids separados por coma.")
        if not ids or len(ids) > 200:
            raise serializers.ValidationError("Indique entre 1 y 200 cuentas.")
        return list(Cuenta.objects.filter(pk__in=ids))
