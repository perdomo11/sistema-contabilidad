from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from usuarios import roles
from usuarios.models import Bitacora

from . import services
from .models import Cuenta

T = Cuenta.Tipo
N = Cuenta.Naturaleza


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BaseCuentas(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)
        self.gastos = self.crear("5", "Gastos", tipo=T.GASTO, acepta_movimientos=False)
        self.operacion = self.crear("52", "Gastos de operación", padre=self.gastos, acepta_movimientos=False)

    def crear(self, codigo, nombre, **kwargs):
        return services.crear_cuenta(usuario=self.contador, codigo=codigo, nombre=nombre, **kwargs)


class CrearCuentaTests(BaseCuentas):
    def test_jerarquia_nivel_y_herencia_de_tipo(self):
        salarios = self.crear("5201", "Salarios", padre=self.operacion)
        self.assertEqual(salarios.nivel, 3)
        self.assertEqual(salarios.tipo, T.GASTO)
        self.assertEqual(salarios.naturaleza, N.DEUDORA)
        self.assertEqual(salarios.creado_por, self.contador)

    def test_naturaleza_por_defecto_segun_tipo(self):
        pasivo = self.crear("2", "Pasivo", tipo=T.PASIVO)
        self.assertEqual(pasivo.naturaleza, N.ACREEDORA)

    def test_raiz_exige_tipo(self):
        with self.assertRaises(ValidationError):
            self.crear("9", "Sin tipo")

    def test_subcuenta_con_tipo_distinto_al_padre(self):
        with self.assertRaises(ValidationError):
            self.crear("5201", "Mal tipo", padre=self.operacion, tipo=T.ACTIVO)

    def test_codigo_debe_empezar_con_el_del_padre(self):
        with self.assertRaises(ValidationError):
            self.crear("6201", "Prefijo incorrecto", padre=self.operacion)

    def test_codigo_debe_ser_mas_largo_que_el_del_padre(self):
        with self.assertRaises(ValidationError):
            self.crear("52", "Mismo código", padre=self.operacion)

    def test_codigo_solo_digitos(self):
        with self.assertRaises(ValidationError):
            self.crear("52AB", "Letras", padre=self.operacion)

    def test_codigo_duplicado(self):
        with self.assertRaises(ValidationError):
            self.crear("5", "Duplicada", tipo=T.GASTO)

    def test_no_se_agregan_subcuentas_a_una_cuenta_de_detalle(self):
        detalle = self.crear("5201", "Salarios", padre=self.operacion)
        with self.assertRaises(ValidationError):
            self.crear("520101", "Hija de detalle", padre=detalle)

    def test_no_se_agregan_subcuentas_a_un_padre_inactivo(self):
        services.actualizar_cuenta(self.operacion, usuario=self.contador, datos={"activa": False})
        with self.assertRaises(ValidationError):
            self.crear("5201", "Bajo inactiva", padre=self.operacion)

    def test_gasto_no_puede_quedar_exento_de_centro_de_costo(self):
        with self.assertRaises(ValidationError):
            self.crear("5201", "Exenta", padre=self.operacion, exenta_centro_costo=True)

    def test_balance_puede_quedar_exento(self):
        activo = self.crear("1", "Activo", tipo=T.ACTIVO, exenta_centro_costo=True)
        self.assertTrue(activo.exenta_centro_costo)

    def test_constraint_bd_exencion_solo_en_balance(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cuenta.objects.filter(pk=self.gastos.pk).update(exenta_centro_costo=True)

    def test_alta_queda_en_bitacora(self):
        evento = Bitacora.objects.filter(accion=Bitacora.Accion.CREAR, entidad="cuenta").latest("id")
        self.assertEqual(evento.objeto_id, str(self.operacion.pk))
        self.assertEqual(evento.valor_nuevo["codigo"], "52")
        self.assertEqual(evento.usuario, self.contador)


class ActualizarCuentaTests(BaseCuentas):
    def test_modifica_campos_editables_y_registra_bitacora(self):
        detalle = self.crear("5201", "Salarios", padre=self.operacion)
        services.actualizar_cuenta(detalle, usuario=self.contador, datos={"nombre": "Sueldos y salarios"})
        detalle.refresh_from_db()
        self.assertEqual(detalle.nombre, "Sueldos y salarios")
        evento = Bitacora.objects.get(accion=Bitacora.Accion.MODIFICAR, entidad="cuenta")
        self.assertEqual(evento.valor_anterior["nombre"], "Salarios")
        self.assertEqual(evento.valor_nuevo["nombre"], "Sueldos y salarios")

    def test_sin_cambios_no_registra_bitacora(self):
        services.actualizar_cuenta(self.operacion, usuario=self.contador, datos={"nombre": "Gastos de operación"})
        self.assertFalse(Bitacora.objects.filter(accion=Bitacora.Accion.MODIFICAR).exists())

    def test_codigo_padre_y_tipo_son_inmutables(self):
        for datos in ({"codigo": "59"}, {"padre": None}, {"tipo": T.ACTIVO}):
            with self.subTest(datos=datos), self.assertRaises(ValidationError):
                services.actualizar_cuenta(self.operacion, usuario=self.contador, datos=datos)

    def test_cuenta_con_hijos_no_puede_aceptar_movimientos(self):
        with self.assertRaises(ValidationError):
            services.actualizar_cuenta(self.gastos, usuario=self.contador, datos={"acepta_movimientos": True})

    def test_no_se_desactiva_con_subcuentas_activas(self):
        with self.assertRaises(ValidationError):
            services.actualizar_cuenta(self.gastos, usuario=self.contador, datos={"activa": False})

    def test_no_se_activa_si_el_padre_esta_inactivo(self):
        services.actualizar_cuenta(self.operacion, usuario=self.contador, datos={"activa": False})
        services.actualizar_cuenta(self.gastos, usuario=self.contador, datos={"activa": False})
        with self.assertRaises(ValidationError):
            services.actualizar_cuenta(self.operacion, usuario=self.contador, datos={"activa": True})

    def test_no_se_exenta_un_gasto(self):
        with self.assertRaises(ValidationError):
            services.actualizar_cuenta(self.operacion, usuario=self.contador, datos={"exenta_centro_costo": True})


class EliminarCuentaTests(BaseCuentas):
    def test_no_se_elimina_con_subcuentas(self):
        with self.assertRaises(ValidationError):
            services.eliminar_cuenta(self.gastos, usuario=self.contador)

    def test_elimina_hoja_y_registra_bitacora(self):
        detalle = self.crear("5201", "Salarios", padre=self.operacion)
        pk = detalle.pk
        services.eliminar_cuenta(detalle, usuario=self.contador)
        self.assertFalse(Cuenta.objects.filter(pk=pk).exists())
        evento = Bitacora.objects.get(accion=Bitacora.Accion.ELIMINAR, entidad="cuenta")
        self.assertEqual(evento.valor_anterior["codigo"], "5201")


class ArbolTests(BaseCuentas):
    def test_arbol_anidado(self):
        self.crear("5201", "Salarios", padre=self.operacion)
        arbol = services.arbol_cuentas()
        self.assertEqual([n["codigo"] for n in arbol], ["5"])
        self.assertEqual(arbol[0]["hijos"][0]["codigo"], "52")
        self.assertEqual(arbol[0]["hijos"][0]["hijos"][0]["codigo"], "5201")


class CuentasApiTests(BaseCuentas):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)

    def test_lectura_para_cualquier_rol(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/cuentas/").data["count"], 2)
        self.assertEqual(self.client.get("/api/cuentas/arbol/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/cuentas/{self.gastos.pk}/").status_code, 200)

    def test_sin_sesion_responde_401(self):
        self.assertEqual(self.client.get("/api/cuentas/").status_code, 401)

    def test_filtros(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/cuentas/", {"q": "operación"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/cuentas/", {"q": "5"}).data["count"], 2)
        self.assertEqual(self.client.get("/api/cuentas/", {"tipo": "ACTIVO"}).data["count"], 0)

    def test_solo_contador_escribe(self):
        self.client.force_authenticate(self.auditor)
        resp = self.client.post("/api/cuentas/", {"codigo": "5201", "nombre": "X", "padre": self.operacion.pk}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self.client.patch(f"/api/cuentas/{self.gastos.pk}/", {"nombre": "X"}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(f"/api/cuentas/{self.operacion.pk}/").status_code, 403)

    def test_crud_como_contador(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post("/api/cuentas/", {"codigo": "5201", "nombre": "Salarios", "padre": self.operacion.pk}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(resp.data["nivel"], 3)
        resp = self.client.patch(f"/api/cuentas/{pk}/", {"nombre": "Sueldos"}, format="json")
        self.assertEqual(resp.data["nombre"], "Sueldos")
        self.assertEqual(self.client.delete(f"/api/cuentas/{pk}/").status_code, 204)

    def test_regla_de_negocio_responde_400_con_mensaje(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post("/api/cuentas/", {"codigo": "6201", "nombre": "X", "padre": self.operacion.pk}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("codigo", resp.data)
        resp = self.client.delete(f"/api/cuentas/{self.gastos.pk}/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("detail", resp.data)

    def test_patch_de_campo_inmutable_responde_400(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.patch(f"/api/cuentas/{self.operacion.pk}/", {"codigo": "59"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("codigo", resp.data)


class CargarCatalogoBaseTests(TestCase):
    def test_carga_idempotente_y_consistente(self):
        crear_usuario("contador", roles.CONTADOR)
        call_command("cargar_catalogo_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        total = Cuenta.objects.count()
        self.assertGreater(total, 50)
        call_command("cargar_catalogo_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(Cuenta.objects.count(), total)

        # Solo las hojas aceptan movimientos; ingresos y gastos exigen centro de costo.
        for cuenta in Cuenta.objects.all():
            self.assertEqual(cuenta.acepta_movimientos, not cuenta.hijos.exists(), cuenta.codigo)
        self.assertFalse(Cuenta.objects.filter(tipo__in=[T.INGRESO, T.GASTO], exenta_centro_costo=True).exists())
        self.assertEqual(Cuenta.objects.get(codigo="1509").naturaleza, N.ACREEDORA)
        self.assertEqual(Cuenta.objects.get(codigo="520101").nivel, 4)


# =============================================================================
# Periodos contables (T1.2)
# =============================================================================

from datetime import date  # noqa: E402

from django.core.exceptions import PermissionDenied  # noqa: E402

from .models import PeriodoContable  # noqa: E402

E = PeriodoContable.Estado


class BasePeriodos(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)
        self.admin = User.objects.create_superuser("admin", password="Prueba_2026!")

    def periodo(self, anio, mes):
        return PeriodoContable.objects.get(anio=anio, mes=mes)

    def cerrar(self, anio, mes):
        return services.cerrar_periodo(self.periodo(anio, mes), usuario=self.contador)


class CrearEjercicioTests(BasePeriodos):
    def test_crea_12_periodos_abiertos_con_fechas(self):
        periodos = services.crear_ejercicio(usuario=self.contador, anio=2024)
        self.assertEqual(len(periodos), 12)
        self.assertTrue(all(p.estado == E.ABIERTO for p in periodos))
        self.assertEqual(periodos[0].fecha_inicio, date(2024, 1, 1))
        self.assertEqual(periodos[1].fecha_fin, date(2024, 2, 29))  # bisiesto
        self.assertEqual(periodos[11].fecha_fin, date(2024, 12, 31))
        self.assertEqual(periodos[0].nombre, "Enero 2024")
        evento = Bitacora.objects.get(accion=Bitacora.Accion.CREAR, entidad="ejercicio")
        self.assertEqual(evento.objeto_id, "2024")

    def test_ejercicio_duplicado(self):
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        with self.assertRaises(ValidationError):
            services.crear_ejercicio(usuario=self.contador, anio=2026)

    def test_anio_fuera_de_rango(self):
        for anio in (1999, 2101):
            with self.subTest(anio=anio), self.assertRaises(ValidationError):
                services.crear_ejercicio(usuario=self.contador, anio=anio)

    def test_constraints_de_base_de_datos(self):
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodoContable.objects.filter(anio=2026, mes=1).update(mes=13)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodoContable.objects.filter(anio=2026, mes=1).update(estado=E.CERRADO)  # sin responsable
        with self.assertRaises(IntegrityError), transaction.atomic():
            PeriodoContable.objects.filter(anio=2026, mes=2).update(mes=1)  # duplicado


class CerrarPeriodoTests(BasePeriodos):
    def setUp(self):
        super().setUp()
        services.crear_ejercicio(usuario=self.contador, anio=2025)
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        for mes in range(1, 13):
            self.cerrar(2025, mes)

    def test_cierre_registra_responsable_y_bitacora(self):
        periodo = self.cerrar(2026, 1)
        self.assertEqual(periodo.estado, E.CERRADO)
        self.assertEqual(periodo.cerrado_por, self.contador)
        self.assertIsNotNone(periodo.cerrado_en)
        evento = Bitacora.objects.filter(accion=Bitacora.Accion.CERRAR).latest("id")
        self.assertEqual(evento.valor_anterior["estado"], E.ABIERTO)
        self.assertEqual(evento.valor_nuevo["estado"], E.CERRADO)

    def test_cierre_secuencial_dentro_del_anio(self):
        self.cerrar(2026, 1)
        with self.assertRaisesMessage(ValidationError, "Febrero 2026"):
            self.cerrar(2026, 3)

    def test_cierre_secuencial_entre_anios(self):
        services.reabrir_periodo(self.periodo(2025, 12), usuario=self.admin, motivo="Ajuste")
        with self.assertRaisesMessage(ValidationError, "Diciembre 2025"):
            self.cerrar(2026, 1)

    def test_no_se_cierra_dos_veces(self):
        self.cerrar(2026, 1)
        with self.assertRaises(ValidationError):
            self.cerrar(2026, 1)


class ReabrirPeriodoTests(BasePeriodos):
    def setUp(self):
        super().setUp()
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        self.cerrar(2026, 1)
        self.cerrar(2026, 2)

    def test_solo_superusuario(self):
        with self.assertRaises(PermissionDenied):
            services.reabrir_periodo(self.periodo(2026, 2), usuario=self.contador, motivo="x")

    def test_motivo_obligatorio(self):
        with self.assertRaises(ValidationError):
            services.reabrir_periodo(self.periodo(2026, 2), usuario=self.admin, motivo="  ")

    def test_solo_el_ultimo_cerrado(self):
        with self.assertRaisesMessage(ValidationError, "Febrero 2026"):
            services.reabrir_periodo(self.periodo(2026, 1), usuario=self.admin, motivo="x")

    def test_no_se_reabre_un_periodo_abierto(self):
        with self.assertRaises(ValidationError):
            services.reabrir_periodo(self.periodo(2026, 3), usuario=self.admin, motivo="x")

    def test_reapertura_y_bitacora_con_motivo(self):
        periodo = services.reabrir_periodo(self.periodo(2026, 2), usuario=self.admin, motivo="Falta provisión")
        self.assertEqual(periodo.estado, E.ABIERTO)
        evento = Bitacora.objects.get(accion=Bitacora.Accion.REABRIR)
        self.assertEqual(evento.valor_nuevo["motivo"], "Falta provisión")
        self.assertIn("Falta provisión", evento.descripcion)
        self.assertEqual(evento.usuario, self.admin)
        # Ahora enero es el último cerrado y sí se puede reabrir.
        services.reabrir_periodo(self.periodo(2026, 1), usuario=self.admin, motivo="Corrección")


class ValidarFechaRegistrableTests(BasePeriodos):
    def setUp(self):
        super().setUp()
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        self.cerrar(2026, 1)

    def test_fecha_en_periodo_abierto(self):
        self.assertEqual(services.validar_fecha_registrable(date(2026, 2, 15)), self.periodo(2026, 2))

    def test_fecha_en_periodo_cerrado(self):
        with self.assertRaisesMessage(ValidationError, "cerrado"):
            services.validar_fecha_registrable(date(2026, 1, 31))

    def test_fecha_sin_periodo(self):
        with self.assertRaisesMessage(ValidationError, "ejercicio 2027"):
            services.validar_fecha_registrable(date(2027, 1, 1))


class PeriodosApiTests(BasePeriodos):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)

    def test_flujo_completo_por_api(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post("/api/periodos/ejercicios/", {"anio": 2026}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        enero, marzo = resp.data[0]["id"], resp.data[2]["id"]

        self.assertEqual(self.client.post(f"/api/periodos/{enero}/cerrar/").status_code, 200)
        resp = self.client.post(f"/api/periodos/{marzo}/cerrar/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Febrero 2026", resp.data["detail"])

        resumen = self.client.get("/api/periodos/ejercicios/").data
        self.assertEqual(resumen, [{"anio": 2026, "abiertos": 11, "cerrados": 1}])
        self.assertEqual(len(self.client.get("/api/periodos/", {"anio": 2026}).data), 12)

        # El contador no puede reabrir; el superusuario sí, con motivo.
        resp = self.client.post(f"/api/periodos/{enero}/reabrir/", {"motivo": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
        self.client.force_authenticate(self.admin)
        resp = self.client.post(f"/api/periodos/{enero}/reabrir/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("motivo", resp.data)
        resp = self.client.post(f"/api/periodos/{enero}/reabrir/", {"motivo": "Ajuste"}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["estado"], E.ABIERTO)

    def test_auditor_solo_consulta(self):
        services.crear_ejercicio(usuario=self.contador, anio=2026)
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/periodos/").status_code, 200)
        resp = self.client.post("/api/periodos/ejercicios/", {"anio": 2027}, format="json")
        self.assertEqual(resp.status_code, 403)
        enero = self.periodo(2026, 1).pk
        self.assertEqual(self.client.post(f"/api/periodos/{enero}/cerrar/").status_code, 403)

    def test_sin_sesion_responde_401(self):
        self.assertEqual(self.client.get("/api/periodos/").status_code, 401)


# =============================================================================
# Asientos contables (T1.3)
# =============================================================================

from decimal import Decimal  # noqa: E402

from django.db import DatabaseError, connection  # noqa: E402
from django.utils import timezone  # noqa: E402

from .models import Asiento, LineaAsiento  # noqa: E402

EA = Asiento.Estado
TA = Asiento.Tipo
D = Decimal


class BaseAsientos(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)
        c = self.contador
        activo = services.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=T.ACTIVO, acepta_movimientos=False)
        self.caja = services.crear_cuenta(usuario=c, codigo="1101", nombre="Caja", padre=activo)
        self.bancos = services.crear_cuenta(usuario=c, codigo="1102", nombre="Bancos", padre=activo)
        gastos = services.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=T.GASTO, acepta_movimientos=False)
        self.agrupacion = services.crear_cuenta(
            usuario=c, codigo="52", nombre="Gastos de operación", padre=gastos, acepta_movimientos=False
        )
        self.salarios = services.crear_cuenta(usuario=c, codigo="5201", nombre="Salarios", padre=self.agrupacion)
        services.crear_ejercicio(usuario=c, anio=2026)

    def lineas(self, *pares):
        """pares: (cuenta, debe, haber)"""
        return [{"cuenta": cuenta, "debe": debe, "haber": haber} for cuenta, debe, haber in pares]

    def borrador(self, fecha=date(2026, 3, 15), lineas=None, concepto="Pago de planilla"):
        lineas = lineas or self.lineas((self.salarios, "1500.00", 0), (self.caja, 0, "1500.00"))
        return services.crear_asiento(usuario=self.contador, fecha=fecha, concepto=concepto, lineas=lineas)

    def contabilizado(self, **kwargs):
        return services.contabilizar_asiento(self.borrador(**kwargs), usuario=self.contador)


class BorradorTests(BaseAsientos):
    def test_borrador_descuadrado_se_guarda(self):
        asiento = self.borrador(lineas=self.lineas((self.salarios, "100", 0), (self.caja, 0, "60")))
        self.assertEqual(asiento.estado, EA.BORRADOR)
        self.assertIsNone(asiento.numero)
        self.assertEqual((asiento.total_debe, asiento.total_haber), (D("100.00"), D("60.00")))
        self.assertEqual(asiento.periodo.mes, 3)
        self.assertEqual(asiento.lineas.count(), 2)
        self.assertTrue(Bitacora.objects.filter(accion=Bitacora.Accion.CREAR, entidad="asiento").exists())

    def test_validaciones_de_lineas(self):
        casos = {
            "cargo y abono": (self.salarios, "10", "10"),
            "sin monto": (self.salarios, 0, 0),
            "negativo": (self.salarios, "-5", 0),
            "tres decimales": (self.salarios, "1.005", 0),
            "no numérico": (self.salarios, "abc", 0),
            "cuenta de agrupación": (self.agrupacion, "10", 0),
            "sin cuenta": (None, "10", 0),
        }
        for nombre, linea in casos.items():
            with self.subTest(nombre), self.assertRaises(ValidationError):
                self.borrador(lineas=self.lineas(linea, (self.caja, 0, "10")))

    def test_cuenta_inactiva(self):
        services.actualizar_cuenta(self.bancos, usuario=self.contador, datos={"activa": False})
        with self.assertRaises(ValidationError):
            self.borrador(lineas=self.lineas((self.salarios, "10", 0), (self.bancos, 0, "10")))

    def test_concepto_obligatorio(self):
        with self.assertRaises(ValidationError):
            self.borrador(concepto="  ")

    def test_fecha_sin_periodo_o_en_periodo_cerrado(self):
        with self.assertRaisesMessage(ValidationError, "ejercicio 2027"):
            self.borrador(fecha=date(2027, 1, 10))
        services.cerrar_periodo(PeriodoContable.objects.get(anio=2026, mes=1), usuario=self.contador)
        with self.assertRaisesMessage(ValidationError, "cerrado"):
            self.borrador(fecha=date(2026, 1, 10))

    def test_editar_y_eliminar_borrador(self):
        asiento = self.borrador()
        services.actualizar_asiento(
            asiento,
            usuario=self.contador,
            fecha=date(2026, 3, 20),
            concepto="Planilla marzo",
            lineas=self.lineas((self.salarios, "2000", 0), (self.bancos, 0, "2000")),
        )
        asiento.refresh_from_db()
        self.assertEqual(asiento.concepto, "Planilla marzo")
        self.assertEqual(list(asiento.lineas.values_list("cuenta__codigo", flat=True)), ["5201", "1102"])
        services.eliminar_asiento(asiento, usuario=self.contador)
        self.assertFalse(Asiento.objects.filter(pk=asiento.pk).exists())
        self.assertFalse(LineaAsiento.objects.filter(asiento_id=asiento.pk).exists())


class ContabilizarTests(BaseAsientos):
    def test_partida_doble_obligatoria(self):
        asiento = self.borrador(lineas=self.lineas((self.salarios, "100", 0), (self.caja, 0, "60")))
        with self.assertRaisesMessage(ValidationError, "Partida doble"):
            services.contabilizar_asiento(asiento, usuario=self.contador)

    def test_minimo_dos_lineas(self):
        asiento = self.borrador(lineas=self.lineas((self.salarios, "100", 0)))
        with self.assertRaisesMessage(ValidationError, "dos líneas"):
            services.contabilizar_asiento(asiento, usuario=self.contador)

    def test_numeracion_correlativa_por_ejercicio(self):
        primero = self.contabilizado()
        segundo = self.contabilizado()
        self.assertEqual((primero.ejercicio, primero.numero, primero.codigo), (2026, 1, "2026-000001"))
        self.assertEqual(segundo.numero, 2)
        self.assertEqual(primero.estado, EA.CONTABILIZADO)
        self.assertEqual(primero.contabilizado_por, self.contador)
        self.assertTrue(Bitacora.objects.filter(accion=Bitacora.Accion.CONTABILIZAR).exists())

    def test_cuenta_desactivada_despues_del_borrador(self):
        asiento = self.borrador(lineas=self.lineas((self.salarios, "10", 0), (self.bancos, 0, "10")))
        services.actualizar_cuenta(self.bancos, usuario=self.contador, datos={"activa": False})
        with self.assertRaisesMessage(ValidationError, "inactiva"):
            services.contabilizar_asiento(asiento, usuario=self.contador)

    def test_contabilizado_es_inmutable_en_el_servicio(self):
        asiento = self.contabilizado()
        with self.assertRaises(ValidationError):
            services.actualizar_asiento(
                asiento, usuario=self.contador, fecha=asiento.fecha, concepto="X", lineas=self.lineas((self.caja, "1", 0))
            )
        with self.assertRaises(ValidationError):
            services.eliminar_asiento(asiento, usuario=self.contador)
        with self.assertRaises(ValidationError):
            services.contabilizar_asiento(asiento, usuario=self.contador)


class TriggersAsientoTests(BaseAsientos):
    """Las reglas se cumplen aunque se salte el servicio (acceso directo a la BD)."""

    def assertRechazaBD(self, funcion):
        with self.assertRaises(DatabaseError), transaction.atomic():
            funcion()

    def test_asiento_contabilizado_no_se_modifica_ni_elimina(self):
        asiento = self.contabilizado()
        self.assertRechazaBD(lambda: Asiento.objects.filter(pk=asiento.pk).update(concepto="alterado"))
        tabla = Asiento._meta.db_table

        def borrar():
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", [asiento.pk])

        self.assertRechazaBD(borrar)
        asiento.refresh_from_db()
        self.assertEqual(asiento.concepto, "Pago de planilla")

    def test_lineas_de_asiento_contabilizado_no_se_tocan(self):
        asiento = self.contabilizado()
        linea = asiento.lineas.first()
        self.assertRechazaBD(lambda: LineaAsiento.objects.filter(pk=linea.pk).update(debe=D("1")))
        self.assertRechazaBD(lambda: LineaAsiento.objects.filter(pk=linea.pk).delete())
        self.assertRechazaBD(
            lambda: LineaAsiento.objects.create(asiento=asiento, numero_linea=9, cuenta=self.caja, debe=D("5"))
        )

    def test_trigger_exige_partida_doble(self):
        asiento = self.borrador(lineas=self.lineas((self.salarios, "100", 0), (self.caja, 0, "60")))
        self.assertRechazaBD(
            lambda: Asiento.objects.filter(pk=asiento.pk).update(
                estado=EA.CONTABILIZADO,
                ejercicio=2026,
                numero=99,
                total_debe=D("100"),
                total_haber=D("100"),
                contabilizado_por=self.contador,
                contabilizado_en=timezone.now(),
            )
        )

    def test_trigger_exige_periodo_abierto(self):
        asiento = self.borrador(fecha=date(2026, 1, 20))
        # Cierra enero saltándose el servicio (que impediría el cierre por el borrador).
        PeriodoContable.objects.filter(anio=2026, mes=1).update(
            estado=E.CERRADO, cerrado_por=self.contador, cerrado_en=timezone.now()
        )
        self.assertRechazaBD(
            lambda: Asiento.objects.filter(pk=asiento.pk).update(
                estado=EA.CONTABILIZADO,
                ejercicio=2026,
                numero=99,
                total_debe=D("1500"),
                total_haber=D("1500"),
                contabilizado_por=self.contador,
                contabilizado_en=timezone.now(),
            )
        )

    def test_check_linea_cargo_o_abono(self):
        asiento = self.borrador()
        linea = asiento.lineas.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            LineaAsiento.objects.filter(pk=linea.pk).update(haber=D("5"))


class ReversionTests(BaseAsientos):
    def test_reversion_invierte_lineas_y_conserva_trazabilidad(self):
        original = self.contabilizado()
        reversion = services.revertir_asiento(original, usuario=self.contador, motivo="Monto erróneo", fecha=date(2026, 3, 31))
        self.assertEqual(reversion.tipo, TA.REVERSION)
        self.assertEqual(reversion.estado, EA.CONTABILIZADO)
        self.assertEqual(reversion.reversion_de, original)
        self.assertEqual(reversion.numero, 2)
        self.assertIn("Monto erróneo", reversion.concepto)
        for linea_o, linea_r in zip(original.lineas.order_by("numero_linea"), reversion.lineas.order_by("numero_linea")):
            self.assertEqual(linea_r.linea_origen, linea_o)
            self.assertEqual((linea_r.debe, linea_r.haber), (linea_o.haber, linea_o.debe))
            self.assertEqual(linea_r.cuenta, linea_o.cuenta)
        original.refresh_from_db()
        self.assertEqual(original.estado, EA.CONTABILIZADO)  # el original no se toca
        evento = Bitacora.objects.get(accion=Bitacora.Accion.REVERTIR)
        self.assertEqual(evento.valor_nuevo["motivo"], "Monto erróneo")

    def test_reglas_de_reversion(self):
        original = self.contabilizado()
        with self.assertRaises(ValidationError):
            services.revertir_asiento(original, usuario=self.contador, motivo=" ")
        with self.assertRaises(ValidationError):
            services.revertir_asiento(original, usuario=self.contador, motivo="x", fecha=date(2026, 3, 1))
        reversion = services.revertir_asiento(original, usuario=self.contador, motivo="x", fecha=date(2026, 3, 15))
        with self.assertRaisesMessage(ValidationError, "ya fue revertido"):
            services.revertir_asiento(original, usuario=self.contador, motivo="x", fecha=date(2026, 3, 15))
        with self.assertRaisesMessage(ValidationError, "no se revierte"):
            services.revertir_asiento(reversion, usuario=self.contador, motivo="x", fecha=date(2026, 3, 15))
        with self.assertRaises(ValidationError):
            services.revertir_asiento(self.borrador(), usuario=self.contador, motivo="x")

    def test_reversion_con_cuenta_desactivada(self):
        original = self.contabilizado(lineas=self.lineas((self.salarios, "10", 0), (self.bancos, 0, "10")))
        services.actualizar_cuenta(self.bancos, usuario=self.contador, datos={"activa": False})
        reversion = services.revertir_asiento(original, usuario=self.contador, motivo="x", fecha=date(2026, 3, 15))
        self.assertEqual(reversion.estado, EA.CONTABILIZADO)


class ReglasRelacionadasTests(BaseAsientos):
    def test_no_se_cierra_periodo_con_borradores(self):
        asiento = self.borrador(fecha=date(2026, 1, 10))
        enero = PeriodoContable.objects.get(anio=2026, mes=1)
        with self.assertRaisesMessage(ValidationError, "borrador"):
            services.cerrar_periodo(enero, usuario=self.contador)
        services.contabilizar_asiento(asiento, usuario=self.contador)
        services.cerrar_periodo(enero, usuario=self.contador)

    def test_cuenta_con_movimientos_no_se_elimina_ni_agrupa(self):
        self.borrador()
        with self.assertRaisesMessage(ValidationError, "movimientos"):
            services.eliminar_cuenta(self.caja, usuario=self.contador)
        with self.assertRaises(ValidationError):
            services.actualizar_cuenta(self.caja, usuario=self.contador, datos={"acepta_movimientos": False})


class AsientosApiTests(BaseAsientos):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)

    def cuerpo(self, debe="250.75", haber="250.75"):
        return {
            "fecha": "2026-04-05",
            "concepto": "Pago de energía",
            "referencia": "FAC-123",
            "lineas": [
                {"cuenta": self.salarios.pk, "debe": debe, "haber": "0", "descripcion": "Abril"},
                {"cuenta": self.caja.pk, "debe": "", "haber": haber},
            ],
        }

    def test_flujo_completo(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post("/api/asientos/", self.cuerpo(haber="200"), format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(resp.data["total_debe"], "250.75")
        self.assertFalse(resp.data["cuadrado"])
        self.assertEqual(len(resp.data["lineas"]), 2)

        resp = self.client.post(f"/api/asientos/{pk}/contabilizar/")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Partida doble", resp.data["detail"])

        resp = self.client.put(f"/api/asientos/{pk}/", self.cuerpo(), format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        resp = self.client.post(f"/api/asientos/{pk}/contabilizar/")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["codigo"], "2026-000001")

        self.assertEqual(self.client.put(f"/api/asientos/{pk}/", self.cuerpo(), format="json").status_code, 400)
        self.assertEqual(self.client.delete(f"/api/asientos/{pk}/").status_code, 400)

        resp = self.client.post(f"/api/asientos/{pk}/revertir/", {"fecha": "2026-04-06", "motivo": "Duplicado"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["reversion_de"]["codigo"], "2026-000001")
        detalle = self.client.get(f"/api/asientos/{pk}/").data
        self.assertEqual(detalle["revertido_por"]["codigo"], "2026-000002")

        listado = self.client.get("/api/asientos/", {"tipo": "REVERSION"}).data
        self.assertEqual(listado["count"], 1)
        listado = self.client.get("/api/asientos/", {"cuenta": self.caja.pk}).data
        self.assertEqual(listado["count"], 2)

    def test_errores_de_lineas_por_api(self):
        self.client.force_authenticate(self.contador)
        cuerpo = self.cuerpo()
        cuerpo["lineas"][0]["debe"] = "-1"
        resp = self.client.post("/api/asientos/", cuerpo, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Línea 1", resp.data["lineas"][0])

    def test_auditor_solo_consulta(self):
        asiento = self.contabilizado()
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/asientos/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/asientos/{asiento.pk}/").status_code, 200)
        self.assertEqual(self.client.post("/api/asientos/", self.cuerpo(), format="json").status_code, 403)
        resp = self.client.post(f"/api/asientos/{asiento.pk}/revertir/", {"motivo": "x"}, format="json")
        self.assertEqual(resp.status_code, 403)
