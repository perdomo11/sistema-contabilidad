"""Prueba de integración de punta a punta (T6.1).

Con los datos de ejemplo de todos los módulos recorre un ciclo completo de marzo de 2026 (aporte de capital,
ingresos y gastos directos y por regla, factura por pagar y su pago, prorrateo escalonado, presupuesto
aprobado y distribuido) y verifica que los módulos cuadran entre sí.
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.test import TestCase

from centros_costo import prorrateo
from centros_costo.models import CentroCosto, EjecucionProrrateo
from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta, LineaAsiento, PeriodoContable
from presupuesto import distribucion, ejecucion
from presupuesto import services as presupuesto
from reportes import integridad
from reportes import services as reportes
from tesoreria import cuentas_por_pagar as cpp
from tesoreria import flujo
from tesoreria.dashboard import dashboard_tesoreria
from tesoreria.models import Proveedor
from usuarios import roles

D = Decimal
DESDE, HASTA = date(2026, 1, 1), date(2026, 12, 31)


def usuario(nombre, rol):
    u = User.objects.create_user(username=nombre, password="Prueba_2026!")
    u.groups.set(Group.objects.filter(name=rol))
    return u


class CicloCompletoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.contador = usuario("contador", roles.CONTADOR)
        cls.tesorero = usuario("tesorero", roles.TESORERO)
        salida = {"stdout": StringIO(), "stderr": StringIO()}
        call_command("cargar_catalogo_base", usuario="contador", **salida)
        contabilidad.crear_ejercicio(usuario=cls.contador, anio=2026)
        call_command("cargar_centros_base", usuario="contador", **salida)
        call_command("cargar_asignacion_base", usuario="contador", **salida)
        call_command("cargar_prorrateo_base", usuario="contador", anio=2026, **salida)
        call_command("cargar_flujo_base", usuario="contador", **salida)

        cuenta = {c.codigo: c for c in Cuenta.objects.all()}
        centro = {c.codigo: c for c in CentroCosto.objects.all()}
        cls.cuenta, cls.centro = cuenta, centro

        def asiento(dia, lineas):
            a = contabilidad.crear_asiento(usuario=cls.contador, fecha=date(2026, 3, dia), concepto="Ciclo de prueba", lineas=lineas)
            return contabilidad.contabilizar_asiento(a, usuario=cls.contador)

        banco = cuenta["1103"]
        asiento(1, [{"cuenta": banco, "debe": "100000", "haber": 0}, {"cuenta": cuenta["31"], "debe": 0, "haber": "100000"}])
        asiento(10, [
            {"cuenta": banco, "debe": "20000", "haber": 0},
            {"cuenta": cuenta["4101"], "centro_costo": centro["02-02"], "debe": 0, "haber": "12000"},
            {"cuenta": cuenta["4101"], "centro_costo": centro["03-02"], "debe": 0, "haber": "8000"},
        ])
        asiento(25, [
            {"cuenta": cuenta["520101"], "centro_costo": centro["01-04"], "debe": "3000", "haber": 0},
            {"cuenta": cuenta["520101"], "centro_costo": centro["02-01"], "debe": "4000", "haber": 0},
            {"cuenta": banco, "debe": 0, "haber": "7000"},
        ])
        # Sin centro: lo asignan las reglas de ejemplo (energía y alquileres → Gerencia general).
        asiento(26, [
            {"cuenta": cuenta["520201"], "debe": "1000", "haber": 0},
            {"cuenta": cuenta["520204"], "debe": "2000", "haber": 0},
            {"cuenta": banco, "debe": 0, "haber": "3000"},
        ])
        # Factura por pagar (telecomunicaciones → Tecnología por regla) y pago parcial.
        cls.factura = cpp.registrar_cuenta_por_pagar(
            usuario=cls.tesorero, proveedor=Proveedor.objects.get(nit="0614-110705-103-8"), tipo_documento="FACTURA",
            numero_documento="T-100", fecha_emision=date(2026, 3, 5), fecha_vencimiento=date(2026, 4, 4),
            concepto="Enlaces de marzo", lineas=[{"cuenta": cuenta["520203"], "monto": D("500")}],
        )
        cpp.registrar_pago(cls.factura, usuario=cls.tesorero, fecha=date(2026, 3, 20), monto=D("300"), cuenta_banco=banco)
        # Prorrateo escalonado de marzo (las tres reglas de ejemplo).
        prorrateo.ejecutar_pendientes(usuario=cls.contador, periodo=PeriodoContable.objects.get(anio=2026, mes=3))
        # Presupuesto 2026 aprobado y distribuido.
        p = presupuesto.crear_presupuesto(usuario=cls.contador, anio=2026, monto="50000")
        cls.presupuesto = presupuesto.aprobar_presupuesto(p, usuario=cls.contador, referencia="Acta JD 01/2026")
        for codigo, monto, cuenta_detalle, marzo in (("01-01", "10000", "520201", "1500"), ("01-04", "5000", "520101", "3000")):
            distribucion.asignar_departamento(cls.presupuesto, usuario=cls.contador, centro=centro[codigo], monto=D(monto))
            meses = ["0"] * 12
            meses[2] = marzo
            distribucion.guardar_detalle(cls.presupuesto, usuario=cls.contador, centro=centro[codigo],
                                         filas=[{"cuenta": cuenta[cuenta_detalle], "meses": meses}])

    def test_contabilidad(self):
        self.assertEqual(EjecucionProrrateo.objects.count(), 3)
        lineas = LineaAsiento.objects.filter(asiento__estado=Asiento.Estado.CONTABILIZADO)
        totales = {k: sum((getattr(l, k) for l in lineas), D(0)) for k in ("debe", "haber")}
        self.assertEqual(totales["debe"], totales["haber"])
        # La regla de asignación imputó la factura a Tecnología.
        linea = self.factura.asiento.lineas.get(cuenta=self.cuenta["520203"])
        self.assertEqual((linea.centro_costo.codigo, linea.regla_asignacion is not None), ("01-03", True))

    def test_reportes_cuadran(self):
        absorbente = reportes.estado_resultados(desde=DESDE, hasta=HASTA)
        self.assertEqual(absorbente["resultado"]["total"], "9500.00")  # 20,000 − 7,000 − 3,000 − 500
        contribucion = reportes.enfoque_contribucion(desde=DESDE, hasta=HASTA)
        self.assertEqual(contribucion["resultado"], "9500.00")
        self.assertEqual(contribucion["resultado_segmento"]["valores"], absorbente["resultado"]["valores"])
        indicadores = reportes.indicadores_rentabilidad(desde=DESDE, hasta=HASTA)
        neto = next(m for m in indicadores["montos"] if m["clave"] == "resultado_neto")
        self.assertEqual(neto["valores"], absorbente["resultado"]["valores"])
        # El prorrateo reparte costos entre unidades pero no cambia el total.
        indirectos = absorbente["secciones"][2]
        self.assertEqual(indirectos["total"], "0.00")
        self.assertNotEqual(indirectos["filas"], [])

    def test_ejecucion_presupuestaria_igual_a_gastos_directos(self):
        r = ejecucion.ejecucion_presupuesto(self.presupuesto, corte=3)
        ejecutado = {d["centro"]["codigo"]: d["ejecutado_al_corte"] for d in r["departamentos"]}
        matriz = reportes.estado_resultados(desde=DESDE, hasta=HASTA, centro=self.centro["01"])
        directos = dict(zip([c["codigo"] for c in matriz["columnas"]], matriz["secciones"][1]["valores"]))
        for codigo in ("01-01", "01-03", "01-04"):
            self.assertEqual(ejecutado[codigo], directos[codigo], codigo)
        self.assertEqual(ejecutado["01-01"], "3000.00")  # energía + alquileres, sin lo prorrateado
        estados = {d["centro"]["codigo"]: d["estado"] for d in r["departamentos"]}
        self.assertEqual(estados["01-04"], "EN_RANGO")  # ejecutó exactamente lo presupuestado
        self.assertEqual(estados["01-03"], "SIN_PRESUPUESTO")

    def test_tesoreria_cuadra(self):
        real = flujo.flujo_efectivo(desde=DESDE, hasta=date(2026, 3, 31))
        self.assertTrue(real["cuadra"])
        self.assertEqual(real["saldo_final"], "109700.00")  # 100,000 + 20,000 − 7,000 − 3,000 − 300
        operacion = next(a for a in real["actividades"] if a["actividad"] == "OPERACION")
        self.assertEqual((operacion["entradas"], operacion["salidas"]), ("20000.00", "10300.00"))
        tablero = dashboard_tesoreria(fecha=date(2026, 3, 31))
        self.assertEqual(tablero["flujo"]["saldo_actual"], "109700.00")
        self.assertEqual(tablero["cuentas_por_pagar"]["pendiente"], "200.00")
        self.assertEqual(tablero["egresos"]["tramos"][1]["monto"], "200.00")  # vence el 04/04, en 0-30 días

    def test_integridad(self):
        resultados = integridad.verificar(2026)
        self.assertFalse(integridad.hay_fallas(resultados), resultados)
        self.assertEqual({r["codigo"]: r["estado"] for r in resultados}["CENTRO_COSTO"], integridad.OK)
        out = StringIO()
        call_command("verificar_integridad", anio=2026, stdout=out)
        self.assertIn("Integridad verificada", out.getvalue())


class IntegridadDetectaFallasTests(TestCase):
    """El verificador debe detectar datos alterados por fuera de los servicios."""

    def test_saldo_alterado_de_cuenta_por_pagar(self):
        from tesoreria.tests_cuentas_por_pagar import BaseCxP

        caso = BaseCxP(methodName="setUp")
        caso.setUp()
        factura = caso.registrar()
        caso.pagar(factura, "100")
        from tesoreria.models import CuentaPorPagar

        # Se simula una alteración directa (saldo y estado coherentes entre sí, pero no con los pagos).
        CuentaPorPagar.objects.filter(pk=factura.pk).update(saldo=D("950.00"))
        resultados = {r["codigo"]: r for r in integridad.verificar(2026)}
        self.assertEqual(resultados["CUENTAS_POR_PAGAR"]["estado"], integridad.FALLA)
        self.assertIn("saldo 950.00", resultados["CUENTAS_POR_PAGAR"]["detalle"][0])
