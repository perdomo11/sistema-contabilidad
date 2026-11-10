"""Pruebas de T5.4: dashboard de tesorería (compone T5.1, T5.2 y T5.3)."""
from datetime import date
from decimal import Decimal

from rest_framework.test import APIClient

from usuarios import roles

from . import flujo
from .cuentas_por_pagar import resumen_cuentas_por_pagar
from .dashboard import dashboard_tesoreria
from .models import ClasificacionFlujo
from .proyeccion import proyeccion_egresos
from .tests_cuentas_por_pagar import crear_usuario
from .tests_flujo import BaseFlujo

REF = date(2026, 2, 28)


class DashboardTests(BaseFlujo):
    def setUp(self):
        super().setUp()
        # Factura vencida grande: déficit proyectado.
        self.registrar(numero="F-2", emision=date(2026, 2, 1), vence=date(2026, 2, 15),
                       lineas=[{"cuenta": self.energia, "centro_costo": self.ti, "monto": Decimal("20000")}])

    def test_coincide_con_los_servicios(self):
        d = dashboard_tesoreria(fecha=REF)
        proyectado = flujo.flujo_proyectado(fecha=REF)
        self.assertEqual(d["flujo"]["saldo_actual"], "13600.00")
        self.assertEqual(d["flujo"]["saldo_proyectado"], proyectado["saldo_proyectado"])
        self.assertEqual(d["flujo"]["alertas"], proyectado["alertas"])
        self.assertEqual(d["egresos"]["acumulado"], proyeccion_egresos(fecha=REF)["acumulado"])
        self.assertEqual(d["cuentas_por_pagar"], resumen_cuentas_por_pagar(fecha=REF))
        self.assertIn("DEFICIT", [a["tipo"] for a in d["flujo"]["alertas"]])

    def test_series_y_proximos_pagos(self):
        d = dashboard_tesoreria(fecha=REF)
        self.assertEqual([(m["anio"], m["mes"]) for m in d["flujo_mensual"]],
                         [(2025, 9), (2025, 10), (2025, 11), (2025, 12), (2026, 1), (2026, 2)])
        self.assertEqual(d["flujo_mensual"][0]["entradas"], "0.00")
        self.assertEqual((d["flujo_mensual"][4]["entradas"], d["flujo_mensual"][5]["salidas"]), ("12000.00", "400.00"))
        self.assertEqual(len(d["flujo"]["semanas"]), 13)
        # Próximos pagos: la vencida F-2; F-1 (12/03) queda fuera de los 7 días.
        self.assertEqual([(p["fecha"], p["monto"]) for p in d["proximos_pagos"]], [("2026-02-15", "20000.00")])
        self.assertEqual(len(dashboard_tesoreria(fecha=date(2026, 3, 6))["proximos_pagos"]), 2)

    def test_sin_cuentas_de_efectivo(self):
        ClasificacionFlujo.objects.filter(actividad=ClasificacionFlujo.Actividad.EFECTIVO).delete()
        d = dashboard_tesoreria(fecha=REF)
        self.assertIsNone(d["flujo"])
        self.assertIn("cuentas de efectivo", d["aviso_flujo"])
        self.assertEqual(d["cuentas_por_pagar"]["pendiente"], "20600.00")

    def test_api_todos_los_roles(self):
        client = APIClient()
        for rol in (roles.JEFE_AREA, roles.AUDITOR, roles.TESORERO):
            client.force_authenticate(crear_usuario(f"u-{rol}", rol))
            resp = client.get("/api/tesoreria/dashboard/", {"fecha": "2026-02-28"})
            self.assertEqual((resp.status_code, resp.data["flujo"]["saldo_actual"]), (200, "13600.00"))
        client.force_authenticate(None)
        self.assertEqual(client.get("/api/tesoreria/dashboard/").status_code, 401)
