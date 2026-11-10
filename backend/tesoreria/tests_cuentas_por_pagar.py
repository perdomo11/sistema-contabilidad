"""Pruebas de T5.1: cuentas por pagar con vencimientos."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from centros_costo import services as centros
from centros_costo.models import CentroCosto
from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta
from usuarios import roles
from usuarios.models import Bitacora

from . import cuentas_por_pagar as cpp
from . import services as proveedores
from .models import CuentaPorPagar, PagoCuentaPorPagar

D = Decimal
Estado = CuentaPorPagar.Estado


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BaseCxP(TestCase):
    def setUp(self):
        self.contador = c = crear_usuario("contador", roles.CONTADOR)
        self.tesorero = crear_usuario("tesorero", roles.TESORERO)
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(usuario=c, codigo="1103", nombre="Bancos", padre=activo, exenta_centro_costo=True)
        self.equipo = contabilidad.crear_cuenta(usuario=c, codigo="1201", nombre="Equipo", padre=activo, exenta_centro_costo=True)
        pasivo = contabilidad.crear_cuenta(usuario=c, codigo="2", nombre="Pasivo", tipo=Cuenta.Tipo.PASIVO, acepta_movimientos=False)
        self.cxp = contabilidad.crear_cuenta(usuario=c, codigo="2401", nombre="CxP proveedores", padre=pasivo, exenta_centro_costo=True)
        gastos = contabilidad.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO, acepta_movimientos=False)
        self.energia = contabilidad.crear_cuenta(usuario=c, codigo="5201", nombre="Energía", padre=gastos)
        self.papeleria = contabilidad.crear_cuenta(usuario=c, codigo="5202", nombre="Papelería", padre=gastos)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)
        kw = {"usuario": c, "tipo": CentroCosto.Tipo.COSTO, "clase": CentroCosto.Clase.DEPARTAMENTO, "vigente_desde": date(2026, 1, 1)}
        self.ti = centros.crear_centro(codigo="01", nombre="TI", **kw)
        self.rrhh = centros.crear_centro(codigo="02", nombre="RR. HH.", **kw)
        self.proveedor = proveedores.crear_proveedor(usuario=c, nit="0614-010190-101-3", nombre="Distribuidora Eléctrica")

    def registrar(self, numero="F-001", total=None, emision=date(2026, 3, 1), vence=date(2026, 3, 31), lineas=None, **kwargs):
        lineas = lineas or [
            {"cuenta": self.energia, "centro_costo": self.ti, "monto": D("600.00")},
            {"cuenta": self.papeleria, "centro_costo": self.rrhh, "monto": D("400.00"), "descripcion": "Resmas"},
        ]
        return cpp.registrar_cuenta_por_pagar(
            usuario=kwargs.pop("usuario", self.contador), proveedor=self.proveedor, tipo_documento="FACTURA",
            numero_documento=numero, fecha_emision=emision, fecha_vencimiento=vence, concepto="Servicios de marzo",
            lineas=lineas, **kwargs,
        )

    def pagar(self, cxp, monto, fecha=date(2026, 3, 20)):
        return cpp.registrar_pago(cxp, usuario=self.tesorero, fecha=fecha, monto=D(monto), cuenta_banco=self.bancos, referencia="TRF-1")

    def lineas(self, asiento):
        filas = asiento.lineas.order_by("numero_linea").values_list("cuenta__codigo", "centro_costo__codigo", "debe", "haber")
        # En Oracle un texto nulo llega como "".
        return [(cuenta, centro or None, debe, haber) for cuenta, centro, debe, haber in filas]


class RegistroTests(BaseCxP):
    def test_registro_genera_asiento_contabilizado(self):
        cxp = self.registrar()
        self.assertEqual((cxp.monto_total, cxp.saldo, cxp.estado), (D("1000.00"), D("1000.00"), Estado.PENDIENTE))
        a = cxp.asiento
        self.assertEqual((a.estado, a.fecha, a.proveedor_id, a.referencia), (Asiento.Estado.CONTABILIZADO, date(2026, 3, 1), self.proveedor.pk, "FACTURA F-001"))
        self.assertEqual(self.lineas(a), [
            ("5201", "01", D("600.00"), D("0.00")),
            ("5202", "02", D("400.00"), D("0.00")),
            ("2401", None, D("0.00"), D("1000.00")),
        ])

    def test_validaciones(self):
        self.registrar()
        with self.assertRaises(ValidationError):
            self.registrar()  # duplicado
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-002", vence=date(2026, 2, 1))
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-003", lineas=[{"cuenta": self.energia, "centro_costo": self.ti, "monto": D("0")}])
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-004", lineas=[{"cuenta": self.energia, "monto": D("10")}])  # gasto sin centro
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-005", cuenta_pasivo=self.bancos)  # no es pasivo
        with self.assertRaises(ValidationError):
            self.registrar(numero="F-006", emision=date(2025, 12, 1), vence=date(2025, 12, 31))  # sin periodo
        self.assertEqual(CuentaPorPagar.objects.count(), 1)

    def test_imputacion_a_activo(self):
        cxp = self.registrar(numero="F-010", lineas=[{"cuenta": self.equipo, "monto": D("2500")}])
        self.assertEqual(self.lineas(cxp.asiento)[0], ("1201", None, D("2500.00"), D("0.00")))

    def test_anular_documento(self):
        cxp = self.registrar()
        with self.assertRaises(ValidationError):
            cpp.anular_cuenta_por_pagar(cxp, usuario=self.contador, motivo="")
        cxp = cpp.anular_cuenta_por_pagar(cxp, usuario=self.contador, motivo="Monto errado", fecha=date(2026, 3, 5))
        self.assertEqual(cxp.estado, Estado.ANULADA)
        self.assertEqual(cxp.asiento_anulacion.reversion_de_id, cxp.asiento_id)
        # Anulado, el mismo número se puede volver a registrar.
        self.assertEqual(self.registrar().estado, Estado.PENDIENTE)

    def test_asiento_no_se_revierte_desde_asientos(self):
        cxp = self.registrar()
        with self.assertRaises(ValidationError) as e:
            contabilidad.revertir_asiento(cxp.asiento, usuario=self.contador, motivo="x", fecha=date(2026, 3, 5))
        self.assertIn("Tesorería", e.exception.messages[0])


class PagoTests(BaseCxP):
    def test_pagos_parcial_y_total(self):
        cxp = self.registrar()
        pago = self.pagar(cxp, "300")
        cxp.refresh_from_db()
        self.assertEqual((cxp.saldo, cxp.estado), (D("700.00"), Estado.PARCIAL))
        self.assertEqual(self.lineas(pago.asiento), [("2401", None, D("300.00"), D("0.00")), ("1103", None, D("0.00"), D("300.00"))])
        with self.assertRaises(ValidationError):
            self.pagar(cxp, "700.01")
        self.pagar(cxp, "700")
        cxp.refresh_from_db()
        self.assertEqual((cxp.saldo, cxp.estado), (D("0.00"), Estado.PAGADA))
        with self.assertRaises(ValidationError):
            self.pagar(cxp, "1")

    def test_validaciones_de_pago(self):
        cxp = self.registrar()
        with self.assertRaises(ValidationError):
            self.pagar(cxp, "100", fecha=date(2026, 2, 28))  # antes de la emisión
        with self.assertRaises(ValidationError):
            cpp.registrar_pago(cxp, usuario=self.tesorero, fecha=date(2026, 3, 20), monto=D("1"), cuenta_banco=self.energia)

    def test_anular_pago_devuelve_saldo(self):
        cxp = self.registrar()
        pago = self.pagar(cxp, "1000")
        with self.assertRaises(ValidationError):
            cpp.anular_cuenta_por_pagar(cxp, usuario=self.contador, motivo="x", fecha=date(2026, 3, 25))  # tiene pagos
        pago = cpp.anular_pago(pago, usuario=self.tesorero, motivo="Cheque rechazado", fecha=date(2026, 3, 25))
        cxp.refresh_from_db()
        self.assertEqual((pago.estado, cxp.saldo, cxp.estado), ("ANULADO", D("1000.00"), Estado.PENDIENTE))
        self.assertEqual(pago.asiento_anulacion.reversion_de_id, pago.asiento_id)
        with self.assertRaises(ValidationError):
            cpp.anular_pago(pago, usuario=self.tesorero, motivo="otra vez", fecha=date(2026, 3, 25))
        cpp.anular_cuenta_por_pagar(cxp, usuario=self.contador, motivo="Ya sin pagos", fecha=date(2026, 3, 25))

    def test_bitacora(self):
        cxp = self.registrar()
        pago = self.pagar(cxp, "100")
        cpp.anular_pago(pago, usuario=self.tesorero, motivo="Error", fecha=date(2026, 3, 25))
        acciones = list(Bitacora.objects.filter(entidad__in=["cuenta_por_pagar", "pago_cxp"]).order_by("id").values_list("entidad", "accion"))
        self.assertEqual(acciones, [("cuenta_por_pagar", "CREAR"), ("pago_cxp", "CREAR"), ("pago_cxp", "ANULAR")])


class VencimientosTests(BaseCxP):
    def setUp(self):
        super().setUp()
        uno = [{"cuenta": self.energia, "centro_costo": self.ti, "monto": D("100")}]
        self.registrar(numero="A", vence=date(2026, 3, 31), lineas=uno)  # 61 días vencida al 31/05
        self.registrar(numero="B", vence=date(2026, 5, 20), lineas=uno)  # 11 días vencida
        self.registrar(numero="C", vence=date(2026, 6, 5), lineas=uno)  # por vencer (5 días)
        self.registrar(numero="D", vence=date(2026, 7, 31), lineas=uno)  # al día
        self.pagar(CuentaPorPagar.objects.get(numero_documento="B"), "40", fecha=date(2026, 5, 2))
        self.corte = date(2026, 5, 31)

    def test_situacion(self):
        qs = cpp.consultar_cuentas_por_pagar(fecha=self.corte)
        situacion = {c.numero_documento: cpp.situacion_vencimiento(c, self.corte) for c in qs}
        self.assertEqual(situacion, {"A": ("VENCIDA", 61), "B": ("VENCIDA", 11), "C": ("POR_VENCER", 5), "D": ("AL_DIA", 61)})
        vencidas = cpp.consultar_cuentas_por_pagar(fecha=self.corte, vencimiento="VENCIDA")
        self.assertEqual([c.numero_documento for c in vencidas], ["A", "B"])

    def test_resumen_y_antiguedad(self):
        r = cpp.resumen_cuentas_por_pagar(fecha=self.corte)
        self.assertEqual((r["pendiente"], r["vencido"], r["por_vencer"], r["al_dia"]), ("360.00", "160.00", "100.00", "100.00"))
        self.assertEqual({a["tramo"]: a["monto"] for a in r["antiguedad"]}, {"1-30": "60.00", "31-60": "0.00", "61-90": "100.00", "mas_90": "0.00"})
        self.assertEqual(r["documentos"], {"total": 4, "vencidos": 2, "por_vencer": 1})
        self.assertEqual(r["pagado_en_el_mes"], "40.00")


class CxPBaseDeDatosTests(BaseCxP):
    def test_reglas_en_bd(self):
        cxp = self.registrar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            CuentaPorPagar.objects.filter(pk=cxp.pk).update(saldo=D("1000.01"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            CuentaPorPagar.objects.filter(pk=cxp.pk).update(estado=Estado.PAGADA)  # saldo no es cero
        with self.assertRaises(DatabaseError), transaction.atomic():
            CuentaPorPagar.objects.filter(pk=cxp.pk).update(monto_total=D("5"), saldo=D("5"))
        with self.assertRaises(DatabaseError), transaction.atomic():
            CuentaPorPagar.objects.filter(pk=cxp.pk).delete()
        pago = self.pagar(cxp, "10")
        with self.assertRaises(DatabaseError), transaction.atomic():
            PagoCuentaPorPagar.objects.filter(pk=pago.pk).update(monto=D("20"))
        with self.assertRaises(DatabaseError), transaction.atomic():
            PagoCuentaPorPagar.objects.filter(pk=pago.pk).delete()


class CxPApiTests(BaseCxP):
    def test_flujo_tesorero(self):
        client = APIClient()
        client.force_authenticate(self.tesorero)
        cuerpo = {
            "proveedor": self.proveedor.pk, "tipo_documento": "CCF", "numero_documento": "CCF-77",
            "fecha_emision": "2026-03-01", "fecha_vencimiento": "2026-03-31", "concepto": "Energía",
            "lineas": [{"cuenta": self.energia.pk, "centro_costo": self.ti.pk, "monto": "250.00"}],
        }
        resp = client.post("/api/cuentas-por-pagar/", cuerpo, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(resp.data["lineas"][0]["centro_costo"]["codigo"], "01")
        resp = client.post(f"/api/cuentas-por-pagar/{pk}/pagos/", {"fecha": "2026-03-15", "monto": "250", "cuenta_banco": self.bancos.pk}, format="json")
        self.assertEqual((resp.status_code, resp.data["estado"]), (201, "PAGADA"), resp.data)
        pago = resp.data["pagos"][0]["id"]
        resp = client.post(f"/api/cuentas-por-pagar/{pk}/pagos/{pago}/anular/", {"motivo": "Error", "fecha": "2026-03-16"}, format="json")
        self.assertEqual((resp.status_code, resp.data["saldo"]), (200, "250.00"), resp.data)
        lista = client.get("/api/cuentas-por-pagar/", {"fecha": "2026-04-15", "vencimiento": "VENCIDA"}).data
        self.assertEqual((lista["count"], lista["results"][0]["dias"]), (1, 15))
        self.assertEqual(client.get("/api/cuentas-por-pagar/resumen/", {"fecha": "2026-04-15"}).data["vencido"], "250.00")

    def test_otros_roles_solo_consultan(self):
        cxp = self.registrar()
        client = APIClient()
        for rol in (roles.JEFE_AREA, roles.AUDITOR):
            client.force_authenticate(crear_usuario(f"u-{rol}", rol))
            self.assertEqual(client.get(f"/api/cuentas-por-pagar/{cxp.pk}/").status_code, 200)
            resp = client.post(f"/api/cuentas-por-pagar/{cxp.pk}/pagos/", {"fecha": "2026-03-15", "monto": "1", "cuenta_banco": self.bancos.pk}, format="json")
            self.assertEqual(resp.status_code, 403)
