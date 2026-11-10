"""Pruebas del catálogo básico de proveedores (T2.2)."""
from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from usuarios import roles
from usuarios.models import Bitacora

from . import services
from .models import Proveedor


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class ProveedoresTests(TestCase):
    def setUp(self):
        self.tesorero = crear_usuario("tesorero", roles.TESORERO)

    def crear(self, nit="0614-010101-101-1", nombre="Proveedor, S.A.", **kwargs):
        return services.crear_proveedor(usuario=self.tesorero, nit=nit, nombre=nombre, **kwargs)

    def test_alta_con_bitacora(self):
        proveedor = self.crear(nrc="1234-5")
        self.assertTrue(proveedor.activo)
        evento = Bitacora.objects.get(entidad="proveedor", accion=Bitacora.Accion.CREAR)
        self.assertEqual(evento.valor_nuevo["nit"], "0614-010101-101-1")

    def test_nit_unico_y_formato(self):
        self.crear()
        with self.assertRaises(ValidationError):
            self.crear(nombre="Otro")
        with self.assertRaises(ValidationError):
            self.crear(nit="ABC-123")

    def test_modificar_y_desactivar(self):
        proveedor = self.crear()
        proveedor = services.actualizar_proveedor(
            proveedor, usuario=self.tesorero, datos={"nombre": "Nuevo nombre", "activo": False}
        )
        self.assertFalse(proveedor.activo)
        evento = Bitacora.objects.get(entidad="proveedor", accion=Bitacora.Accion.MODIFICAR)
        self.assertEqual(evento.valor_anterior["nombre"], "Proveedor, S.A.")

    def test_eliminar_sin_uso(self):
        services.eliminar_proveedor(self.crear(), usuario=self.tesorero)
        self.assertFalse(Proveedor.objects.exists())


class ProveedoresApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tesorero = crear_usuario("tesorero", roles.TESORERO)
        self.jefe = crear_usuario("jefe", roles.JEFE_AREA)

    def test_permisos_y_crud(self):
        datos = {"nit": "0614-010101-101-1", "nombre": "Proveedor, S.A."}
        self.client.force_authenticate(self.jefe)
        self.assertEqual(self.client.post("/api/proveedores/", datos, format="json").status_code, 403)
        self.client.force_authenticate(self.tesorero)
        resp = self.client.post("/api/proveedores/", datos, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(self.client.post("/api/proveedores/", datos, format="json").status_code, 400)
        resp = self.client.patch(f"/api/proveedores/{pk}/", {"activo": False}, format="json")
        self.assertFalse(resp.data["activo"])
        self.client.force_authenticate(self.jefe)
        self.assertEqual(self.client.get("/api/proveedores/", {"q": "prov"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/proveedores/", {"activo": "true"}).data["count"], 0)
