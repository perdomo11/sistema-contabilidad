"""Pruebas de T4.3: ejecución vs. presupuesto y alertas de desviación."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from centros_costo import prorrateo
from centros_costo.models import MedidaBase
from contabilidad import services as contabilidad
from contabilidad.models import Cuenta, PeriodoContable
from usuarios import roles

from . import distribucion, ejecucion, services
from .tests import crear_usuario
from .tests_distribucion import BaseDistribucion, meses

D = Decimal


def por_codigo(departamentos):
    return {d["centro"]["codigo"]: d for d in departamentos}


class BaseEjecucion(BaseDistribucion):
    """Presupuesto 2026: TI 12,000 (energía 1,000/mes) y RR. HH. 6,000 (papelería 500/mes)."""

    def setUp(self):
        super().setUp()
        c = self.contador
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(usuario=c, codigo="1102", nombre="Bancos", padre=activo, exenta_centro_costo=True)
        self.agua = contabilidad.crear_cuenta(usuario=c, codigo="5203", nombre="Agua", padre=self.g52)
        self.mercadeo = self.centro("01-03", "Mercadeo", padre=self.matriz)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)

        self.p = services.crear_presupuesto(usuario=c, anio=2026, monto="100000")
        self.asignar(self.ti, "12000")
        self.asignar(self.rrhh, "6000")
        self.detallar(self.ti, [(self.energia, ["1000"] * 12)])
        self.detallar(self.rrhh, [(self.papeleria, ["500"] * 12)])

        self.gasto(self.energia, self.ti, "1000", 1)
        self.gasto(self.energia, self.ti, "1500", 2)
        self.gasto(self.energia, self.ti, "900", 3)
        self.gasto(self.agua, self.ti, "50", 3)  # cuenta sin presupuesto
        self.gasto(self.papeleria, self.rrhh, "200", 1)
        self.gasto(self.energia, self.mercadeo, "300", 2)  # centro sin asignación

    def gasto(self, cuenta, centro, monto, mes):
        asiento = contabilidad.crear_asiento(
            usuario=self.contador, fecha=date(2026, mes, 10), concepto="Gasto",
            lineas=[
                {"cuenta": cuenta, "centro_costo": centro, "debe": monto, "haber": 0},
                {"cuenta": self.bancos, "debe": 0, "haber": monto},
            ],
        )
        return contabilidad.contabilizar_asiento(asiento, usuario=self.contador)

    def reporte(self, corte=3, **kwargs):
        return ejecucion.ejecucion_presupuesto(self.p, corte=corte, **kwargs)


class EjecucionTests(BaseEjecucion):
    def test_medidas_por_departamento(self):
        r = self.reporte()
        d = por_codigo(r["departamentos"])
        self.assertEqual(list(d), ["01-01", "01-02", "01-03"])
        ti = d["01-01"]
        self.assertEqual(
            (ti["presupuesto_anual"], ti["presupuesto_al_corte"], ti["ejecutado_al_corte"], ti["variacion"], ti["porcentaje_ejecucion"]),
            ("12000.00", "3000.00", "3450.00", "-450.00", "115.00"),
        )
        self.assertEqual(ti["disponible_anual"], "8550.00")
        self.assertEqual(r["totales"]["presupuesto_al_corte"], "4500.00")
        self.assertEqual(r["totales"]["ejecutado_al_corte"], "3950.00")
        self.assertEqual(r["totales"]["presupuesto_anual"], "18000.00")

    def test_alertas_y_estados(self):
        r = self.reporte()
        estados = {k: v["estado"] for k, v in por_codigo(r["departamentos"]).items()}
        self.assertEqual(estados, {"01-01": "DESVIACION", "01-02": "SUBEJECUCION", "01-03": "SIN_PRESUPUESTO"})
        tipos = [(a["nivel"], a["tipo"], a["centro"]["codigo"], a["cuenta"] and a["cuenta"]["codigo"]) for a in r["alertas"]]
        self.assertEqual(tipos, [
            ("ADVERTENCIA", "DESVIACION", "01-01", None),
            ("ADVERTENCIA", "DESVIACION", "01-01", "5201"),
            ("ADVERTENCIA", "SIN_PRESUPUESTO", "01-01", "5203"),
            ("ADVERTENCIA", "SIN_PRESUPUESTO", "01-03", None),
            ("INFORMATIVA", "SUBEJECUCION", "01-02", None),
        ])
        self.assertEqual(r["resumen_alertas"], {"CRITICA": 0, "ADVERTENCIA": 4, "INFORMATIVA": 1})

    def test_umbral(self):
        r = self.reporte(umbral=D("20"))
        estados = {k: v["estado"] for k, v in por_codigo(r["departamentos"]).items()}
        # TI ejecutó 115 %: dentro de 120 %. La cuenta sin presupuesto sigue alertando.
        self.assertEqual(estados["01-01"], "SIN_PRESUPUESTO")
        self.assertFalse(any(a["tipo"] == "DESVIACION" for a in r["alertas"]))
        r = self.reporte(umbral=D("90"))
        self.assertEqual(por_codigo(r["departamentos"])["01-02"]["estado"], "EN_RANGO")
        with self.assertRaises(ValidationError):
            self.reporte(umbral=D("101"))
        with self.assertRaises(ValidationError):
            self.reporte(corte=13)

    def test_sobregiro(self):
        self.gasto(self.energia, self.ti, "9000", 4)
        r = self.reporte(corte=4)
        self.assertEqual(r["alertas"][0]["tipo"], "SOBREGIRO")
        self.assertEqual(r["alertas"][0]["nivel"], "CRITICA")
        self.assertEqual(por_codigo(r["departamentos"])["01-01"]["estado"], "SOBREGIRO")
        self.assertEqual(r["resumen_alertas"]["CRITICA"], 1)
        # Al corte de marzo aún no se registra el gasto de abril.
        self.assertEqual(self.reporte(corte=3)["resumen_alertas"]["CRITICA"], 0)

    def test_corte_y_serie_mensual(self):
        r = self.reporte(corte=1)
        self.assertEqual(r["totales"]["ejecutado_al_corte"], "1200.00")
        febrero = r["mensual"][1]
        self.assertEqual((febrero["presupuesto"], febrero["ejecutado"], febrero["ejecutado_acumulado"]), ("1500.00", "1800.00", "3000.00"))

    def test_detalle_del_departamento(self):
        r = self.reporte(centro=self.ti)
        self.assertEqual([f["cuenta"]["codigo"] for f in r["centro"]["cuentas"]], ["5201", "5203"])
        agua = r["centro"]["cuentas"][1]
        self.assertEqual((agua["presupuesto_al_corte"], agua["ejecutado_al_corte"], agua["porcentaje_ejecucion"]), ("0.00", "50.00", None))
        self.assertEqual(r["centro"]["mensual"][2]["ejecutado"], "950.00")

    def test_reversion_de_diario_compensa(self):
        asiento = self.gasto(self.energia, self.ti, "500", 3)
        self.assertEqual(por_codigo(self.reporte()["departamentos"])["01-01"]["ejecutado_al_corte"], "3950.00")
        contabilidad.revertir_asiento(asiento, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 20))
        self.assertEqual(por_codigo(self.reporte()["departamentos"])["01-01"]["ejecutado_al_corte"], "3450.00")

    def test_prorrateo_no_cambia_la_ejecucion(self):
        antes = self.reporte()["departamentos"]
        base = prorrateo.crear_base(usuario=self.contador, codigo="M2", nombre="Metros", unidad="m²")
        marzo = PeriodoContable.objects.get(anio=2026, mes=3)
        MedidaBase.objects.create(base=base, centro_costo=self.rrhh, periodo=marzo, valor=1, modificado_por=self.contador)
        regla = prorrateo.crear_regla(
            usuario=self.contador, nombre="TI", centro_origen=self.ti, base=base, cuentas=[self.g52], destinos=[self.rrhh]
        )
        ejecucion_prorrateo = prorrateo.ejecutar(usuario=self.contador, regla=regla, periodo=marzo)
        self.assertEqual(self.reporte()["departamentos"], antes)
        prorrateo.anular(ejecucion_prorrateo, usuario=self.contador, motivo="Prueba")
        self.assertEqual(self.reporte()["departamentos"], antes)

    def test_presupuesto_sin_distribucion(self):
        p = services.crear_presupuesto(usuario=self.contador, anio=2028, monto="5000")
        r = ejecucion.ejecucion_presupuesto(p, corte=12)
        self.assertEqual((r["departamentos"], r["alertas"], r["totales"]["ejecutado_al_corte"]), ([], [], "0.00"))
        self.assertEqual(distribucion.resumen_distribucion(p)["sin_distribuir"], "5000.00")


class EjecucionApiTests(BaseEjecucion):
    def test_api(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("jefe", roles.JEFE_AREA))
        url = f"/api/presupuestos/{self.p.pk}/ejecucion/"
        resp = client.get(url, {"corte": 3, "umbral": "10", "centro": self.ti.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["totales"]["ejecutado_al_corte"], "3950.00")
        self.assertEqual(resp.data["centro"]["codigo"], "01-01")
        self.assertEqual(client.get(url, {"corte": 0}).status_code, 400)
        self.assertEqual(client.get(url).status_code, 200)  # corte por defecto
        client.force_authenticate(None)
        self.assertEqual(client.get(url).status_code, 401)
