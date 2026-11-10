"""Pruebas de T4.2: distribución del presupuesto institucional a departamentos."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from centros_costo import services as centros
from centros_costo.models import CentroCosto
from contabilidad import services as contabilidad
from contabilidad.models import Cuenta
from usuarios import roles
from usuarios.models import Bitacora

from . import distribucion, services
from .models import (
    AsignacionPresupuesto,
    CambioDistribucion,
    DetallePresupuesto,
    PresupuestoInstitucional,
    VersionPresupuesto,
)
from .tests import crear_usuario

T, C = CentroCosto.Tipo, CentroCosto.Clase
D = Decimal


def meses(**valores):
    """meses(ene="100", dic="50") → lista de 12 textos."""
    nombres = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return [valores.get(n, "0") for n in nombres]


class BaseDistribucion(TestCase):
    def setUp(self):
        self.contador = c = crear_usuario("contador", roles.CONTADOR)
        gastos = contabilidad.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO, acepta_movimientos=False)
        self.g52 = contabilidad.crear_cuenta(usuario=c, codigo="52", nombre="Operación", padre=gastos, acepta_movimientos=False)
        self.energia = contabilidad.crear_cuenta(usuario=c, codigo="5201", nombre="Energía", padre=self.g52)
        self.papeleria = contabilidad.crear_cuenta(usuario=c, codigo="5202", nombre="Papelería", padre=self.g52)
        ingresos = contabilidad.crear_cuenta(usuario=c, codigo="4", nombre="Ingresos", tipo=Cuenta.Tipo.INGRESO, acepta_movimientos=False)
        self.intereses = contabilidad.crear_cuenta(usuario=c, codigo="4101", nombre="Intereses", padre=ingresos)

        self.matriz = self.centro("01", "Casa matriz", acepta_movimientos=False)
        self.ti = self.centro("01-01", "Tecnología", padre=self.matriz)
        self.rrhh = self.centro("01-02", "Recursos humanos", padre=self.matriz)
        self.p = services.crear_presupuesto(usuario=c, anio=2027, monto="100000.00")

    def centro(self, codigo, nombre, desde=date(2026, 1, 1), **kwargs):
        return centros.crear_centro(
            usuario=self.contador, codigo=codigo, nombre=nombre, tipo=T.COSTO, clase=C.DEPARTAMENTO, vigente_desde=desde, **kwargs
        )

    def asignar(self, centro, monto, **kwargs):
        return distribucion.asignar_departamento(self.p, usuario=self.contador, centro=centro, monto=D(monto), **kwargs)

    def detallar(self, centro, filas, **kwargs):
        filas = [{"cuenta": cuenta, "meses": m} for cuenta, m in filas]
        return distribucion.guardar_detalle(self.p, usuario=self.contador, centro=centro, filas=filas, **kwargs)


class AsignacionTests(BaseDistribucion):
    def test_saldo_sin_distribuir(self):
        self.asignar(self.ti, "60000")
        r = self.asignar(self.rrhh, "25000.50")
        self.assertEqual((r["distribuido"], r["sin_distribuir"], r["porcentaje_distribuido"]), ("85000.50", "14999.50", "85.00"))
        self.assertEqual([(d["centro"]["codigo"], d["asignado"], d["porcentaje"]) for d in r["departamentos"]],
                         [("01-01", "60000.00", "60.00"), ("01-02", "25000.50", "25.00")])

    def test_no_excede_el_monto_institucional(self):
        self.asignar(self.ti, "60000")
        with self.assertRaises(ValidationError) as e:
            self.asignar(self.rrhh, "40000.01")
        self.assertIn("40,000.00", e.exception.message_dict["monto"][0])  # informa el disponible
        # Cambiar la propia asignación descuenta su monto anterior del distribuido.
        r = self.asignar(self.ti, "100000")
        self.assertEqual(r["sin_distribuir"], "0.00")

    def test_centro_de_agrupacion_o_no_vigente(self):
        with self.assertRaises(ValidationError):
            self.asignar(self.matriz, "100")
        viejo = self.centro("02", "Cerrado", desde=date(2020, 1, 1), vigente_hasta=date(2026, 12, 31))
        with self.assertRaises(ValidationError):
            self.asignar(viejo, "100")

    def test_quitar_asignacion(self):
        self.asignar(self.ti, "1000")
        r = self.asignar(self.ti, "0")
        self.assertEqual(r["departamentos"], [])
        self.assertFalse(AsignacionPresupuesto.objects.exists())
        with self.assertRaises(ValidationError):
            self.asignar(self.ti, "0")  # ya no tiene asignación

    def test_monto_institucional_no_baja_de_lo_distribuido(self):
        self.asignar(self.ti, "80000")
        with self.assertRaises(ValidationError):
            services.cambiar_monto(self.p, usuario=self.contador, monto="79999.99")
        p = services.cambiar_monto(self.p, usuario=self.contador, monto="80000")
        self.assertEqual(p.monto, D("80000.00"))

    def test_presupuesto_cerrado(self):
        self.asignar(self.ti, "1000")
        p = services.aprobar_presupuesto(self.p, usuario=self.contador, referencia="Acta")
        self.asignar(self.rrhh, "500")  # aprobado: se puede distribuir
        services.cerrar_presupuesto(p, usuario=self.contador)
        with self.assertRaises(ValidationError):
            self.asignar(self.ti, "2000")
        with self.assertRaises(ValidationError):
            self.detallar(self.ti, [(self.energia, meses(ene="10"))])


class DetalleTests(BaseDistribucion):
    def setUp(self):
        super().setUp()
        self.asignar(self.ti, "12000")

    def test_detalle_por_cuenta_y_mes(self):
        r = self.detallar(self.ti, [(self.energia, ["800"] * 12), (self.papeleria, meses(mar="500", sep="500"))])
        self.assertEqual((r["asignado"], r["detallado"], r["sin_detallar"]), ("12000.00", "10600.00", "1400.00"))
        self.assertEqual([f["cuenta"]["codigo"] for f in r["filas"]], ["5201", "5202"])
        self.assertEqual(r["filas"][1]["meses"][2], "500.00")
        self.assertEqual(r["por_mes"][2], "1300.00")
        self.assertEqual(DetallePresupuesto.objects.count(), 14)  # los ceros no se guardan
        resumen = distribucion.resumen_distribucion(self.p)
        self.assertEqual((resumen["departamentos"][0]["detallado"], resumen["departamentos"][0]["sin_detallar"]), ("10600.00", "1400.00"))

    def test_detalle_no_excede_lo_asignado(self):
        with self.assertRaises(ValidationError):
            self.detallar(self.ti, [(self.energia, ["1000.01"] * 12)])
        self.detallar(self.ti, [(self.energia, ["1000"] * 12)])
        with self.assertRaises(ValidationError):
            self.asignar(self.ti, "11999.99")  # no baja de lo detallado
        with self.assertRaises(ValidationError):
            self.asignar(self.ti, "0")

    def test_validaciones_de_cuentas_y_montos(self):
        casos = [
            [(self.intereses, meses(ene="1"))],  # ingreso
            [(self.g52, meses(ene="1"))],  # agrupación
            [(self.energia, meses(ene="-1"))],
            [(self.energia, meses(ene="1.234"))],
            [(self.energia, meses(ene="abc"))],
            [(self.energia, meses(ene="1")), (self.energia, meses(feb="1"))],  # repetida
        ]
        for filas in casos:
            with self.subTest(filas=filas), self.assertRaises(ValidationError):
                self.detallar(self.ti, filas)
        with self.assertRaises(ValidationError):
            self.detallar(self.rrhh, [(self.energia, meses(ene="1"))])  # sin asignación

    def test_mes_fuera_de_vigencia_del_centro(self):
        nuevo = self.centro("01-03", "Nuevo", padre=self.matriz, desde=date(2027, 7, 1))
        self.asignar(nuevo, "1000")
        with self.assertRaises(ValidationError) as e:
            self.detallar(nuevo, [(self.energia, meses(jun="100"))])
        self.assertIn("mes 6", e.exception.message_dict["filas"][0])
        r = self.detallar(nuevo, [(self.energia, meses(jul="100"))])
        self.assertEqual(r["meses_vigentes"][:7], [False] * 6 + [True])

    def test_historial_y_bitacora(self):
        self.detallar(self.ti, [(self.energia, meses(ene="100", feb="100"))])
        self.detallar(self.ti, [(self.energia, meses(ene="150"))], motivo="Ajuste tarifas")
        cambios = list(CambioDistribucion.objects.filter(cuenta=self.energia).order_by("id").values_list("mes", "monto_anterior", "monto_nuevo", "motivo"))
        self.assertEqual(cambios, [
            (1, D("0.00"), D("100.00"), ""), (2, D("0.00"), D("100.00"), ""),
            (1, D("100.00"), D("150.00"), "Ajuste tarifas"), (2, D("100.00"), D("0.00"), "Ajuste tarifas"),
        ])
        # Asignación inicial (sin cuenta) también queda.
        self.assertTrue(CambioDistribucion.objects.filter(cuenta__isnull=True, monto_nuevo=D("12000.00")).exists())
        evento = Bitacora.objects.filter(entidad="distribucion_presupuesto").latest("id")
        self.assertEqual(evento.valor_anterior["por_cuenta"], {"5201": "200.00"})
        self.assertEqual(evento.valor_nuevo["por_cuenta"], {"5201": "150.00"})
        # Guardar sin cambios no registra nada.
        n = CambioDistribucion.objects.count()
        self.detallar(self.ti, [(self.energia, meses(ene="150"))])
        self.assertEqual(CambioDistribucion.objects.count(), n)

    def test_reemplazo_que_redistribuye_al_tope(self):
        """Bajar una celda y subir otra hasta el tope no choca con los triggers de Oracle."""
        self.detallar(self.ti, [(self.energia, meses(ene="12000"))])
        r = self.detallar(self.ti, [(self.energia, meses(ene="6000")), (self.papeleria, meses(feb="6000"))])
        self.assertEqual(r["sin_detallar"], "0.00")


class DistribucionBaseDeDatosTests(BaseDistribucion):
    """Topes y reglas garantizados por Oracle aunque se salte el servicio."""

    def test_tope_institucional_en_bd(self):
        self.asignar(self.ti, "100000")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AsignacionPresupuesto.objects.create(
                presupuesto=self.p, centro_costo=self.rrhh, monto=D("1"), creado_por=self.contador, modificado_por=self.contador
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            AsignacionPresupuesto.objects.filter(centro_costo=self.ti).update(monto=D("100000.01"))

    def test_tope_departamento_en_bd(self):
        self.asignar(self.ti, "100")
        a = AsignacionPresupuesto.objects.get()
        with self.assertRaises(DatabaseError), transaction.atomic():
            DetallePresupuesto.objects.create(asignacion=a, cuenta=self.energia, mes=1, monto=D("100.01"))
        self.detallar(self.ti, [(self.energia, meses(ene="100"))])
        with self.assertRaises(DatabaseError), transaction.atomic():
            AsignacionPresupuesto.objects.filter(pk=a.pk).update(monto=D("99"))

    def test_monto_institucional_en_bd(self):
        self.asignar(self.ti, "100000")
        # Versión registrada correctamente, pero el monto queda por debajo de lo distribuido.
        with self.assertRaises(DatabaseError), transaction.atomic():
            VersionPresupuesto.objects.create(
                presupuesto=self.p, numero=2, tipo="AJUSTE", monto=D("50000"), monto_anterior=self.p.monto, registrado_por=self.contador
            )
            PresupuestoInstitucional.objects.filter(pk=self.p.pk).update(monto=D("50000"), version=2)

    def test_cerrado_e_historial_inmutable_en_bd(self):
        self.asignar(self.ti, "100")
        with self.assertRaises(DatabaseError), transaction.atomic():
            CambioDistribucion.objects.update(motivo="x")
        p = services.cerrar_presupuesto(services.aprobar_presupuesto(self.p, usuario=self.contador, referencia="A"), usuario=self.contador)
        self.assertEqual(p.estado, "CERRADO")
        with self.assertRaises(DatabaseError), transaction.atomic():
            AsignacionPresupuesto.objects.update(monto=D("50"))


class DistribucionApiTests(BaseDistribucion):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.url = f"/api/presupuestos/{self.p.pk}/distribucion/"

    def test_flujo_contador(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post(self.url, {"centro": self.ti.pk, "monto": "5000.00", "motivo": "Plan TI"}, format="json")
        self.assertEqual((resp.status_code, resp.data["sin_distribuir"]), (200, "95000.00"), resp.data)
        resp = self.client.post(self.url, {"centro": self.rrhh.pk, "monto": "96000"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("monto", resp.data)
        url_ti = f"{self.url}{self.ti.pk}/"
        cuerpo = {"filas": [{"cuenta": self.energia.pk, "meses": ["400"] * 12}], "motivo": ""}
        resp = self.client.put(url_ti, cuerpo, format="json")
        self.assertEqual((resp.status_code, resp.data["sin_detallar"]), (200, "200.00"), resp.data)
        resp = self.client.put(url_ti, {"filas": [{"cuenta": self.energia.pk, "meses": ["x"] + ["0"] * 11}]}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("filas", resp.data)
        self.assertEqual(self.client.get(url_ti).data["detallado"], "4800.00")
        historial = self.client.get(f"/api/presupuestos/{self.p.pk}/historial-distribucion/", {"centro": self.ti.pk}).data
        self.assertEqual(len(historial), 13)  # asignación + 12 meses

    def test_otros_roles_solo_consultan(self):
        self.asignar(self.ti, "100")
        self.client.force_authenticate(crear_usuario("jefe", roles.JEFE_AREA))
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(f"{self.url}{self.ti.pk}/").status_code, 200)
        self.assertEqual(self.client.post(self.url, {"centro": self.rrhh.pk, "monto": "1"}, format="json").status_code, 403)
        self.assertEqual(self.client.put(f"{self.url}{self.ti.pk}/", {"filas": []}, format="json").status_code, 403)
