"""Pruebas de T3.1: estado de resultados por centro (costeo absorbente)."""
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from centros_costo import prorrateo
from centros_costo import services as centros
from centros_costo.models import CentroCosto, MedidaBase
from contabilidad import services as contabilidad
from contabilidad.models import Cuenta, PeriodoContable
from usuarios import roles

from . import services

T, C = CentroCosto.Tipo, CentroCosto.Clase
ENERO = date(2026, 1, 1)
DESDE, HASTA = date(2026, 1, 1), date(2026, 12, 31)


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


def fila(seccion, codigo):
    return next(f for f in seccion["filas"] if f["cuenta"]["codigo"] == codigo)


class BaseReportes(TestCase):
    def setUp(self):
        self.contador = c = crear_usuario("contador", roles.CONTADOR)
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(usuario=c, codigo="1102", nombre="Bancos", padre=activo, exenta_centro_costo=True)
        ingresos = contabilidad.crear_cuenta(usuario=c, codigo="4", nombre="Ingresos", tipo=Cuenta.Tipo.INGRESO, acepta_movimientos=False)
        g41 = contabilidad.crear_cuenta(usuario=c, codigo="41", nombre="Intermediación", padre=ingresos, acepta_movimientos=False)
        self.intereses = contabilidad.crear_cuenta(usuario=c, codigo="4101", nombre="Intereses", padre=g41)
        gastos = contabilidad.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO, acepta_movimientos=False)
        self.g52 = contabilidad.crear_cuenta(usuario=c, codigo="52", nombre="Gastos de operación", padre=gastos, acepta_movimientos=False)
        self.energia = contabilidad.crear_cuenta(usuario=c, codigo="5201", nombre="Energía", padre=self.g52)
        self.agua = contabilidad.crear_cuenta(usuario=c, codigo="5202", nombre="Agua", padre=self.g52)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)
        self.marzo = PeriodoContable.objects.get(anio=2026, mes=3)

        self.matriz = self.centro("01", "Casa matriz", T.UTILIDAD, acepta_movimientos=False)
        self.gerencia = self.centro("01-01", "Gerencia", T.COSTO, padre=self.matriz)
        self.negocios = self.centro("01-02", "Negocios", T.INGRESO, padre=self.matriz)
        self.agencia = self.centro("02", "Agencia", T.UTILIDAD, acepta_movimientos=False)
        self.caja = self.centro("02-01", "Caja", T.COSTO, padre=self.agencia)
        self.proyecto = self.centro("90", "Proyecto", T.COSTO)

        self.ingreso(self.negocios, "1000")
        self.ingreso(self.caja, "500")
        self.gasto(self.energia, self.gerencia, "300")
        self.gasto(self.agua, self.caja, "100")

    def centro(self, codigo, nombre, tipo, **kwargs):
        return centros.crear_centro(
            usuario=self.contador, codigo=codigo, nombre=nombre, tipo=tipo, clase=C.DEPARTAMENTO, vigente_desde=ENERO, **kwargs
        )

    def registrar(self, lineas, fecha=date(2026, 3, 10)):
        asiento = contabilidad.crear_asiento(usuario=self.contador, fecha=fecha, concepto="Movimiento", lineas=lineas)
        return contabilidad.contabilizar_asiento(asiento, usuario=self.contador)

    def ingreso(self, centro, monto):
        return self.registrar([
            {"cuenta": self.bancos, "debe": monto, "haber": 0},
            {"cuenta": self.intereses, "centro_costo": centro, "debe": 0, "haber": monto},
        ])

    def gasto(self, cuenta, centro, monto):
        return self.registrar([
            {"cuenta": cuenta, "centro_costo": centro, "debe": monto, "haber": 0},
            {"cuenta": self.bancos, "debe": 0, "haber": monto},
        ])

    def prorratear(self):
        """Gerencia (01-01) distribuye gastos de operación: 1 m² a Negocios, 3 m² a Caja."""
        base = prorrateo.crear_base(usuario=self.contador, codigo="M2", nombre="Metros", unidad="m²")
        for centro, valor in ((self.negocios, 1), (self.caja, 3)):
            MedidaBase.objects.create(base=base, centro_costo=centro, periodo=self.marzo, valor=valor, modificado_por=self.contador)
        regla = prorrateo.crear_regla(
            usuario=self.contador, nombre="Gerencia", centro_origen=self.gerencia, base=base,
            cuentas=[self.g52], destinos=[self.negocios, self.caja],
        )
        return prorrateo.ejecutar(usuario=self.contador, regla=regla, periodo=self.marzo)

    def reporte(self, **kwargs):
        return services.estado_resultados(desde=DESDE, hasta=HASTA, **kwargs)


class EstadoResultadosTests(BaseReportes):
    def test_vista_general_por_unidades_raiz(self):
        r = self.reporte()
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01", "02", "90"])
        ingresos, directos, indirectos = r["secciones"]
        self.assertEqual(fila(ingresos, "41")["valores"], ["1000.00", "500.00", "0.00"])
        self.assertEqual(fila(directos, "52")["valores"], ["300.00", "100.00", "0.00"])
        self.assertEqual(indirectos["filas"], [])
        self.assertEqual(r["resultado_directo"]["valores"], ["700.00", "400.00", "0.00"])
        self.assertEqual(r["resultado"]["total"], "1100.00")

    def test_absorbente_con_prorrateo(self):
        self.prorratear()
        r = self.reporte()
        indirectos = r["secciones"][2]
        # 01 distribuye 300 (de Gerencia) y recibe 75 (Negocios); 02 recibe 225.
        self.assertEqual(indirectos["valores"], ["-225.00", "225.00", "0.00"])
        self.assertEqual(indirectos["total"], "0.00")
        self.assertEqual(r["indirectos"]["recibidos"]["valores"], ["75.00", "225.00", "0.00"])
        self.assertEqual(r["indirectos"]["distribuidos"]["valores"], ["300.00", "0.00", "0.00"])
        self.assertEqual(r["resultado"]["valores"], ["925.00", "175.00", "0.00"])
        self.assertEqual(r["resultado"]["total"], "1100.00")  # el prorrateo no cambia el total

    def test_navegacion_por_la_jerarquia(self):
        self.prorratear()
        r = self.reporte(centro=self.matriz)
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01-01", "01-02"])
        self.assertEqual([c["codigo"] for c in r["ruta"]], ["01"])
        self.assertEqual(r["resultado"]["valores"], ["0.00", "925.00"])  # el centro de servicio queda en cero
        self.assertEqual(r["secciones"][2]["valores"], ["-300.00", "75.00"])
        detalle = self.reporte(centro=self.negocios)
        self.assertEqual([c["codigo"] for c in detalle["columnas"]], ["01-02"])
        self.assertEqual([c["codigo"] for c in detalle["ruta"]], ["01", "01-02"])
        self.assertEqual(detalle["resultado"]["total"], "925.00")

    def test_prorrateo_anulado_no_aparece(self):
        ejecucion = self.prorratear()
        prorrateo.anular(ejecucion, usuario=self.contador, motivo="Prueba")
        r = self.reporte()
        self.assertEqual(r["secciones"][2]["filas"], [])
        self.assertEqual(r["indirectos"]["recibidos"]["total"], "0.00")
        self.assertEqual(r["resultado"]["valores"], ["700.00", "400.00", "0.00"])

    def test_nivel_de_cuentas_y_rango(self):
        r = self.reporte(nivel_cuentas=1)
        self.assertEqual([f["cuenta"]["codigo"] for f in r["secciones"][1]["filas"]], ["5"])
        r = self.reporte(nivel_cuentas=3)
        self.assertEqual([f["cuenta"]["codigo"] for f in r["secciones"][1]["filas"]], ["5201", "5202"])
        vacio = services.estado_resultados(desde=date(2026, 4, 1), hasta=date(2026, 4, 30))
        self.assertEqual(vacio["resultado"]["total"], "0.00")
        with self.assertRaises(ValidationError):
            services.estado_resultados(desde=HASTA, hasta=DESDE)

    def test_unidad_no_vigente_sin_datos_se_omite(self):
        centros.actualizar_centro(self.proyecto, usuario=self.contador, datos={"vigente_hasta": date(2026, 1, 31)})
        r = services.estado_resultados(desde=date(2026, 3, 1), hasta=date(2026, 3, 31))
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01", "02"])

    def test_coincide_con_la_balanza(self):
        from contabilidad.libros import balanza_comprobacion

        self.prorratear()
        balanza = balanza_comprobacion(desde=DESDE, hasta=HASTA, nivel=1)
        saldo = {f["codigo"]: f for f in balanza["filas"]}
        movimiento = lambda codigo: Decimal(str(saldo[codigo]["abonos"])) - Decimal(str(saldo[codigo]["cargos"]))  # noqa: E731
        self.assertEqual(Decimal(self.reporte()["resultado"]["total"]), movimiento("4") + movimiento("5"))


class EstadoResultadosApiTests(BaseReportes):
    def test_api(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("jefe", roles.JEFE_AREA))
        resp = client.get("/api/reportes/estado-resultados/", {"desde": "2026-01-01", "hasta": "2026-12-31", "centro": self.matriz.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["resultado"]["total"], "700.00")
        resp = client.get("/api/reportes/estado-resultados/", {"desde": "2026-12-31", "hasta": "2026-01-01"})
        self.assertEqual(resp.status_code, 400)
        client.force_authenticate(None)
        self.assertEqual(client.get("/api/reportes/estado-resultados/", {"desde": "2026-01-01", "hasta": "2026-12-31"}).status_code, 401)
