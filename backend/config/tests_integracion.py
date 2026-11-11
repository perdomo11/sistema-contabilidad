"""Prueba de integración de punta a punta (T6.1, ampliada en T7.2–T7.4).

Con los datos de ejemplo de todos los módulos recorre un ciclo completo de marzo de 2026 (aporte de capital,
ingresos y gastos directos y por regla, factura por pagar y su pago, CCF de compra con IVA y retención,
CCF de venta con IVA débito, prorrateo escalonado, presupuesto aprobado y distribuido) y verifica que los
módulos cuadran entre sí. `DatosDemoTests` prueba la carga de datos de demostración (T7.4).
"""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Sum
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
from tesoreria.libro_compras import libro_compras
from tesoreria.models import CuentaPorPagar, Proveedor
from usuarios import roles
from ventas import documentos as documentos_venta
from ventas import services as clientes
from ventas.libro import libro_ventas
from ventas.models import Cliente, DocumentoVenta

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
        # T7.2: CCF de vigilancia (proveedor → Gerencia general por regla) con IVA y retención del 1 %; queda pendiente.
        cls.ccf_compra = cpp.registrar_cuenta_por_pagar(
            usuario=cls.tesorero, proveedor=Proveedor.objects.get(nit="0614-300610-104-2"), tipo_documento="CCF",
            numero_documento="S-200", fecha_emision=date(2026, 3, 6), fecha_vencimiento=date(2026, 4, 4),
            concepto="Vigilancia de marzo", lineas=[{"cuenta": cuenta["520206"], "monto": D("1000")}], aplica_retencion=True,
        )
        # T7.3: CCF de venta cobrado en banco: intereses exentos y comisión gravada.
        cliente = clientes.crear_cliente(usuario=cls.contador, nombre="Comercial de Prueba, S.A. de C.V.", tipo="CONTRIBUYENTE",
                                         nit="0614-010101-999-1", nrc="999999-9")
        cls.venta = documentos_venta.registrar_documento_venta(
            usuario=cls.contador, cliente=cliente, tipo_documento="CCF", numero_documento="CCF-1", fecha_emision=date(2026, 3, 15),
            concepto="Intereses y comisiones de marzo", lineas=[
                {"cuenta": cuenta["4101"], "centro_costo": centro["02-02"], "monto": D("2000"), "exenta": True},
                {"cuenta": cuenta["4201"], "centro_costo": centro["02-02"], "monto": D("1000")},
            ],
        )
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
        # 20,000 − 7,000 − 3,000 − 500 − 1,000 (vigilancia, sin IVA) + 3,000 (venta, sin IVA)
        self.assertEqual(absorbente["resultado"]["total"], "11500.00")
        contribucion = reportes.enfoque_contribucion(desde=DESDE, hasta=HASTA)
        self.assertEqual(contribucion["resultado"], "11500.00")
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
        self.assertEqual(ejecutado["01-01"], "4000.00")  # energía + alquileres + vigilancia, sin lo prorrateado
        estados = {d["centro"]["codigo"]: d["estado"] for d in r["departamentos"]}
        self.assertEqual(estados["01-04"], "EN_RANGO")  # ejecutó exactamente lo presupuestado
        self.assertEqual(estados["01-03"], "SIN_PRESUPUESTO")

    def test_tesoreria_cuadra(self):
        real = flujo.flujo_efectivo(desde=DESDE, hasta=date(2026, 3, 31))
        self.assertTrue(real["cuadra"])
        self.assertEqual(real["saldo_final"], "112830.00")  # 100,000 + 20,000 − 7,000 − 3,000 − 300 + 3,130 (venta con IVA)
        operacion = next(a for a in real["actividades"] if a["actividad"] == "OPERACION")
        self.assertEqual((operacion["entradas"], operacion["salidas"]), ("23130.00", "10300.00"))
        tablero = dashboard_tesoreria(fecha=date(2026, 3, 31))
        self.assertEqual(tablero["flujo"]["saldo_actual"], "112830.00")
        self.assertEqual(tablero["cuentas_por_pagar"]["pendiente"], "1320.00")  # 200 + CCF neto de retención (1,120)
        self.assertEqual(tablero["egresos"]["tramos"][1]["monto"], "1320.00")  # ambos vencen el 04/04, en 0-30 días

    def test_libros_de_iva(self):
        compras = libro_compras(anio=2026, mes=3)
        self.assertEqual([f["numero_documento"] for f in compras["filas"]], ["S-200"])  # la factura T-100 no da crédito fiscal
        self.assertEqual((compras["totales"]["iva_credito_fiscal"], compras["totales"]["iva_retenido"]), ("130.00", "10.00"))
        ventas = libro_ventas(anio=2026, mes=3)
        self.assertEqual((ventas["resumen"]["iva_debito_fiscal"], ventas["resumen"]["total_ventas"]), ("130.00", "3130.00"))
        saldos = {c: LineaAsiento.objects.filter(cuenta__codigo=c, asiento__estado=Asiento.Estado.CONTABILIZADO)
                  .aggregate(s=Sum("debe") - Sum("haber"))["s"] for c in ("1403", "2405", "2406")}
        self.assertEqual(saldos, {"1403": D("130.00"), "2405": D("-10.00"), "2406": D("-130.00")})

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


class DatosDemoTests(TestCase):
    """T7.4: `cargar_datos_demo` sobre una base limpia (marzo y abril de 2026)."""

    @classmethod
    def setUpTestData(cls):
        cls.contador = usuario("contador", roles.CONTADOR)
        cls.salida = StringIO()
        call_command("cargar_datos_demo", usuario="contador", desde="2026-03-01", hasta="2026-04-30", stdout=cls.salida)

    def test_carga_completa_y_verificada(self):
        texto = self.salida.getvalue()
        self.assertIn("Datos de demostración cargados y verificados.", texto)
        self.assertIn("Integridad verificada", texto)
        self.assertEqual(Proveedor.objects.count(), 18)
        self.assertEqual(Cliente.objects.count(), 25)
        self.assertEqual(Asiento.objects.filter(referencia__startswith="PLANILLA-").count(), 2)
        self.assertEqual(Asiento.objects.filter(referencia="PAGO-PLANILLA-2026-03").count(), 1)  # el de abril vence en mayo
        self.assertEqual(EjecucionProrrateo.objects.count(), 6)  # 3 reglas × 2 meses
        self.assertTrue(CuentaPorPagar.objects.filter(estado="PAGADA").exists())
        self.assertTrue(CuentaPorPagar.objects.filter(estado="PENDIENTE").exists())  # documentos que vencen después del rango
        self.assertTrue(CuentaPorPagar.objects.filter(iva_retenido__gt=0).exists())
        self.assertTrue(CuentaPorPagar.objects.filter(compras_exentas__gt=0).exists())
        self.assertTrue(DocumentoVenta.objects.filter(tipo_documento="CCF").exists())
        self.assertTrue(DocumentoVenta.objects.filter(tipo_documento="FACTURA").exists())

    def test_reglas_contables(self):
        lineas = LineaAsiento.objects.filter(asiento__estado=Asiento.Estado.CONTABILIZADO)
        totales = lineas.aggregate(d=Sum("debe"), h=Sum("haber"))
        self.assertEqual(totales["d"], totales["h"])
        sin_centro = lineas.filter(cuenta__tipo__in=[Cuenta.Tipo.INGRESO, Cuenta.Tipo.GASTO], centro_costo__isnull=True)
        self.assertFalse(sin_centro.exists())
        self.assertFalse(integridad.hay_fallas(integridad.verificar(2026)))

    def test_libros_cuadran_con_las_cuentas(self):
        def movimiento(codigo, mes, signo):
            s = LineaAsiento.objects.filter(cuenta__codigo=codigo, asiento__estado=Asiento.Estado.CONTABILIZADO,
                                            asiento__fecha__month=mes).aggregate(d=Sum("debe"), h=Sum("haber"))
            return signo * ((s["d"] or D(0)) - (s["h"] or D(0)))

        for mes in (3, 4):
            self.assertEqual(movimiento("1403", mes, 1), D(libro_compras(anio=2026, mes=mes)["totales"]["iva_credito_fiscal"]))
            self.assertEqual(movimiento("2406", mes, -1), D(libro_ventas(anio=2026, mes=mes)["resumen"]["iva_debito_fiscal"]))

    def test_reportes_y_flujo(self):
        estado = reportes.estado_resultados(desde=date(2026, 3, 1), hasta=date(2026, 4, 30))
        self.assertGreater(D(estado["resultado"]["total"]), 0)  # la agencia opera con utilidad
        self.assertEqual(reportes.enfoque_contribucion(desde=date(2026, 3, 1), hasta=date(2026, 4, 30))["resultado"],
                         estado["resultado"]["total"])
        self.assertTrue(flujo.flujo_efectivo(desde=date(2026, 3, 1), hasta=date(2026, 4, 30))["cuadra"])

    def test_idempotente(self):
        antes = (Asiento.objects.count(), CuentaPorPagar.objects.count(), DocumentoVenta.objects.count())
        salida = StringIO()
        call_command("cargar_datos_demo", usuario="contador", desde="2026-03-01", hasta="2026-04-30", stdout=salida)
        self.assertEqual((Asiento.objects.count(), CuentaPorPagar.objects.count(), DocumentoVenta.objects.count()), antes)
        self.assertIn("No se creó nada nuevo", salida.getvalue())

    def test_periodo_cerrado(self):
        for p in PeriodoContable.objects.filter(anio=2026, mes__in=[1, 2]).order_by("mes"):
            contabilidad.cerrar_periodo(p, usuario=self.contador)
        antes = Asiento.objects.count()
        with self.assertRaises(CommandError) as e:
            call_command("cargar_datos_demo", usuario="contador", desde="2026-02-01", hasta="2026-02-28", stdout=StringIO())
        self.assertIn("cerrados", str(e.exception))
        self.assertEqual(Asiento.objects.count(), antes)
