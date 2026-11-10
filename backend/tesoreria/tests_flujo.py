"""Pruebas de T5.3: flujo de efectivo real y proyectado con alertas de déficit."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from contabilidad import services as contabilidad
from contabilidad.models import Cuenta
from usuarios import roles

from . import flujo
from .models import ClasificacionFlujo
from .tests_cuentas_por_pagar import BaseCxP, crear_usuario

D = Decimal
A = ClasificacionFlujo.Actividad
ENE, FEB = (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 28))


def actividad(r, act):
    return next(a for a in r["actividades"] if a["actividad"] == act)


class BaseFlujo(BaseCxP):
    """Enero: aporte 10,000 (fin.), equipo −3,000 (inv.), intereses +2,000 (op.), traspaso a caja 500.
    Febrero: pago a proveedor −400 (op.), préstamo recibido +5,000 (fin.)."""

    def setUp(self):
        super().setUp()
        c = self.contador
        activo = self.bancos.padre
        self.caja = contabilidad.crear_cuenta(usuario=c, codigo="1101", nombre="Caja", padre=activo, exenta_centro_costo=True)
        pasivo = self.cxp.padre
        self.prestamo = contabilidad.crear_cuenta(usuario=c, codigo="2201", nombre="Préstamo", padre=pasivo, exenta_centro_costo=True)
        patrimonio = contabilidad.crear_cuenta(usuario=c, codigo="3", nombre="Patrimonio", tipo=Cuenta.Tipo.PATRIMONIO, acepta_movimientos=False)
        self.capital = contabilidad.crear_cuenta(usuario=c, codigo="31", nombre="Capital", padre=patrimonio, exenta_centro_costo=True)
        ingresos = contabilidad.crear_cuenta(usuario=c, codigo="4", nombre="Ingresos", tipo=Cuenta.Tipo.INGRESO, acepta_movimientos=False)
        self.intereses = contabilidad.crear_cuenta(usuario=c, codigo="4101", nombre="Intereses", padre=ingresos)
        for cuenta in (self.bancos, self.caja):
            flujo.asignar_actividad(usuario=c, cuenta=cuenta, actividad=A.EFECTIVO)
        flujo.asignar_actividad(usuario=c, cuenta=self.prestamo, actividad=A.FINANCIAMIENTO)

        self.mover(date(2026, 1, 5), self.bancos, self.capital, "10000")
        self.mover(date(2026, 1, 10), self.equipo, self.bancos, "3000")
        self.mover(date(2026, 1, 15), self.bancos, self.intereses, "2000", centro_haber=self.ti)
        self.mover(date(2026, 1, 20), self.caja, self.bancos, "500")
        factura = self.registrar(numero="F-1", emision=date(2026, 2, 10), vence=date(2026, 3, 12))  # 1,000
        self.pagar(factura, "400", fecha=date(2026, 2, 20))
        self.mover(date(2026, 2, 25), self.bancos, self.prestamo, "5000")

    def mover(self, fecha, cargo, abono, monto, centro_haber=None):
        asiento = contabilidad.crear_asiento(
            usuario=self.contador, fecha=fecha, concepto="Movimiento",
            lineas=[
                {"cuenta": cargo, "debe": monto, "haber": 0},
                {"cuenta": abono, "centro_costo": centro_haber, "debe": 0, "haber": monto},
            ],
        )
        return contabilidad.contabilizar_asiento(asiento, usuario=self.contador)


class FlujoRealTests(BaseFlujo):
    def test_por_actividad_y_conciliacion(self):
        r = flujo.flujo_efectivo(desde=date(2026, 1, 1), hasta=date(2026, 2, 28))
        self.assertEqual(r["saldo_inicial"], "0.00")
        op, inv, fin = (actividad(r, a) for a in (A.OPERACION, A.INVERSION, A.FINANCIAMIENTO))
        self.assertEqual((op["entradas"], op["salidas"], op["neto"]), ("2000.00", "400.00", "1600.00"))
        self.assertEqual((inv["entradas"], inv["salidas"], inv["neto"]), ("0.00", "3000.00", "-3000.00"))
        self.assertEqual((fin["entradas"], fin["neto"]), ("15000.00", "15000.00"))
        self.assertEqual((r["neto"], r["saldo_final"], r["saldo_final_contable"], r["cuadra"]), ("13600.00", "13600.00", "13600.00", True))
        # El traspaso a caja no es flujo; el pago a proveedor sale por la cuenta por pagar (operación).
        self.assertEqual([f["cuenta"]["codigo"] for f in op["filas"]], ["2401", "4101"])
        self.assertEqual(r["mensual"], [
            {"anio": 2026, "mes": 1, "entradas": "12000.00", "salidas": "3000.00", "neto": "9000.00"},
            {"anio": 2026, "mes": 2, "entradas": "5000.00", "salidas": "400.00", "neto": "4600.00"},
        ])

    def test_saldo_inicial_del_rango(self):
        r = flujo.flujo_efectivo(desde=FEB[0], hasta=FEB[1])
        self.assertEqual((r["saldo_inicial"], r["neto"], r["saldo_final"], r["cuadra"]), ("9000.00", "4600.00", "13600.00", True))

    def test_reclasificar_mueve_de_actividad(self):
        flujo.asignar_actividad(usuario=self.contador, cuenta=self.equipo, actividad=A.OPERACION)
        r = flujo.flujo_efectivo(desde=ENE[0], hasta=ENE[1])
        self.assertEqual(actividad(r, A.INVERSION)["salidas"], "0.00")
        self.assertEqual(actividad(r, A.OPERACION)["salidas"], "3000.00")
        flujo.quitar_actividad(ClasificacionFlujo.objects.get(cuenta=self.equipo), usuario=self.contador)
        self.assertEqual(actividad(flujo.flujo_efectivo(desde=ENE[0], hasta=ENE[1]), A.INVERSION)["salidas"], "3000.00")

    def test_herencia_y_validaciones(self):
        grupo = contabilidad.crear_cuenta(usuario=self.contador, codigo="1105", nombre="Bancos exterior", padre=self.bancos.padre,
                                          acepta_movimientos=False)
        hija = contabilidad.crear_cuenta(usuario=self.contador, codigo="110501", nombre="Banco X", padre=grupo, exenta_centro_costo=True)
        self.assertNotIn(hija.pk, flujo.cuentas_efectivo())  # por tipo: activo → inversión
        flujo.asignar_actividad(usuario=self.contador, cuenta=grupo, actividad=A.EFECTIVO)
        self.assertIn(hija.pk, flujo.cuentas_efectivo())  # la hereda del grupo
        self.assertEqual(flujo.actividades_por_cuenta()[self.capital.pk][0], A.FINANCIAMIENTO)  # por tipo
        with self.assertRaises(ValidationError):
            flujo.asignar_actividad(usuario=self.contador, cuenta=self.cxp, actividad=A.EFECTIVO)
        ClasificacionFlujo.objects.all().delete()
        with self.assertRaises(ValidationError):
            flujo.flujo_efectivo(desde=ENE[0], hasta=ENE[1])


class FlujoProyectadoTests(BaseFlujo):
    REF = date(2026, 2, 28)

    def proyectar(self, entradas="ninguna"):
        return flujo.flujo_proyectado(fecha=self.REF, entradas=entradas)

    def test_sin_deficit_y_bajo_minimo(self):
        r = self.proyectar()
        self.assertEqual((r["saldo_actual"], r["alertas"]), ("13600.00", []))
        semana2 = r["semanas"][1]  # la factura F-1 (saldo 600) vence el 12/03, día 12
        self.assertEqual((semana2["saldo_inicial"], semana2["salidas"], semana2["saldo_final"]), ("13600.00", "600.00", "13000.00"))
        self.assertEqual(r["saldo_proyectado"], {"30": "13000.00", "60": "13000.00", "90": "13000.00"})
        flujo.actualizar_configuracion(usuario=self.tesorero, datos={"saldo_minimo": D("13500")})
        r = self.proyectar()
        self.assertEqual([(a["tipo"], a["semana"]) for a in r["alertas"]], [("BAJO_MINIMO", 2)])
        self.assertEqual(r["semanas"][1]["estado"], "BAJO_MINIMO")

    def test_deficit_con_vencidos(self):
        self.registrar(numero="F-2", emision=date(2026, 2, 1), vence=date(2026, 2, 15),
                       lineas=[{"cuenta": self.energia, "centro_costo": self.ti, "monto": D("20000")}])
        r = self.proyectar()
        self.assertEqual(r["semanas"][0]["saldo_final"], "-6400.00")
        self.assertEqual(r["semanas"][0]["estado"], "DEFICIT")
        tipos = {a["tipo"]: a for a in r["alertas"]}
        self.assertEqual(set(tipos), {"DEFICIT", "VENCIDOS"})
        self.assertEqual((tipos["DEFICIT"]["semana"], tipos["DEFICIT"]["monto"]), (1, "7000.00"))
        self.assertEqual(tipos["VENCIDOS"]["monto"], "20000.00")
        self.assertEqual((r["saldo_minimo_proyectado"], r["saldo_proyectado"]["30"]), ("-7000.00", "-7000.00"))

    def test_entradas_historicas(self):
        flujo.actualizar_configuracion(usuario=self.tesorero, datos={"dias_historia": 60})
        r = self.proyectar(entradas="historico")
        # Entradas de operación de los últimos 60 días: intereses 2,000 → 33.33 diarios.
        self.assertEqual((r["base_historica"]["entradas_operacion"], r["entradas_diarias"]), ("2000.00", "33.33"))
        self.assertEqual(r["semanas"][0]["entradas"], "233.31")
        self.assertEqual(r["saldo_proyectado"]["30"], str(D("13600") + D("33.33") * 30 - D("600")))
        with self.assertRaises(ValidationError):
            flujo.flujo_proyectado(fecha=self.REF, entradas="otra")


class CargarFlujoBaseTests(TestCase):
    def test_comando(self):
        crear_usuario("contador", roles.CONTADOR)
        out = StringIO()
        call_command("cargar_catalogo_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        call_command("cargar_flujo_base", usuario="contador", stdout=out, stderr=StringIO())
        efectivo = set(Cuenta.objects.filter(pk__in=flujo.cuentas_efectivo()).values_list("codigo", flat=True))
        self.assertTrue({"11", "1101", "110101", "1103"} <= efectivo)
        self.assertEqual(flujo.actividades_por_cuenta()[Cuenta.objects.get(codigo="2201").pk][0], A.FINANCIAMIENTO)
        call_command("cargar_flujo_base", usuario="contador", stdout=out, stderr=StringIO())
        self.assertIn("0 asignada(s)", out.getvalue())


class FlujoApiTests(BaseFlujo):
    def test_api(self):
        client = APIClient()
        client.force_authenticate(self.tesorero)
        resp = client.get("/api/tesoreria/flujo-efectivo/", {"desde": "2026-01-01", "hasta": "2026-02-28"})
        self.assertEqual((resp.status_code, resp.data["saldo_final"]), (200, "13600.00"))
        resp = client.get("/api/tesoreria/flujo-proyectado/", {"fecha": "2026-02-28", "entradas": "ninguna"})
        self.assertEqual((resp.status_code, resp.data["saldo_actual"]), (200, "13600.00"))
        resp = client.patch("/api/tesoreria/configuracion/", {"saldo_minimo": "500.00"}, format="json")
        self.assertEqual((resp.status_code, resp.data["saldo_minimo"]), (200, "500.00"))
        resp = client.post("/api/tesoreria/clasificacion-flujo/", {"cuenta": self.equipo.pk, "actividad": "OPERACION"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual({c["codigo"] for c in resp.data["cuentas_efectivo"]}, {"1101", "1103"})
        pk = next(a["id"] for a in resp.data["asignaciones"] if a["cuenta"]["codigo"] == "1201")
        self.assertEqual(client.delete(f"/api/tesoreria/clasificacion-flujo/{pk}/").status_code, 200)

    def test_otros_roles_solo_consultan(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))
        self.assertEqual(client.get("/api/tesoreria/flujo-proyectado/").status_code, 200)
        self.assertEqual(client.get("/api/tesoreria/configuracion/").status_code, 200)
        self.assertEqual(client.patch("/api/tesoreria/configuracion/", {"saldo_minimo": "1"}, format="json").status_code, 403)
        resp = client.post("/api/tesoreria/clasificacion-flujo/", {"cuenta": self.equipo.pk, "actividad": "OPERACION"}, format="json")
        self.assertEqual(resp.status_code, 403)
