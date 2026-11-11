"""Pruebas de T7.2: IVA en compras y libro de compras."""
from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, override_settings
from openpyxl import load_workbook
from rest_framework.test import APIClient

from config.excel import FILA_TITULOS, FORMATO_MONTO
from contabilidad import services as contabilidad
from contabilidad.models import Cuenta, LineaAsiento
from usuarios import roles

from . import cuentas_por_pagar as cpp
from . import services as proveedores
from .libro_compras import libro_compras
from .models import CuentaPorPagar
from .tests_cuentas_por_pagar import BaseCxP, crear_usuario

D = Decimal


class BaseIva(BaseCxP):
    def setUp(self):
        super().setUp()
        c = self.contador
        activo, pasivo = Cuenta.objects.get(codigo="1"), Cuenta.objects.get(codigo="2")
        self.iva = contabilidad.crear_cuenta(usuario=c, codigo="1403", nombre="IVA crédito fiscal", padre=activo, exenta_centro_costo=True)
        self.retenido = contabilidad.crear_cuenta(usuario=c, codigo="2405", nombre="IVA retenido", padre=pasivo, exenta_centro_costo=True)
        self.proveedor.nrc = "123456-7"
        self.proveedor.save()

    def ccf(self, numero="CCF-001", gravadas="1000.00", exentas="0", emision=date(2026, 3, 1), **kwargs):
        lineas = [{"cuenta": self.energia, "centro_costo": self.ti, "monto": D(gravadas) + D(exentas)}]
        return cpp.registrar_cuenta_por_pagar(
            usuario=self.contador, proveedor=self.proveedor, tipo_documento="CCF", numero_documento=numero,
            fecha_emision=emision, fecha_vencimiento=emision, concepto="Energía", lineas=lineas,
            compras_exentas=D(exentas), **kwargs,
        )

    def saldo(self, cuenta):
        lineas = LineaAsiento.objects.filter(cuenta=cuenta, asiento__estado="CONTABILIZADO")
        return sum((l.debe - l.haber for l in lineas), D(0))


class IvaComprasTests(BaseIva):
    def test_ccf_carga_iva_credito_fiscal(self):
        cxp = self.ccf()
        self.assertEqual(
            (cxp.compras_gravadas, cxp.compras_exentas, cxp.iva_credito_fiscal, cxp.iva_retenido, cxp.monto_total, cxp.saldo),
            (D("1000.00"), D("0.00"), D("130.00"), D("0.00"), D("1130.00"), D("1130.00")),
        )
        self.assertEqual(self.lineas(cxp.asiento), [
            ("5201", "01", D("1000.00"), D("0.00")),
            ("1403", None, D("130.00"), D("0.00")),
            ("2401", None, D("0.00"), D("1130.00")),
        ])

    def test_ccf_con_exentas_y_retencion(self):
        cxp = self.ccf(gravadas="500.00", exentas="200.00", aplica_retencion=True)
        # 500 + 200 + 65 − 5
        self.assertEqual((cxp.iva_credito_fiscal, cxp.iva_retenido, cxp.monto_total), (D("65.00"), D("5.00"), D("760.00")))
        self.assertEqual(self.lineas(cxp.asiento), [
            ("5201", "01", D("700.00"), D("0.00")),
            ("1403", None, D("65.00"), D("0.00")),
            ("2401", None, D("0.00"), D("760.00")),
            ("2405", None, D("0.00"), D("5.00")),
        ])

    def test_iva_con_redondeo_del_documento(self):
        cxp = self.ccf(gravadas="10.05", iva_credito_fiscal=D("1.30"))  # 13 % = 1.3065 → 1.31; se admite ±0.01
        self.assertEqual(cxp.monto_total, D("11.35"))

    def test_validaciones(self):
        with self.assertRaises(ValidationError) as e:
            self.ccf(iva_credito_fiscal=D("100.00"))
        self.assertIn("13 %", str(e.exception))
        with self.assertRaises(ValidationError):
            self.ccf(numero="X2", gravadas="80.00", aplica_retencion=True)  # retención solo desde US$100
        with self.assertRaises(ValidationError):
            self.ccf(numero="X3", compras_gravadas=D("900.00"))  # gravadas + exentas ≠ imputación
        with self.assertRaises(ValidationError):
            self.ccf(numero="X4", exentas="-5")
        with self.assertRaises(ValidationError) as e:
            self.registrar(numero="F-IVA", iva_credito_fiscal=D("130.00"))  # una factura no da crédito fiscal
        self.assertIn("CCF", str(e.exception))
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-RET", aplica_retencion=True)
        self.assertEqual(CuentaPorPagar.objects.count(), 0)

    def test_falta_cuenta_de_iva(self):
        Cuenta.objects.filter(pk=self.iva.pk).update(codigo="1499")
        with self.assertRaises(ValidationError) as e:
            self.ccf()
        self.assertIn("1403", str(e.exception))

    def test_factura_y_recibo_sin_desglose(self):
        factura = self.registrar()
        self.assertEqual((factura.compras_gravadas, factura.compras_exentas, factura.iva_credito_fiscal), (D("1000.00"), D("0.00"), D("0.00")))
        recibo = cpp.registrar_cuenta_por_pagar(
            usuario=self.contador, proveedor=self.proveedor, tipo_documento="RECIBO", numero_documento="R-1",
            fecha_emision=date(2026, 3, 1), fecha_vencimiento=date(2026, 3, 1), concepto="Alquiler",
            lineas=[{"cuenta": self.energia, "centro_costo": self.ti, "monto": D("300")}],
        )
        self.assertEqual((recibo.compras_gravadas, recibo.compras_exentas, recibo.monto_total), (D("0.00"), D("300.00"), D("300.00")))

    def test_anulacion_revierte_iva_y_retencion(self):
        cxp = self.ccf(aplica_retencion=True)
        self.assertEqual((self.saldo(self.iva), self.saldo(self.retenido)), (D("130.00"), D("-10.00")))
        cpp.anular_cuenta_por_pagar(cxp, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 2))
        self.assertEqual((self.saldo(self.iva), self.saldo(self.retenido)), (D("0.00"), D("0.00")))

    def test_pago_por_el_neto_de_retencion(self):
        cxp = self.ccf(aplica_retencion=True)  # 1000 + 130 − 10
        pago = self.pagar(cxp, "1120.00", fecha=date(2026, 3, 10))
        cxp.refresh_from_db()
        self.assertEqual((pago.monto, cxp.saldo, cxp.estado), (D("1120.00"), D("0.00"), CuentaPorPagar.Estado.PAGADA))

    def test_oracle_exige_que_el_desglose_cuadre(self):
        cxp = self.ccf()
        asiento = contabilidad.contabilizar_asiento(contabilidad.crear_asiento(
            usuario=self.contador, fecha=date(2026, 3, 1), concepto="Prueba", lineas=[
                {"cuenta": self.bancos, "debe": D("1"), "haber": 0}, {"cuenta": self.cxp, "debe": 0, "haber": D("1")},
            ],
        ), usuario=self.contador)
        datos = dict(
            proveedor=self.proveedor, tipo_documento="CCF", numero_documento="Z", fecha_emision=date(2026, 3, 1),
            fecha_vencimiento=date(2026, 3, 1), concepto="x", cuenta_pasivo=self.cxp, asiento=asiento,
            creado_por=self.contador, modificado_por=self.contador,
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            CuentaPorPagar.objects.create(compras_gravadas=D("100"), iva_credito_fiscal=D("13"), monto_total=D("100"), saldo=D("100"), **datos)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CuentaPorPagar.objects.create(**{**datos, "tipo_documento": "FACTURA"}, compras_gravadas=D("100"),
                                          iva_credito_fiscal=D("13"), monto_total=D("113"), saldo=D("113"))
        # El desglose de un documento registrado tampoco se modifica (TRG_CXP_REGLAS).
        with self.assertRaises(DatabaseError), transaction.atomic():
            CuentaPorPagar.objects.filter(pk=cxp.pk).update(compras_gravadas=D("900"), compras_exentas=D("100"))

    def test_api_registra_ccf_con_desglose(self):
        client = APIClient()
        client.force_authenticate(self.tesorero)
        resp = client.post("/api/cuentas-por-pagar/", {
            "proveedor": self.proveedor.pk, "tipo_documento": "CCF", "numero_documento": "CCF-API",
            "fecha_emision": "2026-03-01", "fecha_vencimiento": "2026-03-31", "concepto": "Energía",
            "compras_exentas": "50.00", "aplica_retencion": True,
            "lineas": [{"cuenta": self.energia.pk, "centro_costo": self.ti.pk, "monto": "250.00"}],
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        d = resp.data
        self.assertEqual(
            (d["compras_gravadas"], d["compras_exentas"], d["iva_credito_fiscal"], d["iva_retenido"], d["monto_total"]),
            ("200.00", "50.00", "26.00", "2.00", "274.00"),
        )
        self.assertEqual([l["cuenta"]["codigo"] for l in d["lineas"]], ["5201"])  # la imputación no incluye el IVA


class CatalogoBaseIvaTests(TestCase):
    def test_catalogo_base_crea_cuentas_de_iva(self):
        User.objects.create_user(username="contador")
        call_command("cargar_catalogo_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        for codigo, tipo in (("1403", Cuenta.Tipo.ACTIVO), ("2405", Cuenta.Tipo.PASIVO)):
            cuenta = Cuenta.objects.get(codigo=codigo)
            self.assertEqual((cuenta.tipo, cuenta.acepta_movimientos, cuenta.exenta_centro_costo), (tipo, True, True), codigo)


@override_settings(EMPRESA_NOMBRE="Banco de Prueba, S.A.", EMPRESA_NIT="0614-010101-101-1", EMPRESA_NRC="1111-1")
class LibroComprasTests(BaseIva):
    def setUp(self):
        super().setUp()
        otro = proveedores.crear_proveedor(usuario=self.contador, nit="0614-020202-102-2", nombre="Papelería Central", nrc="22222-2")
        self.a = self.ccf(numero="CCF-10", emision=date(2026, 3, 15), gravadas="200.00", exentas="50.00")
        self.b = self.ccf(numero="CCF-05", emision=date(2026, 3, 2), aplica_retencion=True)
        self.c = cpp.registrar_cuenta_por_pagar(
            usuario=self.contador, proveedor=otro, tipo_documento="CCF", numero_documento="P-1", fecha_emision=date(2026, 3, 20),
            fecha_vencimiento=date(2026, 3, 30), concepto="Resmas", compras_gravadas=D("100.00"),
            lineas=[{"cuenta": self.papeleria, "centro_costo": self.rrhh, "monto": D("100.00")}],
        )
        # No se anotan: anulado, factura y otro mes.
        anulado = self.ccf(numero="CCF-99", emision=date(2026, 3, 3))
        cpp.anular_cuenta_por_pagar(anulado, usuario=self.contador, motivo="Duplicado", fecha=date(2026, 3, 4))
        self.registrar(numero="F-1")
        self.ccf(numero="CCF-ABR", emision=date(2026, 4, 1))
        self.client = APIClient()
        self.client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))

    def test_libro_del_mes(self):
        libro = libro_compras(anio=2026, mes=3)
        self.assertEqual(libro["periodo"], "Marzo 2026")
        self.assertEqual([(f["correlativo"], f["numero_documento"]) for f in libro["filas"]], [(1, "CCF-05"), (2, "CCF-10"), (3, "P-1")])
        primera = libro["filas"][0]
        self.assertEqual((primera["proveedor"]["nrc"], primera["proveedor"]["nit"]), ("123456-7", "0614-010190-101-3"))
        self.assertEqual(
            (primera["compras_gravadas"], primera["iva_credito_fiscal"], primera["iva_retenido"], primera["total"]),
            ("1000.00", "130.00", "10.00", "1130.00"),
        )
        self.assertEqual(libro["totales"], {
            "compras_exentas": "50.00", "compras_gravadas": "1300.00", "iva_credito_fiscal": "169.00",
            "iva_retenido": "10.00", "total": "1519.00",
        })

    def test_iva_del_libro_igual_a_la_cuenta(self):
        # Crédito fiscal del libro = movimiento neto de la cuenta 1403 en marzo (lo anulado se compensa).
        lineas = LineaAsiento.objects.filter(cuenta=self.iva, asiento__estado="CONTABILIZADO", asiento__fecha__month=3)
        self.assertEqual(sum((l.debe - l.haber for l in lineas), D(0)), D(libro_compras(anio=2026, mes=3)["totales"]["iva_credito_fiscal"]))

    def test_api(self):
        resp = self.client.get("/api/tesoreria/libro-compras/", {"anio": 2026, "mes": 3})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data["filas"]), 3)
        self.assertEqual(self.client.get("/api/tesoreria/libro-compras/", {"anio": 2026, "mes": 13}).status_code, 400)
        self.assertEqual(self.client.get("/api/tesoreria/libro-compras/").status_code, 400)
        self.assertEqual(APIClient().get("/api/tesoreria/libro-compras/", {"anio": 2026, "mes": 3}).status_code, 401)

    def test_exportar_excel(self):
        resp = self.client.get("/api/tesoreria/libro-compras/exportar/", {"anio": 2026, "mes": 3})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("libro_compras_2026_03.xlsx", resp["Content-Disposition"])
        ws = load_workbook(BytesIO(resp.content)).active
        self.assertEqual((ws["A1"].value, ws["A3"].value, ws["A4"].value), ("Banco de Prueba, S.A.", "Libro de compras", "Mes de Marzo 2026"))
        titulos = [c.value for c in ws[FILA_TITULOS]]
        self.assertEqual(titulos, [
            "N.º", "Fecha de emisión", "Tipo de documento", "N.º de documento", "NRC", "NIT", "Nombre del proveedor",
            "Compras exentas", "Compras gravadas", "IVA crédito fiscal", "Retención / percepción 1 %", "Total compras",
        ])
        filas = [list(f) for f in ws.iter_rows(min_row=FILA_TITULOS + 1, values_only=True)]
        self.assertEqual(filas[0][:7], [1, filas[0][1], "CCF", "CCF-05", "123456-7", "0614-010190-101-3", "Distribuidora Eléctrica"])
        self.assertEqual(filas[0][1].date(), date(2026, 3, 2))
        total = filas[-1]
        self.assertIn("TOTALES DEL MES (3 documentos)", total[6])
        self.assertEqual(total[7:], [50, 1300, 169, 10, 1519])
        self.assertEqual(ws.cell(row=FILA_TITULOS + 1, column=10).number_format, FORMATO_MONTO)
