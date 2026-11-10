"""Pruebas de T5.2: proyección de egresos a 30/60/90 días."""
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from usuarios import roles
from usuarios.models import Bitacora

from . import cuentas_por_pagar as cpp
from . import proyeccion
from .models import CuentaPorPagar, EgresoProgramado
from .tests_cuentas_por_pagar import BaseCxP, crear_usuario

D = Decimal
F = EgresoProgramado.Frecuencia
REFERENCIA = date(2026, 6, 1)  # horizonte hasta el 30/08/2026


def por_clave(lista, clave):
    return {x[clave]: x for x in lista}


class BaseProyeccion(BaseCxP):
    def setUp(self):
        super().setUp()
        self.docs = {}
        for numero, vence, monto in (
            ("A", date(2026, 5, 20), "100"),  # vencido
            ("B", date(2026, 6, 15), "200"),  # 0-30 (se paga 50)
            ("C", date(2026, 7, 20), "300"),  # 31-60
            ("D", date(2026, 8, 25), "400"),  # 61-90
            ("E", date(2026, 9, 15), "500"),  # fuera del horizonte
            ("F", date(2026, 6, 10), "600"),  # pagada
        ):
            self.docs[numero] = self.registrar(
                numero=numero, emision=date(2026, 5, 1), vence=vence,
                lineas=[{"cuenta": self.energia, "centro_costo": self.ti, "monto": D(monto)}],
            )
        self.pagar(self.docs["B"], "50", fecha=date(2026, 5, 15))
        self.pagar(self.docs["F"], "600", fecha=date(2026, 5, 15))
        self.planilla = self.egreso(concepto="Planilla", categoria="PLANILLA", monto=D("1000"), frecuencia=F.MENSUAL,
                                    fecha_inicio=date(2026, 1, 1), dia_mes=30)
        self.egreso(concepto="Pago a cuenta", categoria="IMPUESTOS", monto=D("250"), frecuencia=F.UNICA, fecha_inicio=date(2026, 7, 10))
        self.egreso(concepto="Inactivo", categoria="OTROS", monto=D("999"), frecuencia=F.UNICA, fecha_inicio=date(2026, 6, 2), activo=False)

    def egreso(self, **datos):
        return proyeccion.crear_egreso_programado(usuario=self.tesorero, **datos)

    def proyectar(self, fecha=REFERENCIA):
        return proyeccion.proyeccion_egresos(fecha=fecha)


class ProyeccionTests(BaseProyeccion):
    def test_tramos_y_acumulados(self):
        r = self.proyectar()
        self.assertEqual({t["tramo"]: t["monto"] for t in r["tramos"]},
                         {"VENCIDO": "100.00", "D30": "1150.00", "D60": "1550.00", "D90": "1400.00"})
        self.assertEqual(r["acumulado"], {"30": "1250.00", "60": "2800.00", "90": "4200.00"})
        self.assertEqual(r["total"], "4200.00")
        self.assertEqual((r["tramos"][1]["desde"], r["tramos"][3]["hasta"]), ("2026-06-01", "2026-08-30"))

    def test_por_categoria_y_proveedor(self):
        r = self.proyectar()
        cat = por_clave(r["por_categoria"], "categoria")
        self.assertEqual(list(cat), ["PROVEEDORES", "PLANILLA", "IMPUESTOS"])
        self.assertEqual(cat["PROVEEDORES"]["tramos"], {"VENCIDO": "100.00", "D30": "150.00", "D60": "300.00", "D90": "400.00"})
        self.assertEqual((cat["PLANILLA"]["total"], cat["IMPUESTOS"]["tramos"]["D60"]), ("3000.00", "250.00"))
        self.assertEqual(r["proveedores"], [{"id": self.proveedor.pk, "nombre": self.proveedor.nombre, "monto": "950.00"}])

    def test_detalle_y_semanas(self):
        r = self.proyectar()
        detalle = [(d["fecha"], d["origen"], d["monto"], d["tramo"]) for d in r["detalle"]]
        self.assertEqual(detalle[0], ("2026-05-20", "CUENTA_POR_PAGAR", "100.00", "VENCIDO"))
        planillas = [d for d in r["detalle"] if d["categoria"] == "PLANILLA"]
        self.assertEqual([d["fecha"] for d in planillas], ["2026-06-30", "2026-07-30", "2026-08-30"])
        self.assertNotIn(self.docs["E"].pk, [d["id"] for d in r["detalle"] if d["origen"] == "CUENTA_POR_PAGAR"])  # fuera del horizonte
        semanas = {s["semana"]: s["monto"] for s in r["semanas"]}
        self.assertEqual(len(semanas), 13)
        self.assertEqual(semanas[3], "150.00")  # B vence el día 14
        self.assertEqual(sum(D(m) for m in semanas.values()), D("4100.00"))  # todo menos el vencido

    def test_programar_pago_mueve_de_tramo(self):
        c = self.docs["C"]
        proyeccion.programar_pago(c, usuario=self.tesorero, fecha_pago_programada=date(2026, 6, 5))
        r = self.proyectar()
        self.assertEqual(por_clave(r["tramos"], "tramo")["D30"]["monto"], "1450.00")
        item = next(d for d in r["detalle"] if d["origen"] == "CUENTA_POR_PAGAR" and d["id"] == c.pk)
        self.assertEqual((item["fecha"], item["programado"], item["vencimiento"]), ("2026-06-05", True, "2026-07-20"))
        # Un documento fuera del horizonte entra si se programa dentro.
        proyeccion.programar_pago(self.docs["E"], usuario=self.tesorero, fecha_pago_programada=date(2026, 8, 1))
        self.assertEqual(self.proyectar()["total"], "4700.00")
        proyeccion.programar_pago(c, usuario=self.tesorero, fecha_pago_programada=None)
        self.assertEqual(por_clave(self.proyectar()["tramos"], "tramo")["D30"]["monto"], "1150.00")
        self.assertEqual(Bitacora.objects.filter(entidad="cuenta_por_pagar", accion="MODIFICAR").count(), 3)

    def test_programar_validaciones(self):
        with self.assertRaises(ValidationError):
            proyeccion.programar_pago(self.docs["C"], usuario=self.tesorero, fecha_pago_programada=date(2026, 4, 30))
        with self.assertRaises(ValidationError):
            proyeccion.programar_pago(self.docs["F"], usuario=self.tesorero, fecha_pago_programada=date(2026, 6, 5))  # pagada

    def test_pagos_y_anulaciones_se_reflejan(self):
        cpp.anular_cuenta_por_pagar(self.docs["D"], usuario=self.contador, motivo="Duplicada", fecha=date(2026, 5, 20))
        self.pagar(CuentaPorPagar.objects.get(numero_documento="C"), "100", fecha=date(2026, 5, 20))
        tramos = {t["tramo"]: t["monto"] for t in self.proyectar()["tramos"]}
        self.assertEqual((tramos["D60"], tramos["D90"]), ("1450.00", "1000.00"))

    def test_fecha_de_referencia(self):
        r = self.proyectar(fecha=date(2026, 7, 1))
        tramos = {t["tramo"]: t["monto"] for t in r["tramos"]}
        # A y B ya vencieron; la planilla de junio ya no se proyecta.
        self.assertEqual(tramos["VENCIDO"], "250.00")
        self.assertEqual(tramos["D30"], "1550.00")  # C (20/07) + planilla 30/07 + impuesto 10/07


class EgresosProgramadosTests(BaseProyeccion):
    def test_ocurrencias_mensuales(self):
        e = self.egreso(concepto="Alquiler", categoria="ALQUILERES", monto=D("10"), frecuencia=F.MENSUAL,
                        fecha_inicio=date(2026, 1, 15), fecha_fin=date(2026, 4, 30), dia_mes=31)
        self.assertEqual(proyeccion.ocurrencias(e, date(2026, 1, 1), date(2026, 12, 31)),
                         [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)])
        self.assertEqual(proyeccion.proxima_fecha(e, date(2026, 3, 1)), date(2026, 3, 31))
        self.assertIsNone(proyeccion.proxima_fecha(e, date(2026, 5, 1)))

    def test_validaciones(self):
        casos = [
            {"frecuencia": F.MENSUAL, "dia_mes": None},
            {"monto": D("0")},
            {"concepto": "  "},
            {"frecuencia": F.MENSUAL, "dia_mes": 5, "fecha_fin": date(2025, 1, 1)},
        ]
        base = {"concepto": "X", "categoria": "OTROS", "monto": D("1"), "frecuencia": F.UNICA, "fecha_inicio": date(2026, 6, 1)}
        for cambios in casos:
            with self.subTest(cambios=cambios), self.assertRaises(ValidationError):
                self.egreso(**{**base, **cambios})

    def test_desactivar_editar_y_eliminar(self):
        proyeccion.actualizar_egreso_programado(self.planilla, usuario=self.tesorero, datos={"activo": False})
        self.assertNotIn("PLANILLA", [c["categoria"] for c in self.proyectar()["por_categoria"]])
        proyeccion.actualizar_egreso_programado(self.planilla, usuario=self.tesorero, datos={"activo": True, "monto": D("1200")})
        cat = por_clave(self.proyectar()["por_categoria"], "categoria")
        self.assertEqual(cat["PLANILLA"]["total"], "3600.00")
        proyeccion.eliminar_egreso_programado(self.planilla, usuario=self.tesorero)
        self.assertFalse(EgresoProgramado.objects.filter(pk=self.planilla.pk).exists())
        acciones = list(Bitacora.objects.filter(entidad="egreso_programado").values_list("accion", flat=True))
        self.assertEqual(acciones.count("MODIFICAR"), 2)
        self.assertIn("ELIMINAR", acciones)


class ProyeccionApiTests(BaseProyeccion):
    def test_api(self):
        client = APIClient()
        client.force_authenticate(self.tesorero)
        resp = client.get("/api/tesoreria/proyeccion-egresos/", {"fecha": "2026-06-01"})
        self.assertEqual((resp.status_code, resp.data["acumulado"]["90"]), (200, "4200.00"))
        resp = client.post(f"/api/cuentas-por-pagar/{self.docs['C'].pk}/programar/", {"fecha_pago_programada": "2026-06-05"}, format="json")
        self.assertEqual((resp.status_code, resp.data["fecha_pago_programada"]), (200, "2026-06-05"), resp.data)
        resp = client.post("/api/egresos-programados/", {
            "concepto": "Renta", "categoria": "IMPUESTOS", "monto": "80.00", "frecuencia": "UNICA", "fecha_inicio": "2026-06-20",
        }, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        resp = client.patch(f"/api/egresos-programados/{pk}/", {"monto": "90.00"}, format="json")
        self.assertEqual((resp.status_code, resp.data["monto"]), (200, "90.00"), resp.data)
        self.assertEqual(len(client.get("/api/egresos-programados/").data), 4)
        self.assertEqual(client.delete(f"/api/egresos-programados/{pk}/").status_code, 204)

    def test_otros_roles_solo_consultan(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("jefe", roles.JEFE_AREA))
        self.assertEqual(client.get("/api/tesoreria/proyeccion-egresos/").status_code, 200)
        self.assertEqual(client.get("/api/egresos-programados/").status_code, 200)
        resp = client.post(f"/api/cuentas-por-pagar/{self.docs['C'].pk}/programar/", {"fecha_pago_programada": None}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(client.delete(f"/api/egresos-programados/{self.planilla.pk}/").status_code, 403)
