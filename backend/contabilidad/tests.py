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
