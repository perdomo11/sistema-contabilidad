"""Pruebas de T7.3: clientes, documentos de venta con IVA débito fiscal y libro de ventas."""
from datetime import date
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, override_settings
from openpyxl import load_workbook
from rest_framework.test import APIClient

from centros_costo import services as centros
from centros_costo.models import CentroCosto
from config.excel import FILA_TITULOS
from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta, LineaAsiento
from reportes import integridad
from usuarios import roles
from usuarios.models import Bitacora

from . import documentos as ventas
from . import services
from .libro import libro_ventas
from .models import Cliente, DocumentoVenta

D = Decimal
Estado = DocumentoVenta.Estado


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BaseVentas(TestCase):
    def setUp(self):
        self.contador = c = crear_usuario("contador", roles.CONTADOR)
        self.tesorero = crear_usuario("tesorero", roles.TESORERO)
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(usuario=c, codigo="1103", nombre="Bancos", padre=activo, exenta_centro_costo=True)
        self.cxc = contabilidad.crear_cuenta(usuario=c, codigo="1401", nombre="Cuentas por cobrar", padre=activo, exenta_centro_costo=True)
        pasivo = contabilidad.crear_cuenta(usuario=c, codigo="2", nombre="Pasivo", tipo=Cuenta.Tipo.PASIVO, acepta_movimientos=False)
        self.iva = contabilidad.crear_cuenta(usuario=c, codigo="2406", nombre="IVA débito fiscal", padre=pasivo, exenta_centro_costo=True)
        ingresos = contabilidad.crear_cuenta(usuario=c, codigo="4", nombre="Ingresos", tipo=Cuenta.Tipo.INGRESO, acepta_movimientos=False)
        self.intereses = contabilidad.crear_cuenta(usuario=c, codigo="4101", nombre="Intereses", padre=ingresos)
        self.comisiones = contabilidad.crear_cuenta(usuario=c, codigo="4201", nombre="Comisiones", padre=ingresos)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)
        kw = {"usuario": c, "tipo": CentroCosto.Tipo.INGRESO, "clase": CentroCosto.Clase.DEPARTAMENTO, "vigente_desde": date(2026, 1, 1)}
        self.creditos = centros.crear_centro(codigo="01", nombre="Créditos", **kw)
        self.agencia = centros.crear_centro(codigo="02", nombre="Agencia", **kw)
        self.empresa = services.crear_cliente(usuario=c, nombre="Comercial Los Pinos, S.A. de C.V.", tipo="CONTRIBUYENTE",
                                              nit="0614-120598-104-6", nrc="245871-3")
        self.persona = services.crear_cliente(usuario=c, nombre="Clientes varios", tipo="CONSUMIDOR_FINAL")

    def emitir(self, tipo="CCF", numero="CCF-0001", fecha=date(2026, 3, 5), cliente=None, lineas=None, **kwargs):
        lineas = lineas or [
            {"cuenta": self.comisiones, "centro_costo": self.agencia, "monto": D("200.00")},
            {"cuenta": self.intereses, "centro_costo": self.creditos, "monto": D("800.00"), "exenta": True},
        ]
        return ventas.registrar_documento_venta(
            usuario=kwargs.pop("usuario", self.contador), cliente=cliente or self.empresa, tipo_documento=tipo,
            numero_documento=numero, fecha_emision=fecha, concepto="Servicios bancarios", lineas=lineas, **kwargs,
        )

    def lineas(self, asiento):
        filas = asiento.lineas.order_by("numero_linea").values_list("cuenta__codigo", "centro_costo__codigo", "debe", "haber")
        return [(cuenta, centro or None, debe, haber) for cuenta, centro, debe, haber in filas]

    def saldo(self, cuenta):
        lineas = LineaAsiento.objects.filter(cuenta=cuenta, asiento__estado="CONTABILIZADO")
        return sum((l.haber - l.debe for l in lineas), D(0))


class ClienteTests(BaseVentas):
    def test_contribuyente_exige_nit_y_nrc(self):
        with self.assertRaises(ValidationError) as e:
            services.crear_cliente(usuario=self.contador, nombre="Sin NRC", tipo="CONTRIBUYENTE", nit="0614-010101-101-1")
        self.assertIn("nrc", e.exception.message_dict)
        with self.assertRaises(ValidationError):
            services.crear_cliente(usuario=self.contador, nombre="Duplicado", tipo="CONTRIBUYENTE", nit="0614-120598-104-6", nrc="1-1")
        with self.assertRaises(ValidationError):
            services.crear_cliente(usuario=self.contador, nombre="NIT malo", tipo="CONSUMIDOR_FINAL", nit="ABC")

    def test_consumidores_finales_sin_nit(self):
        otro = services.crear_cliente(usuario=self.contador, nombre="María Pérez", tipo="CONSUMIDOR_FINAL")
        self.assertIsNone(otro.nit)  # varios clientes sin NIT no chocan con la unicidad
        self.assertEqual(Cliente.objects.filter(tipo="CONSUMIDOR_FINAL").count(), 2)

    def test_restriccion_en_bd(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cliente.objects.create(nombre="X", tipo="CONTRIBUYENTE", creado_por=self.contador, modificado_por=self.contador)

    def test_cliente_con_documentos_no_se_elimina_ni_cambia_nit(self):
        self.emitir()
        with self.assertRaises(ValidationError):
            services.eliminar_cliente(self.empresa, usuario=self.contador)
        with self.assertRaises(ValidationError):
            services.actualizar_cliente(self.empresa, usuario=self.contador, datos={"nrc": "999-9"})
        cliente = services.actualizar_cliente(self.empresa, usuario=self.contador, datos={"activo": False})
        self.assertFalse(cliente.activo)
        self.assertTrue(Bitacora.objects.filter(entidad="cliente", accion="MODIFICAR").exists())


class DocumentoVentaTests(BaseVentas):
    def test_ccf_genera_asiento_con_iva_debito(self):
        doc = self.emitir()
        self.assertEqual(
            (doc.ventas_gravadas, doc.ventas_exentas, doc.iva_debito_fiscal, doc.total),
            (D("200.00"), D("800.00"), D("26.00"), D("1026.00")),
        )
        self.assertEqual((doc.asiento.estado, doc.asiento.referencia), (Asiento.Estado.CONTABILIZADO, "CCF CCF-0001"))
        self.assertEqual(self.lineas(doc.asiento), [
            ("1103", None, D("1026.00"), D("0.00")),
            ("4201", "02", D("0.00"), D("200.00")),
            ("4101", "01", D("0.00"), D("800.00")),
            ("2406", None, D("0.00"), D("26.00")),
        ])
        self.assertTrue(Bitacora.objects.filter(entidad="documento_venta", accion="CREAR", objeto_id=str(doc.pk)).exists())

    def test_factura_a_credito_y_solo_exenta(self):
        doc = self.emitir(tipo="FACTURA", numero="F-1", cliente=self.persona, cuenta_cobro=self.cxc,
                          lineas=[{"cuenta": self.intereses, "centro_costo": self.creditos, "monto": D("50"), "exenta": True}])
        self.assertEqual((doc.iva_debito_fiscal, doc.total), (D("0.00"), D("50.00")))
        self.assertEqual([l[0] for l in self.lineas(doc.asiento)], ["1401", "4101"])  # sin línea de IVA

    def test_validaciones(self):
        with self.assertRaises(ValidationError) as e:
            self.emitir(cliente=self.persona)  # CCF a consumidor final
        self.assertIn("contribuyentes", str(e.exception))
        with self.assertRaises(ValidationError):
            self.emitir(numero="X1", lineas=[{"cuenta": self.bancos, "monto": D("10")}])  # no es ingreso
        with self.assertRaises(ValidationError):
            self.emitir(numero="X2", lineas=[{"cuenta": self.comisiones, "monto": D("10")}])  # ingreso sin centro
        with self.assertRaises(ValidationError):
            self.emitir(numero="X3", lineas=[{"cuenta": self.comisiones, "centro_costo": self.agencia, "monto": D("10.001")}])
        with self.assertRaises(ValidationError):
            self.emitir(numero="X4", cuenta_cobro=self.comisiones)  # cobro a una cuenta de ingreso
        with self.assertRaises(ValidationError):
            self.emitir(numero="X5", fecha=date(2025, 12, 1))  # sin periodo
        self.assertEqual(DocumentoVenta.objects.count(), 0)

    def test_numero_no_se_reutiliza(self):
        doc = self.emitir()
        ventas.anular_documento_venta(doc, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 6))
        with self.assertRaises(ValidationError) as e:
            self.emitir()
        self.assertIn("no se reutiliza", str(e.exception))
        self.assertEqual(self.emitir(tipo="FACTURA", cliente=self.persona).tipo_documento, "FACTURA")  # otro tipo, mismo número

    def test_anular_revierte_el_asiento(self):
        doc = self.emitir()
        with self.assertRaises(ValidationError):
            ventas.anular_documento_venta(doc, usuario=self.contador, motivo="")
        doc = ventas.anular_documento_venta(doc, usuario=self.contador, motivo="Cliente equivocado", fecha=date(2026, 3, 6))
        self.assertEqual((doc.estado, doc.asiento_anulacion.reversion_de_id), (Estado.ANULADO, doc.asiento_id))
        self.assertEqual((self.saldo(self.iva), self.saldo(self.comisiones), self.saldo(self.bancos)), (D(0), D(0), D(0)))
        with self.assertRaises(ValidationError):
            ventas.anular_documento_venta(doc, usuario=self.contador, motivo="Otra vez")

    def test_asiento_no_se_revierte_desde_asientos(self):
        doc = self.emitir()
        with self.assertRaises(ValidationError) as e:
            contabilidad.revertir_asiento(doc.asiento, usuario=self.contador, motivo="x", fecha=date(2026, 3, 6))
        self.assertIn("Ventas", e.exception.messages[0])

    def test_reglas_en_bd(self):
        doc = self.emitir()
        with self.assertRaises(DatabaseError), transaction.atomic():
            DocumentoVenta.objects.filter(pk=doc.pk).update(total=D("1"), ventas_exentas=D("0"), iva_debito_fiscal=D("0"), ventas_gravadas=D("1"))
        with self.assertRaises(DatabaseError), transaction.atomic():
            DocumentoVenta.objects.filter(pk=doc.pk).delete()
        datos = dict(cliente=self.empresa, tipo_documento="CCF", numero_documento="Z", fecha_emision=date(2026, 3, 5), concepto="x",
                     cuenta_cobro=self.bancos, asiento=self.emitir(numero="CCF-0002").asiento, creado_por=self.contador)
        with self.assertRaises(IntegrityError), transaction.atomic():  # total ≠ gravadas + exentas + IVA
            DocumentoVenta.objects.create(ventas_gravadas=D("100"), iva_debito_fiscal=D("13"), total=D("100"), **datos)
        with self.assertRaises(IntegrityError), transaction.atomic():  # número repetido
            DocumentoVenta.objects.create(**{**datos, "numero_documento": "CCF-0001"}, ventas_exentas=D("1"), total=D("1"))
        ventas.anular_documento_venta(doc, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 6))
        with self.assertRaises(DatabaseError), transaction.atomic():
            DocumentoVenta.objects.filter(pk=doc.pk).update(motivo_anulacion="cambio")

    def test_integridad(self):
        self.emitir()
        anulado = self.emitir(numero="CCF-0002")
        ventas.anular_documento_venta(anulado, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 6))
        r = {x["codigo"]: x for x in integridad.verificar(2026)}["VENTAS"]
        self.assertEqual((r["estado"], r["revisados"]), (integridad.OK, 2))


class VentasApiTests(BaseVentas):
    def test_flujo_por_api(self):
        client = APIClient()
        client.force_authenticate(self.tesorero)
        resp = client.post("/api/clientes/", {"nombre": "Ana López", "tipo": "CONSUMIDOR_FINAL"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        resp = client.post("/api/ventas/documentos/", {
            "cliente": resp.data["id"], "tipo_documento": "FACTURA", "numero_documento": "F-0010", "fecha_emision": "2026-03-10",
            "concepto": "Comisión por remesa",
            "lineas": [{"cuenta": self.comisiones.pk, "centro_costo": self.agencia.pk, "monto": "10.00"}],
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual((resp.data["iva_debito_fiscal"], resp.data["total"]), ("1.30", "11.30"))
        self.assertEqual([l["cuenta"]["codigo"] for l in resp.data["lineas"]], ["4201"])
        pk = resp.data["id"]
        lista = client.get("/api/ventas/documentos/", {"tipo_documento": "FACTURA"}).data
        self.assertEqual(lista["count"], 1)
        resp = client.post(f"/api/ventas/documentos/{pk}/anular/", {"motivo": "Error", "fecha": "2026-03-11"}, format="json")
        self.assertEqual((resp.status_code, resp.data["estado"]), (200, "ANULADO"), resp.data)

    def test_permisos(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))
        self.assertEqual(client.get("/api/clientes/").status_code, 200)
        self.assertEqual(client.post("/api/clientes/", {"nombre": "X", "tipo": "CONSUMIDOR_FINAL"}, format="json").status_code, 403)
        self.assertEqual(APIClient().get("/api/ventas/documentos/").status_code, 401)


@override_settings(EMPRESA_NOMBRE="Banco de Prueba, S.A.", EMPRESA_NIT="0614-010101-101-1", EMPRESA_NRC="1111-1")
class LibroVentasTests(BaseVentas):
    def setUp(self):
        super().setUp()
        self.emitir(numero="CCF-0002", fecha=date(2026, 3, 20))
        self.emitir(numero="CCF-0001", fecha=date(2026, 3, 5))
        anulado = self.emitir(numero="CCF-0003", fecha=date(2026, 3, 21))
        ventas.anular_documento_venta(anulado, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 22))
        self.emitir(numero="CCF-0004", fecha=date(2026, 4, 1))  # otro mes
        comision = [{"cuenta": self.comisiones, "centro_costo": self.agencia, "monto": D("10.00")}]
        for numero in ("F-0001", "F-0002", "F-0003"):
            self.emitir(tipo="FACTURA", numero=numero, cliente=self.persona, fecha=date(2026, 3, 10), lineas=comision)
        anulada = self.emitir(tipo="FACTURA", numero="F-0004", cliente=self.persona, fecha=date(2026, 3, 10), lineas=comision)
        ventas.anular_documento_venta(anulada, usuario=self.contador, motivo="Error", fecha=date(2026, 3, 10))
        self.emitir(tipo="FACTURA", numero="F-0005", cliente=self.persona, fecha=date(2026, 3, 11), lineas=[
            {"cuenta": self.intereses, "centro_costo": self.creditos, "monto": D("40.00"), "exenta": True},
        ])

    def test_contribuyentes(self):
        ccf = libro_ventas(anio=2026, mes=3)["contribuyentes"]
        self.assertEqual([(f["correlativo"], f["numero_documento"], f["anulado"]) for f in ccf["filas"]],
                         [(1, "CCF-0001", False), (2, "CCF-0002", False), (3, "CCF-0003", True)])
        self.assertEqual((ccf["filas"][0]["cliente"]["nrc"], ccf["filas"][2]["total"]), ("245871-3", "0.00"))
        self.assertEqual(ccf["totales"], {"ventas_exentas": "1600.00", "ventas_gravadas": "400.00", "iva_debito_fiscal": "52.00", "total": "2052.00"})

    def test_consumidor_final_por_dia(self):
        cf = libro_ventas(anio=2026, mes=3)["consumidor_final"]
        dia = cf["filas"][0]
        self.assertEqual((dia["fecha"], dia["del_numero"], dia["al_numero"], dia["documentos"], dia["anulados"]),
                         ("2026-03-10", "F-0001", "F-0004", 4, 1))
        # Gravadas con IVA incluido: 3 × 11.30
        self.assertEqual((dia["ventas_gravadas"], dia["iva_debito_fiscal"], dia["total"]), ("33.90", "3.90", "33.90"))
        self.assertEqual((cf["filas"][1]["ventas_exentas"], cf["totales"]["total"]), ("40.00", "73.90"))

    def test_debito_fiscal_igual_a_la_cuenta(self):
        libro = libro_ventas(anio=2026, mes=3)
        lineas = LineaAsiento.objects.filter(cuenta=self.iva, asiento__estado="CONTABILIZADO", asiento__fecha__month=3)
        self.assertEqual(sum((l.haber - l.debe for l in lineas), D(0)), D(libro["resumen"]["iva_debito_fiscal"]))
        self.assertEqual(libro["resumen"]["iva_debito_fiscal"], "55.90")

    def test_api_y_excel(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))
        self.assertEqual(client.get("/api/ventas/libro/", {"anio": 2026, "mes": 3}).status_code, 200)
        self.assertEqual(client.get("/api/ventas/libro/", {"anio": 2026, "mes": 0}).status_code, 400)
        resp = client.get("/api/ventas/libro/exportar/", {"anio": 2026, "mes": 3})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("libro_ventas_2026_03.xlsx", resp["Content-Disposition"])
        libro = load_workbook(BytesIO(resp.content))
        self.assertEqual(libro.sheetnames, ["Contribuyentes", "Consumidor final"])
        ccf, cf = libro["Contribuyentes"], libro["Consumidor final"]
        self.assertEqual((ccf["A1"].value, ccf["A3"].value, ccf["A4"].value),
                         ("Banco de Prueba, S.A.", "Libro de ventas a contribuyentes", "Mes de Marzo 2026"))
        self.assertEqual(ccf.cell(row=FILA_TITULOS, column=9).value, "IVA débito fiscal")
        filas = [list(f) for f in ccf.iter_rows(min_row=FILA_TITULOS + 1, values_only=True)]
        self.assertIn("(ANULADO)", filas[2][5])
        self.assertEqual(filas[-1][6:], [1600, 400, 52, 2052])
        filas = [list(f) for f in cf.iter_rows(min_row=FILA_TITULOS + 1, values_only=True)]
        self.assertEqual(filas[0][1:5], ["F-0001", "F-0004", 4, 1])
        self.assertEqual(filas[-1][3:], [5, 1, 40, 33.9, 3.9, 73.9])
