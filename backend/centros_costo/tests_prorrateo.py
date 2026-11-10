"""Pruebas de T2.3: motor de prorrateo con bases configurables y trazabilidad."""
from datetime import date
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from rest_framework.test import APIClient

from contabilidad import services as contabilidad
from contabilidad.models import Asiento, Cuenta, LineaAsiento, PeriodoContable
from usuarios import roles
from usuarios.models import Bitacora

from . import prorrateo, services
from .models import CentroCosto, EjecucionProrrateo, MedidaBase, ReglaProrrateo

T, C = CentroCosto.Tipo, CentroCosto.Clase
ENERO = date(2026, 1, 1)
D = Decimal


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class RepartirTests(TestCase):
    def test_residuo_mayor_cuadra_al_centavo(self):
        self.assertEqual(prorrateo.repartir(D("100.00"), [D(1), D(1), D(1)]), [D("33.34"), D("33.33"), D("33.33")])
        partes = prorrateo.repartir(D("0.05"), [D(1)] * 7)
        self.assertEqual(sum(partes), D("0.05"))
        self.assertEqual(prorrateo.repartir(D("1000.00"), [D(100), D(300), D(600)]), [D("100.00"), D("300.00"), D("600.00")])
        partes = prorrateo.repartir(D("999.99"), [D("1.5"), D("2.25"), D(0), D("7.0001")])
        self.assertEqual(sum(partes), D("999.99"))
        self.assertEqual(partes[2], 0)


class BaseProrrateoTests(TestCase):
    def setUp(self):
        self.contador = c = crear_usuario("contador", roles.CONTADOR)
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(usuario=c, codigo="1102", nombre="Bancos", padre=activo, exenta_centro_costo=True)
        gastos = contabilidad.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO, acepta_movimientos=False)
        self.generales = contabilidad.crear_cuenta(usuario=c, codigo="5202", nombre="Generales", padre=gastos, acepta_movimientos=False)
        self.energia = contabilidad.crear_cuenta(usuario=c, codigo="520201", nombre="Energía", padre=self.generales)
        self.agua = contabilidad.crear_cuenta(usuario=c, codigo="520202", nombre="Agua", padre=self.generales)
        self.salarios = contabilidad.crear_cuenta(usuario=c, codigo="5201", nombre="Salarios", padre=gastos)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)
        self.enero = PeriodoContable.objects.get(anio=2026, mes=1)
        self.marzo = PeriodoContable.objects.get(anio=2026, mes=3)

        matriz = self.centro("01", "Matriz", acepta_movimientos=False)
        self.gerencia = self.centro("01-01", "Gerencia", padre=matriz)
        self.ti = self.centro("01-02", "Tecnología", padre=matriz)
        self.agencia_a = self.centro("01-03", "Agencia A", padre=matriz)
        self.agencia_b = self.centro("01-04", "Agencia B", padre=matriz)

        self.m2 = prorrateo.crear_base(usuario=c, codigo="METROS2", nombre="Metros cuadrados", unidad="m²")
        for periodo in (self.enero, self.marzo):
            self.medidas(periodo, {self.gerencia: "50", self.ti: "100", self.agencia_a: "300", self.agencia_b: "600"})

    def centro(self, codigo, nombre, **kwargs):
        datos = {"tipo": T.COSTO, "clase": C.DEPARTAMENTO, "vigente_desde": ENERO, **kwargs}
        return services.crear_centro(usuario=self.contador, codigo=codigo, nombre=nombre, **datos)

    def medidas(self, periodo, valores):
        return prorrateo.guardar_medidas(
            usuario=self.contador, base=self.m2, periodo=periodo,
            valores=[{"centro_costo": c, "valor": v} for c, v in valores.items()],
        )

    def regla(self, nombre="Gerencia por m²", origen=None, destinos=None, cuentas=None, orden=1, **kwargs):
        return prorrateo.crear_regla(
            usuario=self.contador, nombre=nombre, orden=orden, base=kwargs.pop("base", self.m2),
            centro_origen=origen or self.gerencia,
            cuentas=cuentas or [self.generales],
            destinos=destinos or [self.ti, self.agencia_a, self.agencia_b],
            **kwargs,
        )

    def gasto(self, cuenta, centro, monto, fecha=date(2026, 3, 10)):
        asiento = contabilidad.crear_asiento(
            usuario=self.contador, fecha=fecha, concepto="Gasto",
            lineas=[
                {"cuenta": cuenta, "centro_costo": centro, "debe": monto, "haber": 0},
                {"cuenta": self.bancos, "debe": 0, "haber": monto},
            ],
        )
        return contabilidad.contabilizar_asiento(asiento, usuario=self.contador)

    def ejecutar(self, regla, periodo=None):
        return prorrateo.ejecutar(usuario=self.contador, regla=regla, periodo=periodo or self.marzo)

    def saldo(self, centro, periodo=None):
        """Saldo (debe - haber) del centro en gastos generales durante el periodo."""
        periodo = periodo or self.marzo
        s = LineaAsiento.objects.filter(
            asiento__estado=Asiento.Estado.CONTABILIZADO, centro_costo=centro,
            cuenta__in=[self.energia, self.agua], asiento__fecha__gte=periodo.fecha_inicio,
            asiento__fecha__lte=periodo.fecha_fin,
        ).aggregate(d=Sum("debe"), h=Sum("haber"))
        return (s["d"] or 0) - (s["h"] or 0)


class ReglasProrrateoTests(BaseProrrateoTests):
    def test_crea_con_bitacora(self):
        regla = self.regla()
        self.assertEqual(regla.destinos.count(), 3)
        evento = Bitacora.objects.get(entidad="regla_prorrateo", accion=Bitacora.Accion.CREAR)
        self.assertEqual(evento.valor_nuevo["cuentas"], ["5202"])

    def test_origen_no_es_destino_y_destinos_de_detalle(self):
        with self.assertRaises(ValidationError):
            self.regla(destinos=[self.gerencia, self.ti])
        with self.assertRaises(ValidationError):
            self.regla(destinos=[CentroCosto.objects.get(codigo="01")])

    def test_cuentas_exentas_no_se_prorratean(self):
        with self.assertRaises(ValidationError):
            self.regla(cuentas=[self.bancos])

    def test_no_se_distribuye_dos_veces_lo_mismo(self):
        self.regla()
        with self.assertRaises(ValidationError) as ctx:
            self.regla(nombre="Energía", cuentas=[self.energia])  # 520201 está dentro de 5202
        self.assertIn("cuentas", ctx.exception.message_dict)
        self.regla(nombre="Salarios", cuentas=[self.salarios])

    def test_escalonado(self):
        self.regla()  # orden 1: 01-01 → 01-02, 01-03, 01-04
        with self.assertRaises(ValidationError) as ctx:  # orden 2 no puede devolver costos a 01-01
            self.regla(nombre="TI", origen=self.ti, destinos=[self.gerencia, self.agencia_a], orden=2)
        self.assertIn("destinos", ctx.exception.message_dict)
        with self.assertRaises(ValidationError) as ctx:  # 01-02 recibe de la orden 1: debe ir después
            self.regla(nombre="TI", origen=self.ti, destinos=[self.agencia_a], orden=1)
        self.assertIn("orden", ctx.exception.message_dict)
        self.regla(nombre="TI", origen=self.ti, destinos=[self.agencia_a, self.agencia_b], orden=2)

    def test_eliminar_solo_sin_ejecuciones(self):
        regla = self.regla()
        self.gasto(self.energia, self.gerencia, "100")
        self.ejecutar(regla)
        with self.assertRaises(ValidationError):
            prorrateo.eliminar_regla(regla, usuario=self.contador)
        prorrateo.actualizar_regla(regla, usuario=self.contador, datos={"activa": False})


class MedidasTests(BaseProrrateoTests):
    def test_cuadricula_y_validaciones(self):
        cuadricula = prorrateo.cuadricula_medidas(self.m2, self.marzo)
        self.assertEqual([f["codigo"] for f in cuadricula["filas"]], ["01-01", "01-02", "01-03", "01-04"])
        self.assertEqual(cuadricula["total"], "1050.0000")
        with self.assertRaises(ValidationError):
            self.medidas(self.marzo, {self.ti: "-1"})
        with self.assertRaises(ValidationError):
            self.medidas(self.marzo, {self.ti: "1.00001"})
        self.medidas(self.marzo, {self.ti: ""})  # vacío elimina
        self.assertFalse(MedidaBase.objects.filter(periodo=self.marzo, centro_costo=self.ti).exists())

    def test_copiar_del_periodo_anterior(self):
        febrero = PeriodoContable.objects.get(anio=2026, mes=2)
        copiadas, cuadricula = prorrateo.copiar_medidas(usuario=self.contador, base=self.m2, periodo=febrero)
        self.assertEqual(copiadas, 4)
        self.assertEqual(cuadricula["total"], "1050.0000")
        with self.assertRaises(ValidationError):  # ya no falta nada
            prorrateo.copiar_medidas(usuario=self.contador, base=self.m2, periodo=febrero)

    def test_no_se_cambian_medidas_ya_usadas(self):
        self.gasto(self.energia, self.gerencia, "100")
        self.ejecutar(self.regla())
        with self.assertRaises(ValidationError):
            self.medidas(self.marzo, {self.ti: "200"})
        self.assertFalse(prorrateo.cuadricula_medidas(self.m2, self.marzo)["editable"])


class EjecucionTests(BaseProrrateoTests):
    def test_distribuye_y_traza_cada_linea(self):
        gasto = self.gasto(self.energia, self.gerencia, "1000")
        self.gasto(self.salarios, self.gerencia, "500")  # otra cuenta: no se distribuye
        ejecucion = self.ejecutar(self.regla())
        asiento = ejecucion.asiento
        self.assertEqual(asiento.tipo, Asiento.Tipo.PRORRATEO)
        self.assertEqual(asiento.estado, Asiento.Estado.CONTABILIZADO)
        self.assertEqual(asiento.fecha, date(2026, 3, 31))
        self.assertEqual(ejecucion.total_distribuido, D("1000.00"))
        origen = gasto.lineas.get(numero_linea=1)
        lineas = list(asiento.lineas.order_by("numero_linea"))
        self.assertTrue(all(l.linea_origen_id == origen.pk for l in lineas))
        self.assertEqual(
            [(l.centro_costo.codigo, l.debe, l.haber) for l in lineas],
            [("01-01", 0, D("1000")), ("01-02", D("100"), 0), ("01-03", D("300"), 0), ("01-04", D("600"), 0)],
        )
        self.assertEqual(self.saldo(self.gerencia), 0)
        self.assertEqual({d["codigo"]: d["porcentaje"] for d in ejecucion.detalle["destinos"]},
                         {"01-02": "10.0000", "01-03": "30.0000", "01-04": "60.0000"})
        self.assertTrue(Bitacora.objects.filter(entidad="prorrateo", accion=Bitacora.Accion.PRORRATEAR).exists())

    def test_abonos_se_distribuyen_en_sentido_contrario(self):
        self.gasto(self.energia, self.gerencia, "1000")
        devolucion = contabilidad.crear_asiento(
            usuario=self.contador, fecha=date(2026, 3, 12), concepto="Nota de crédito",
            lineas=[
                {"cuenta": self.bancos, "debe": "100", "haber": 0},
                {"cuenta": self.agua, "centro_costo": self.gerencia, "debe": 0, "haber": "100"},
            ],
        )
        contabilidad.contabilizar_asiento(devolucion, usuario=self.contador)
        ejecucion = self.ejecutar(self.regla())
        self.assertEqual(ejecucion.total_distribuido, D("900.00"))
        self.assertEqual(self.saldo(self.gerencia), 0)
        self.assertEqual(self.saldo(self.agencia_b), D("540.00"))

    def test_una_vez_por_periodo_y_solo_periodo_abierto(self):
        regla = self.regla()
        self.gasto(self.energia, self.gerencia, "100")
        self.ejecutar(regla)
        with self.assertRaises(ValidationError):
            self.ejecutar(regla)
        contabilidad.cerrar_periodo(self.enero, usuario=self.contador)
        with self.assertRaises(ValidationError):
            self.ejecutar(regla, self.enero)

    def test_sin_costos_o_sin_medidas(self):
        regla = self.regla()
        with self.assertRaises(prorrateo.SinMovimientos):
            self.ejecutar(regla)
        self.gasto(self.energia, self.gerencia, "100")
        self.medidas(self.marzo, {self.agencia_b: ""})
        with self.assertRaises(ValidationError) as ctx:
            self.ejecutar(regla)
        self.assertIn("01-04", str(ctx.exception))

    def test_escalonado_en_la_ejecucion(self):
        r1 = self.regla()
        r2 = self.regla(nombre="TI", origen=self.ti, destinos=[self.agencia_a, self.agencia_b], orden=2)
        self.gasto(self.energia, self.gerencia, "1000")
        self.gasto(self.agua, self.ti, "40")
        with self.assertRaises(ValidationError):
            self.ejecutar(r2)  # falta la regla 1, que envía costos a TI
        self.ejecutar(r1)
        e2 = self.ejecutar(r2)
        self.assertEqual(e2.total_distribuido, D("140.00"))  # 40 propios + 100 recibidos
        self.assertEqual(self.saldo(self.ti), 0)
        self.assertEqual(self.saldo(self.agencia_a) + self.saldo(self.agencia_b), D("1040.00"))

    def test_anular_y_volver_a_ejecutar(self):
        r1 = self.regla()
        r2 = self.regla(nombre="TI", origen=self.ti, destinos=[self.agencia_a, self.agencia_b], orden=2)
        self.gasto(self.energia, self.gerencia, "1000")
        e1 = self.ejecutar(r1)
        e2 = self.ejecutar(r2)
        with self.assertRaises(ValidationError):
            prorrateo.anular(e1, usuario=self.contador, motivo="Medidas mal")
        prorrateo.anular(e2, usuario=self.contador, motivo="Medidas mal")
        e1 = prorrateo.anular(e1, usuario=self.contador, motivo="Medidas mal")
        self.assertEqual(e1.estado, EjecucionProrrateo.Estado.ANULADA)
        self.assertEqual(e1.asiento.reversion.tipo, Asiento.Tipo.REVERSION)
        self.assertEqual(self.saldo(self.gerencia), D("1000.00"))
        # Se corrigen las medidas y se recalcula: el asiento anulado y su reversión no cuentan como costo.
        self.medidas(self.marzo, {self.ti: "400"})
        nueva = self.ejecutar(r1)
        self.assertEqual(nueva.total_distribuido, D("1000.00"))
        self.assertEqual(self.saldo(self.ti), D("307.69"))
        self.assertTrue(Bitacora.objects.filter(entidad="prorrateo", accion=Bitacora.Accion.ANULAR).count() == 2)

    def test_el_asiento_de_prorrateo_no_se_revierte_desde_asientos(self):
        self.gasto(self.energia, self.gerencia, "100")
        ejecucion = self.ejecutar(self.regla())
        with self.assertRaises(ValidationError) as ctx:
            contabilidad.revertir_asiento(ejecucion.asiento, usuario=self.contador, motivo="X", fecha=date(2026, 3, 31))
        self.assertIn("Prorrateo", str(ctx.exception))

    def test_ejecutar_pendientes_en_orden(self):
        self.regla(nombre="TI", origen=self.ti, destinos=[self.agencia_a, self.agencia_b], orden=2)
        self.regla()
        self.regla(nombre="Salarios agencia A", origen=self.agencia_a, cuentas=[self.salarios],
                   destinos=[self.agencia_b], orden=3)
        self.gasto(self.energia, self.gerencia, "1000")
        resultados = prorrateo.ejecutar_pendientes(usuario=self.contador, periodo=self.marzo)
        self.assertEqual([r["resultado"] for r in resultados], ["EJECUTADA", "EJECUTADA", "SIN_MOVIMIENTOS"])
        self.assertEqual(resultados[0]["regla"], "Gerencia por m²")
        # Las ya ejecutadas no se repiten; solo queda la que no tiene costos.
        resultados = prorrateo.ejecutar_pendientes(usuario=self.contador, periodo=self.marzo)
        self.assertEqual([r["regla"] for r in resultados], ["Salarios agencia A"])
        self.assertEqual(EjecucionProrrateo.objects.count(), 2)

    def test_vista_previa_no_registra(self):
        self.gasto(self.energia, self.gerencia, "1000")
        resumen = prorrateo.previsualizar(self.regla(), self.marzo)
        self.assertEqual(resumen["total"], "1000.00")
        self.assertEqual([d["monto"] for d in resumen["destinos"]], ["100.00", "300.00", "600.00"])
        self.assertEqual(len(resumen["origen"]), 1)
        self.assertFalse(EjecucionProrrateo.objects.exists())


class ProrrateoApiTests(BaseProrrateoTests):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)

    def test_permisos(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/prorrateo/bases/").status_code, 200)
        self.assertEqual(self.client.get("/api/prorrateo/ejecuciones/", {"periodo": self.marzo.pk}).status_code, 200)
        resp = self.client.post("/api/prorrateo/bases/", {"codigo": "X", "nombre": "X", "unidad": "u"}, format="json")
        self.assertEqual(resp.status_code, 403)
        resp = self.client.put("/api/prorrateo/medidas/", {"base": self.m2.pk, "periodo": self.marzo.pk, "valores": []}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_flujo_completo(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.get("/api/prorrateo/medidas/", {"base": self.m2.pk, "periodo": self.marzo.pk})
        self.assertEqual(len(resp.data["filas"]), 4)
        resp = self.client.put(
            "/api/prorrateo/medidas/",
            {"base": self.m2.pk, "periodo": self.marzo.pk, "valores": [{"centro_costo": self.ti.pk, "valor": "100.5"}]},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        datos = {
            "nombre": "Gerencia", "orden": 1, "centro_origen": self.gerencia.pk, "base": self.m2.pk,
            "cuentas": [self.generales.pk], "destinos": [self.ti.pk, self.agencia_a.pk, self.agencia_b.pk],
        }
        resp = self.client.post("/api/prorrateo/reglas/", datos, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        regla = resp.data["id"]
        self.assertEqual([c["codigo"] for c in resp.data["cuentas"]], ["5202"])
        resp = self.client.patch(f"/api/prorrateo/reglas/{regla}/", {"nombre": "Gerencia general"}, format="json")
        self.assertEqual(resp.data["nombre"], "Gerencia general")

        self.gasto(self.energia, self.gerencia, "1000")
        resp = self.client.get("/api/prorrateo/ejecuciones/previsualizar/", {"regla": regla, "periodo": self.marzo.pk})
        self.assertEqual(resp.status_code, 200, resp.data)
        resp = self.client.post("/api/prorrateo/ejecuciones/", {"regla": regla, "periodo": self.marzo.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        ejecucion, asiento = resp.data["id"], resp.data["asiento"]

        detalle = self.client.get(f"/api/asientos/{asiento}/").data
        self.assertEqual(detalle["tipo"], "PRORRATEO")
        self.assertTrue(all(l["origen_asiento_codigo"] for l in detalle["lineas"]))
        resp = self.client.post(f"/api/asientos/{asiento}/revertir/", {"motivo": "x"}, format="json")
        self.assertEqual(resp.status_code, 400)

        estado = self.client.get("/api/prorrateo/ejecuciones/", {"periodo": self.marzo.pk}).data
        self.assertEqual(estado[0]["estado"], "EJECUTADA")
        resp = self.client.post(f"/api/prorrateo/ejecuciones/{ejecucion}/anular/", {"motivo": ""}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.post(f"/api/prorrateo/ejecuciones/{ejecucion}/anular/", {"motivo": "Prueba"}, format="json")
        self.assertEqual(resp.data["estado"], "ANULADA")
        self.assertIsNotNone(resp.data["reversion"])
        resp = self.client.post("/api/prorrateo/ejecuciones/pendientes/", {"periodo": self.marzo.pk}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data[0]["resultado"], "EJECUTADA")


class CargarProrrateoBaseTests(TestCase):
    def test_carga_idempotente(self):
        autor = crear_usuario("contador", roles.CONTADOR)
        salida = {"stdout": StringIO(), "stderr": StringIO()}
        call_command("cargar_catalogo_base", usuario="contador", **salida)
        call_command("cargar_centros_base", usuario="contador", **salida)
        contabilidad.crear_ejercicio(usuario=autor, anio=2026)
        call_command("cargar_prorrateo_base", usuario="contador", anio=2026, **salida)
        self.assertEqual(ReglaProrrateo.objects.count(), 3)
        total = MedidaBase.objects.count()
        self.assertEqual(total, 3 * 13 * 12)
        call_command("cargar_prorrateo_base", usuario="contador", anio=2026, **salida)
        self.assertEqual((ReglaProrrateo.objects.count(), MedidaBase.objects.count()), (3, total))
