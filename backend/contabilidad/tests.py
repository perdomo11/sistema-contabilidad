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


def crear_centro_prueba(usuario, codigo="01", **kwargs):
    """Centro de costo de detalle vigente desde 2020 (para las pruebas de asientos y libros)."""
    from datetime import date as _date

    from centros_costo.models import CentroCosto
    from centros_costo.services import crear_centro

    datos = {
        "nombre": "Contabilidad",
        "tipo": CentroCosto.Tipo.COSTO,
        "clase": CentroCosto.Clase.DEPARTAMENTO,
        "vigente_desde": _date(2020, 1, 1),
        **kwargs,
    }
    return crear_centro(usuario=usuario, codigo=codigo, **datos)


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
        self.centro = crear_centro_prueba(c)

    def lineas(self, *pares):
        """pares: (cuenta, debe, haber)"""
        return [
            {"cuenta": cuenta, "centro_costo": self.centro, "debe": debe, "haber": haber} for cuenta, debe, haber in pares
        ]

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
                {"cuenta": self.salarios.pk, "centro_costo": self.centro.pk, "debe": debe, "haber": "0", "descripcion": "Abril"},
                {"cuenta": self.caja.pk, "centro_costo": self.centro.pk, "debe": "", "haber": haber},
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


# =============================================================================
# Libros: diario, mayor y balanza (T1.4)
# =============================================================================

from . import libros  # noqa: E402


class BaseLibros(TestCase):
    """Catálogo y movimientos:
    - 10/02: Caja D 1000 / Depósitos H 1000
    - 05/03: Salarios D 300 / Caja H 300
    - 20/03: Otro activo (112) D 50 / Bancos H 50
    - 25/03: borrador Caja D 999 / Depósitos H 999 (no cuenta)
    """

    def setUp(self):
        c = self.contador = crear_usuario("contador", roles.CONTADOR)
        crear = lambda **kw: services.crear_cuenta(usuario=c, **kw)  # noqa: E731
        activo = crear(codigo="1", nombre="Activo", tipo=T.ACTIVO, acepta_movimientos=False)
        self.fondos = crear(codigo="11", nombre="Fondos", padre=activo, acepta_movimientos=False)
        self.caja = crear(codigo="1101", nombre="Caja", padre=self.fondos)
        self.bancos = crear(codigo="1102", nombre="Bancos", padre=self.fondos)
        # Hija directa de "1" cuyo código empieza con "11" pero NO es subcuenta de "11".
        self.otro = crear(codigo="112", nombre="Otro activo", padre=activo)
        pasivo = crear(codigo="2", nombre="Pasivo", tipo=T.PASIVO, acepta_movimientos=False)
        self.depositos = crear(codigo="2101", nombre="Depósitos", padre=pasivo)
        gastos = crear(codigo="5", nombre="Gastos", tipo=T.GASTO, acepta_movimientos=False)
        self.salarios = crear(codigo="5201", nombre="Salarios", padre=gastos)
        crear(codigo="9", nombre="Orden sin uso", tipo=T.ORDEN)
        services.crear_ejercicio(usuario=c, anio=2026)
        self.centro = crear_centro_prueba(c)

        self.registrar(date(2026, 2, 10), (self.caja, "1000", 0), (self.depositos, 0, "1000"))
        self.registrar(date(2026, 3, 5), (self.salarios, "300", 0), (self.caja, 0, "300"))
        self.registrar(date(2026, 3, 20), (self.otro, "50", 0), (self.bancos, 0, "50"))
        self.registrar(date(2026, 3, 25), (self.caja, "999", 0), (self.depositos, 0, "999"), contabilizar=False)

    def registrar(self, fecha, *pares, contabilizar=True):
        asiento = services.crear_asiento(
            usuario=self.contador,
            fecha=fecha,
            concepto=f"Movimiento {fecha}",
            lineas=[{"cuenta": cta, "centro_costo": self.centro, "debe": d, "haber": h} for cta, d, h in pares],
        )
        if contabilizar:
            asiento = services.contabilizar_asiento(asiento, usuario=self.contador)
        return asiento

    MARZO = {"desde": date(2026, 3, 1), "hasta": date(2026, 3, 31)}


class BalanzaTests(BaseLibros):
    def fila(self, balanza, codigo):
        return next(f for f in balanza["filas"] if f["codigo"] == codigo)

    def test_saldos_por_cuenta_y_cuadre(self):
        b = libros.balanza_comprobacion(**self.MARZO)
        caja = self.fila(b, "1101")
        self.assertEqual(
            (caja["inicial_deudor"], caja["cargos"], caja["abonos"], caja["final_deudor"]),
            ("1000.00", "0.00", "300.00", "700.00"),
        )
        depositos = self.fila(b, "2101")
        self.assertEqual((depositos["inicial_acreedor"], depositos["final_acreedor"]), ("1000.00", "1000.00"))
        self.assertEqual(self.fila(b, "1102")["final_acreedor"], "50.00")
        self.assertTrue(b["cuadra"])
        self.assertEqual(
            b["totales"],
            {
                "inicial_deudor": "1000.00",
                "inicial_acreedor": "1000.00",
                "cargos": "350.00",
                "abonos": "350.00",
                "final_deudor": "1050.00",
                "final_acreedor": "1050.00",
            },
        )

    def test_borradores_no_cuentan(self):
        b = libros.balanza_comprobacion(**self.MARZO)
        self.assertEqual(self.fila(b, "1101")["cargos"], "0.00")

    def test_agrupacion_suma_solo_descendientes(self):
        b = libros.balanza_comprobacion(**self.MARZO)
        fondos = self.fila(b, "11")  # Caja + Bancos, sin "112"
        self.assertEqual((fondos["inicial_deudor"], fondos["abonos"], fondos["final_deudor"]), ("1000.00", "350.00", "650.00"))
        self.assertEqual(fondos["cargos"], "0.00")
        activo = self.fila(b, "1")
        self.assertEqual((activo["cargos"], activo["abonos"], activo["final_deudor"]), ("50.00", "350.00", "700.00"))

    def test_filtro_por_nivel_no_altera_totales(self):
        completa = libros.balanza_comprobacion(**self.MARZO)
        nivel1 = libros.balanza_comprobacion(**self.MARZO, nivel=1)
        self.assertEqual([f["codigo"] for f in nivel1["filas"]], ["1", "2", "5"])
        self.assertEqual(nivel1["totales"], completa["totales"])

    def test_cuentas_sin_movimiento(self):
        sin = libros.balanza_comprobacion(**self.MARZO)
        con = libros.balanza_comprobacion(**self.MARZO, incluir_sin_movimiento=True)
        self.assertNotIn("9", [f["codigo"] for f in sin["filas"]])
        self.assertEqual(len(con["filas"]), Cuenta.objects.count())

    def test_rango_invalido(self):
        with self.assertRaises(ValidationError):
            libros.balanza_comprobacion(desde=date(2026, 3, 31), hasta=date(2026, 3, 1))


class MayorTests(BaseLibros):
    def test_saldo_corriente_cuenta_deudora(self):
        m = libros.libro_mayor(cuenta=self.caja, **self.MARZO)
        self.assertEqual(m["saldo_inicial"], "1000.00")
        self.assertEqual([(x["haber"], x["saldo"]) for x in m["movimientos"]], [("300.00", "700.00")])
        self.assertEqual(m["saldo_final"], "700.00")

    def test_saldo_positivo_en_cuenta_acreedora(self):
        m = libros.libro_mayor(cuenta=self.depositos, desde=date(2026, 1, 1), hasta=date(2026, 12, 31))
        self.assertEqual(m["saldo_inicial"], "0.00")
        self.assertEqual(m["saldo_final"], "1000.00")  # el borrador de 999 no cuenta

    def test_mayor_de_agrupacion_incluye_subcuentas_reales(self):
        m = libros.libro_mayor(cuenta=self.fondos, **self.MARZO)
        self.assertEqual(sorted(x["cuenta_codigo"] for x in m["movimientos"]), ["1101", "1102"])
        self.assertEqual((m["saldo_inicial"], m["saldo_final"]), ("1000.00", "650.00"))
        self.assertEqual(m["totales"], {"debe": "0.00", "haber": "350.00"})


class DiarioTests(BaseLibros):
    def test_orden_totales_y_exclusion_de_borradores(self):
        asientos, totales = libros.libro_diario(**self.MARZO)
        self.assertEqual([a.fecha for a in asientos], [date(2026, 3, 5), date(2026, 3, 20)])
        self.assertEqual(totales, {"debe": "350.00", "haber": "350.00"})


class LibrosApiTests(BaseLibros):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))

    def test_endpoints(self):
        rango = {"desde": "2026-03-01", "hasta": "2026-03-31"}
        resp = self.client.get("/api/libros/diario/", rango)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 2)
        self.assertEqual(resp.data["totales"]["debe"], "350.00")
        self.assertEqual(len(resp.data["results"][0]["lineas"]), 2)

        resp = self.client.get("/api/libros/mayor/", {**rango, "cuenta": self.caja.pk})
        self.assertEqual(resp.data["saldo_final"], "700.00")

        resp = self.client.get("/api/libros/balanza/", {**rango, "nivel": 2})
        self.assertTrue(resp.data["cuadra"])
        self.assertTrue(all(f["nivel"] <= 2 for f in resp.data["filas"]))

    def test_validaciones(self):
        self.assertEqual(self.client.get("/api/libros/balanza/").status_code, 400)
        resp = self.client.get("/api/libros/diario/", {"desde": "2026-03-31", "hasta": "2026-03-01"})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("hasta", resp.data)

    def test_requiere_sesion(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/libros/balanza/", {"desde": "2026-01-01", "hasta": "2026-12-31"}).status_code, 401)


# =============================================================================
# Regla 3: centro de costo en las líneas (T2.1)
# =============================================================================


class CentroEnLineasTests(BaseAsientos):
    def sin_centro(self, *pares):
        return [{"cuenta": c, "centro_costo": None, "debe": d, "haber": h} for c, d, h in pares]

    def test_cuenta_no_exenta_exige_centro(self):
        with self.assertRaisesMessage(ValidationError, "exige centro de costo"):
            self.borrador(lineas=self.sin_centro((self.salarios, "10", 0), (self.caja, 0, "10")))

    def test_cuenta_exenta_no_exige_centro(self):
        services.actualizar_cuenta(self.caja, usuario=self.contador, datos={"exenta_centro_costo": True})
        lineas = [
            {"cuenta": self.salarios, "centro_costo": self.centro, "debe": "10", "haber": 0},
            {"cuenta": self.caja, "centro_costo": None, "debe": 0, "haber": "10"},
        ]
        asiento = services.contabilizar_asiento(self.borrador(lineas=lineas), usuario=self.contador)
        self.assertEqual(asiento.estado, EA.CONTABILIZADO)

    def test_centro_de_agrupacion_o_no_vigente(self):
        agrupacion = crear_centro_prueba(self.contador, codigo="02", nombre="Agencia", acepta_movimientos=False)
        futuro = crear_centro_prueba(self.contador, codigo="03", nombre="Nueva", vigente_desde=date(2026, 6, 1))
        for centro, mensaje in ((agrupacion, "agrupación"), (futuro, "no está vigente")):
            lineas = [
                {"cuenta": self.salarios, "centro_costo": centro, "debe": "10", "haber": 0},
                {"cuenta": self.caja, "centro_costo": self.centro, "debe": 0, "haber": "10"},
            ]
            with self.subTest(centro=centro.codigo), self.assertRaisesMessage(ValidationError, mensaje):
                self.borrador(lineas=lineas)

    def test_trigger_exige_centro(self):
        asiento = self.borrador()
        LineaAsiento.objects.filter(asiento=asiento).update(centro_costo=None)  # borrador: permitido en BD
        with self.assertRaises(DatabaseError), transaction.atomic():
            Asiento.objects.filter(pk=asiento.pk).update(
                estado=EA.CONTABILIZADO,
                ejercicio=2026,
                numero=99,
                total_debe=D("1500"),
                total_haber=D("1500"),
                contabilizado_por=self.contador,
                contabilizado_en=timezone.now(),
            )

    def test_reversion_copia_el_centro_aunque_ya_no_este_vigente(self):
        from centros_costo.services import actualizar_centro

        original = self.contabilizado()
        actualizar_centro(self.centro, usuario=self.contador, datos={"vigente_hasta": date(2026, 3, 31)})
        reversion = services.revertir_asiento(original, usuario=self.contador, motivo="x", fecha=date(2026, 4, 10))
        self.assertEqual(reversion.estado, EA.CONTABILIZADO)
        self.assertTrue(all(l.centro_costo_id == self.centro.pk for l in reversion.lineas.all()))

    def test_salida_api_incluye_centro(self):
        asiento = self.contabilizado()
        client = APIClient()
        client.force_authenticate(self.contador)
        linea = client.get(f"/api/asientos/{asiento.pk}/").data["lineas"][0]
        self.assertEqual((linea["centro_costo"], linea["centro_codigo"]), (self.centro.pk, "01"))


# =============================================================================
# Exportación a Excel (T7.1)
# =============================================================================

from io import BytesIO  # noqa: E402

from django.test import override_settings  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from config.excel import FILA_TITULOS, FORMATO_MONTO  # noqa: E402


@override_settings(EMPRESA_NOMBRE="Banco de Prueba, S.A.", EMPRESA_NIT="0614-010101-101-1", EMPRESA_NRC="1111-1")
class ExportacionExcelTests(BaseLibros):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.client.force_authenticate(crear_usuario("auditor", roles.AUDITOR))

    def hoja(self, url, params=None):
        resp = self.client.get(url, params or {})
        self.assertEqual(resp.status_code, 200, getattr(resp, "data", None))
        self.assertEqual(resp["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertIn("attachment;", resp["Content-Disposition"])
        return load_workbook(BytesIO(resp.content)).active

    def filas(self, ws):
        return [list(f) for f in ws.iter_rows(min_row=FILA_TITULOS + 1, values_only=True)]

    def fila(self, ws, texto):
        return next(f for f in self.filas(ws) if texto in f)

    def test_encabezado_y_formato_comun(self):
        ws = self.hoja("/api/libros/diario/exportar/", {"desde": "2026-03-01", "hasta": "2026-03-31"})
        self.assertEqual(ws["A1"].value, "Banco de Prueba, S.A.")
        self.assertIn("NIT: 0614-010101-101-1", ws["A2"].value)
        self.assertIn("NRC: 1111-1", ws["A2"].value)
        self.assertEqual(ws["A3"].value, "Libro diario")
        self.assertEqual(ws["A4"].value, "Del 01/03/2026 al 31/03/2026")
        self.assertEqual(ws.freeze_panes, f"A{FILA_TITULOS + 1}")
        self.assertEqual(ws.cell(row=FILA_TITULOS, column=7).value, "Cargo")
        self.assertTrue(all(ws.column_dimensions[c].width > 0 for c in "ABCDEFGH"))

    def test_diario_partidas_lineas_y_totales(self):
        ws = self.hoja("/api/libros/diario/exportar/", {"desde": "2026-03-01", "hasta": "2026-03-31"})
        filas = self.filas(ws)
        partidas = [f for f in filas if f[1] and f[1].startswith("2026-")]
        self.assertEqual(len(partidas), 2)  # el borrador del 25/03 no aparece
        self.assertEqual(partidas[0][0].date(), date(2026, 3, 5))
        salarios = self.fila(ws, "Salarios")
        self.assertEqual((salarios[6], salarios[7]), (300, None))
        totales = self.fila(ws, "TOTALES DEL PERIODO")
        self.assertEqual((totales[6], totales[7]), (350, 350))
        # Montos como número con 2 decimales, no como texto.
        celda = next(c for c in ws["G"] if c.value == 350)
        self.assertEqual(celda.number_format, FORMATO_MONTO)
        self.assertIsInstance(celda.value, (int, float))

    def test_mayor_de_una_cuenta(self):
        ws = self.hoja("/api/libros/mayor/exportar/", {"desde": "2026-03-01", "hasta": "2026-03-31", "cuenta": self.caja.pk})
        self.assertEqual(ws["A3"].value, "Libro mayor: 1101 Caja")
        self.assertEqual(self.fila(ws, "Saldo inicial")[8], 1000)
        final = self.fila(ws, "Totales y saldo final 1101")
        self.assertEqual((final[6], final[7], final[8]), (0, 300, 700))

    def test_mayor_general_todas_las_cuentas_con_saldo_o_movimiento(self):
        ws = self.hoja("/api/libros/mayor/exportar/", {"desde": "2026-03-01", "hasta": "2026-03-31"})
        grupos = [f[2] for f in self.filas(ws) if f[2] and "(naturaleza" in f[2]]
        self.assertEqual([g.split()[0] for g in grupos], ["1101", "1102", "112", "2101", "5201"])
        totales = self.fila(ws, "TOTALES DEL PERIODO")
        self.assertEqual((totales[6], totales[7]), (350, 350))
        depositos = self.fila(ws, "Totales y saldo final 2101")
        self.assertEqual(depositos[8], 1000)  # saldo inicial sin movimientos en marzo

    def test_mayor_general_servicio_igual_al_mayor_por_cuenta(self):
        general = {m["cuenta"]["codigo"]: m for m in libros.libro_mayor_general(**self.MARZO)}
        for cuenta in (self.caja, self.bancos, self.depositos, self.salarios):
            self.assertEqual(general[cuenta.codigo], libros.libro_mayor(cuenta=cuenta, **self.MARZO))

    def test_catalogo_con_filtros(self):
        ws = self.hoja("/api/cuentas/exportar/")
        titulos = [c.value for c in ws[FILA_TITULOS]]
        self.assertEqual(
            titulos,
            ["Código", "Nombre de la cuenta", "Nivel", "Tipo", "Naturaleza", "Acepta movimientos", "Activa", "Cuenta padre"],
        )
        filas = [f for f in self.filas(ws) if f[2]]
        self.assertEqual(len(filas), Cuenta.objects.count())
        caja = next(f for f in filas if f[0] == "1101")
        self.assertEqual((caja[2], caja[3], caja[5], caja[6], caja[7]), (3, "Activo", "Sí", "Sí", "11 Fondos"))

        ws = self.hoja("/api/cuentas/exportar/", {"tipo": "GASTO"})
        self.assertEqual([f[0] for f in self.filas(ws) if f[2]], ["5", "5201"])

    def test_validaciones_y_permisos(self):
        resp = self.client.get("/api/libros/diario/exportar/", {"desde": "2026-03-31", "hasta": "2026-03-01"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.client.get("/api/libros/mayor/exportar/").status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/cuentas/exportar/").status_code, 401)
