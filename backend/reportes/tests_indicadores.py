"""Pruebas de T3.3: indicadores de rentabilidad por área."""
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from contabilidad import services as contabilidad
from contabilidad.models import Cuenta
from usuarios import roles

from . import services
from .tests import DESDE, HASTA, BaseReportes, crear_usuario

R = Cuenta.Rubro


def por_clave(lista):
    return {x["clave"]: x for x in lista}


class IndicadoresRentabilidadTests(BaseReportes):
    def setUp(self):
        super().setUp()
        c = self.contador
        ingresos, gastos = self.intereses.padre.padre, self.g52.padre
        g43 = contabilidad.crear_cuenta(
            usuario=c, codigo="43", nombre="No operacionales", padre=ingresos, acepta_movimientos=False,
            rubro_resultado=R.INGRESO_NO_OPERACION,
        )
        self.otros_ingresos = contabilidad.crear_cuenta(usuario=c, codigo="4301", nombre="Otros ingresos", padre=g43)
        g51 = contabilidad.crear_cuenta(
            usuario=c, codigo="51", nombre="Costos de intermediación", padre=gastos, acepta_movimientos=False,
            rubro_resultado=R.COSTO_INTERMEDIACION, comportamiento_costo=Cuenta.Comportamiento.VARIABLE,
        )
        self.intereses_pagados = contabilidad.crear_cuenta(usuario=c, codigo="5101", nombre="Intereses pagados", padre=g51)
        g53 = contabilidad.crear_cuenta(
            usuario=c, codigo="53", nombre="No operacionales", padre=gastos, acepta_movimientos=False,
            rubro_resultado=R.GASTO_NO_OPERACION,
        )
        self.perdidas = contabilidad.crear_cuenta(usuario=c, codigo="5301", nombre="Pérdidas", padre=g53)

        self.gasto(self.intereses_pagados, self.negocios, "200")
        self.gasto(self.perdidas, self.proyecto, "30")
        self.registrar([
            {"cuenta": self.bancos, "debe": "50", "haber": 0},
            {"cuenta": self.otros_ingresos, "centro_costo": self.caja, "debe": 0, "haber": "50"},
        ])

    def reporte(self, **kwargs):
        return services.indicadores_rentabilidad(desde=DESDE, hasta=HASTA, **kwargs)

    def test_montos_por_rubro(self):
        r = self.reporte()
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01", "02", "90"])
        m = por_clave(r["montos"])
        esperado = {
            "ingresos_operacion": (["1000.00", "500.00", "0.00"], "1500.00"),
            "costo_intermediacion": (["200.00", "0.00", "0.00"], "200.00"),
            "margen_bruto": (["800.00", "500.00", "0.00"], "1300.00"),
            "gastos_operacion": (["300.00", "100.00", "0.00"], "400.00"),
            "resultado_operativo": (["500.00", "400.00", "0.00"], "900.00"),
            "ingresos_no_operacion": (["0.00", "50.00", "0.00"], "50.00"),
            "gastos_no_operacion": (["0.00", "0.00", "30.00"], "30.00"),
            "resultado_neto": (["500.00", "450.00", "-30.00"], "920.00"),
            "margen_contribucion": (["800.00", "550.00", "0.00"], "1350.00"),
        }
        for clave, (valores, total) in esperado.items():
            self.assertEqual((m[clave]["valores"], m[clave]["total"]), (valores, total), clave)

    def test_margenes_porcentuales(self):
        i = por_clave(self.reporte()["indicadores"])
        self.assertEqual((i["margen_bruto"]["valores"], i["margen_bruto"]["total"]), (["80.00", "100.00", None], "86.67"))
        self.assertEqual((i["margen_operativo"]["valores"], i["margen_operativo"]["total"]), (["50.00", "80.00", None], "60.00"))
        self.assertEqual(
            (i["margen_contribucion"]["valores"], i["margen_contribucion"]["total"]), (["80.00", "100.00", None], "87.10")
        )
        # Sin ingresos el margen no se calcula (no hay base).
        self.assertEqual((i["margen_neto"]["valores"], i["margen_neto"]["total"]), (["50.00", "81.82", None], "59.35"))

    def test_participacion_en_el_resultado(self):
        p = por_clave(self.reporte()["participacion"])
        self.assertTrue(p["resultado"]["aplica"])
        self.assertEqual(p["resultado"]["valores"], ["54.35", "48.91", "-3.26"])  # el proyecto con pérdida resta
        self.assertEqual(p["resultado"]["total"], "100.00")
        self.assertEqual(p["ingresos"]["valores"], ["64.52", "35.48", "0.00"])

    def test_participacion_no_aplica_con_resultado_no_positivo(self):
        self.gasto(self.agua, self.caja, "2000")
        p = por_clave(self.reporte()["participacion"])
        self.assertFalse(p["resultado"]["aplica"])
        self.assertEqual(p["resultado"]["valores"], [None, None, None])
        self.assertIsNone(p["resultado"]["total"])
        self.assertTrue(p["ingresos"]["aplica"])

    def test_cuadra_con_absorbente_y_contribucion(self):
        self.prorratear()
        for centro in (None, self.matriz):
            r = self.reporte(centro=centro)
            m = por_clave(r["montos"])
            absorbente = services.estado_resultados(desde=DESDE, hasta=HASTA, centro=centro)
            contribucion = services.enfoque_contribucion(desde=DESDE, hasta=HASTA, centro=centro)
            self.assertEqual(m["resultado_neto"]["valores"], absorbente["resultado"]["valores"])
            self.assertEqual(m["resultado_neto"]["total"], absorbente["resultado"]["total"])
            self.assertEqual(m["margen_contribucion"]["valores"], contribucion["margen_contribucion"]["valores"])
            self.assertEqual(
                por_clave(r["indicadores"])["margen_contribucion"]["valores"], contribucion["margen_contribucion"]["razon"][:-1]
            )

    def test_prorrateo_entra_en_gastos_de_operacion(self):
        self.prorratear()
        r = self.reporte(centro=self.matriz)
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01-01", "01-02"])
        m = por_clave(r["montos"])
        # Gerencia distribuye su gasto (queda en cero); Negocios recibe 75.
        self.assertEqual(m["gastos_operacion"]["valores"], ["0.00", "75.00"])
        self.assertEqual(m["resultado_operativo"]["valores"], ["0.00", "725.00"])
        self.assertEqual(m["margen_bruto"]["valores"], ["0.00", "800.00"])  # el prorrateo no toca el margen bruto
        self.assertEqual(por_clave(r["participacion"])["resultado"]["valores"], ["0.00", "100.00"])

    def test_rango_invalido(self):
        with self.assertRaises(ValidationError):
            services.indicadores_rentabilidad(desde=HASTA, hasta=DESDE)

    def test_api(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))
        resp = client.get("/api/reportes/indicadores/", {"desde": "2026-01-01", "hasta": "2026-12-31"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(por_clave(resp.data["montos"])["resultado_neto"]["total"], "920.00")
        self.assertEqual(client.get("/api/reportes/indicadores/", {"desde": "2026-12-31", "hasta": "2026-01-01"}).status_code, 400)
        client.force_authenticate(None)
        self.assertEqual(client.get("/api/reportes/indicadores/", {"desde": "2026-01-01", "hasta": "2026-12-31"}).status_code, 401)
