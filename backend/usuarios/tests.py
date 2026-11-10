from django.contrib.auth.models import Group, User
from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from . import roles
from .models import Bitacora, BitacoraInmutableError
from .services import registrar_evento, tiene_rol

CONTRASENA = "Prueba_2026!"


def crear_usuario(username, *nombres_roles, **extra):
    usuario = User.objects.create_user(username=username, password=CONTRASENA, **extra)
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class RolesTests(TestCase):
    def test_migracion_crea_los_cuatro_roles(self):
        self.assertEqual(set(Group.objects.filter(name__in=roles.TODOS).values_list("name", flat=True)), set(roles.TODOS))

    def test_tiene_rol(self):
        contador = crear_usuario("c1", roles.CONTADOR)
        admin = User.objects.create_superuser("admin1", password=CONTRASENA)
        self.assertTrue(tiene_rol(contador, roles.CONTADOR))
        self.assertFalse(tiene_rol(contador, roles.AUDITOR))
        self.assertTrue(tiene_rol(admin, roles.AUDITOR))

    def test_usuario_inactivo_no_tiene_roles(self):
        contador = crear_usuario("c2", roles.CONTADOR, is_active=False)
        self.assertFalse(tiene_rol(contador, roles.CONTADOR))


class AutenticacionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.contador = crear_usuario("contador", roles.CONTADOR)

    def login(self, username="contador", password=CONTRASENA):
        return self.client.post("/api/auth/login/", {"username": username, "password": password}, format="json")

    def test_login_correcto_devuelve_tokens_y_roles_y_queda_en_bitacora(self):
        resp = self.login()
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)
        self.assertEqual(resp.data["usuario"]["roles"], [roles.CONTADOR])
        evento = Bitacora.objects.get(accion=Bitacora.Accion.LOGIN)
        self.assertEqual(evento.usuario, self.contador)

    def test_login_fallido_devuelve_401_y_queda_en_bitacora(self):
        resp = self.login(password="incorrecta")
        self.assertEqual(resp.status_code, 401)
        evento = Bitacora.objects.get(accion=Bitacora.Accion.LOGIN_FALLIDO)
        self.assertIsNone(evento.usuario)
        self.assertEqual(evento.nombre_usuario, "contador")

    def test_endpoint_protegido_sin_token_responde_401(self):
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_health_es_publico(self):
        self.assertEqual(self.client.get("/api/health/").status_code, 200)

    def test_me_con_token(self):
        access = self.login().data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        resp = self.client.get("/api/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "contador")

    def test_logout_invalida_el_refresh(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        resp = self.client.post("/api/auth/logout/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Bitacora.objects.filter(accion=Bitacora.Accion.LOGOUT, usuario=self.contador).exists())
        self.client.credentials()
        resp = self.client.post("/api/auth/refresh/", {"refresh": tokens["refresh"]}, format="json")
        self.assertEqual(resp.status_code, 401)


class BitacoraApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)
        self.contador = crear_usuario("contador", roles.CONTADOR)
        registrar_evento(Bitacora.Accion.LOGIN, usuario=self.contador)

    def test_auditor_puede_consultar_bitacora(self):
        self.client.force_authenticate(self.auditor)
        resp = self.client.get("/api/bitacora/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["count"], 1)

    def test_filtro_por_accion(self):
        registrar_evento(Bitacora.Accion.LOGOUT, usuario=self.contador)
        self.client.force_authenticate(self.auditor)
        resp = self.client.get("/api/bitacora/", {"accion": "LOGOUT"})
        self.assertEqual(resp.data["count"], 1)

    def test_contador_no_puede_consultar_bitacora(self):
        self.client.force_authenticate(self.contador)
        self.assertEqual(self.client.get("/api/bitacora/").status_code, 403)


class BitacoraInmutableTests(TestCase):
    def setUp(self):
        self.evento = registrar_evento(Bitacora.Accion.LOGIN, nombre_usuario="x", descripcion="original")

    def test_modelo_impide_modificar(self):
        self.evento.descripcion = "alterada"
        with self.assertRaises(BitacoraInmutableError):
            self.evento.save()

    def test_modelo_impide_borrar(self):
        with self.assertRaises(BitacoraInmutableError):
            self.evento.delete()
        with self.assertRaises(BitacoraInmutableError):
            Bitacora.objects.all().delete()
        with self.assertRaises(BitacoraInmutableError):
            Bitacora.objects.update(descripcion="alterada")

    def test_trigger_impide_update_en_base_de_datos(self):
        tabla = Bitacora._meta.db_table
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"UPDATE {tabla} SET descripcion = 'alterada' WHERE id = %s", [self.evento.pk])
        self.evento.refresh_from_db()
        self.assertEqual(self.evento.descripcion, "original")

    def test_trigger_impide_delete_en_base_de_datos(self):
        tabla = Bitacora._meta.db_table
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {tabla} WHERE id = %s", [self.evento.pk])
        self.assertTrue(Bitacora.objects.filter(pk=self.evento.pk).exists())


class AdminBitacoraTests(TestCase):
    def test_cambio_de_rol_en_admin_queda_en_bitacora(self):
        admin = User.objects.create_superuser("admin", password=CONTRASENA)
        usuario = crear_usuario("jefe", roles.CONTADOR)
        self.client.force_login(admin)
        datos = {
            "username": "jefe",
            "first_name": "",
            "last_name": "",
            "email": "",
            "is_active": "on",
            "groups": [Group.objects.get(name=roles.JEFE_AREA).pk],
            "last_login_0": "",
            "last_login_1": "",
            "date_joined_0": "2026-01-01",
            "date_joined_1": "00:00:00",
        }
        resp = self.client.post(f"/admin/auth/user/{usuario.pk}/change/", datos)
        self.assertEqual(resp.status_code, 302, getattr(resp, "context_data", {}).get("errors"))
        evento = Bitacora.objects.get(accion=Bitacora.Accion.MODIFICAR, entidad="usuario")
        self.assertEqual(evento.valor_anterior["roles"], [roles.CONTADOR])
        self.assertEqual(evento.valor_nuevo["roles"], [roles.JEFE_AREA])
        self.assertEqual(evento.usuario, admin)
