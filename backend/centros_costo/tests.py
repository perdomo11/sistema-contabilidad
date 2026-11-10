from datetime import date
from io import StringIO

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from contabilidad import services as contabilidad
from contabilidad.models import Cuenta
from usuarios import roles
from usuarios.models import Bitacora

from . import services
from .models import CentroCosto

T, C = CentroCosto.Tipo, CentroCosto.Clase
ENERO = date(2026, 1, 1)


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!", first_name=username.title())
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BaseCentros(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)
        self.matriz = self.crear("01", "Casa matriz", tipo=T.UTILIDAD, clase=C.SUCURSAL, acepta_movimientos=False)
        self.contabilidad = self.crear("01-01", "Contabilidad", padre=self.matriz)

    def crear(self, codigo, nombre, **kwargs):
        datos = {"tipo": T.COSTO, "clase": C.DEPARTAMENTO, "vigente_desde": ENERO, **kwargs}
        return services.crear_centro(usuario=self.contador, codigo=codigo, nombre=nombre, **datos)

    def actualizar(self, centro, **datos):
        return services.actualizar_centro(centro, usuario=self.contador, datos=datos)

    def registrar_movimiento(self, centro, fecha=date(2026, 3, 10)):
        """Asiento en borrador con una línea en el centro indicado."""
        gasto = contabilidad.crear_cuenta(
            usuario=self.contador, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO
        )
        if not contabilidad_periodo_existe(fecha.year):
            contabilidad.crear_ejercicio(usuario=self.contador, anio=fecha.year)
        return contabilidad.crear_asiento(
            usuario=self.contador,
            fecha=fecha,
            concepto="Movimiento",
            lineas=[{"cuenta": gasto, "centro_costo": centro, "debe": "10", "haber": 0}],
        )


def contabilidad_periodo_existe(anio):
    from contabilidad.models import PeriodoContable

    return PeriodoContable.objects.filter(anio=anio).exists()


class CrearCentroTests(BaseCentros):
    def test_jerarquia_nivel_y_codigo_en_mayusculas(self):
        hijo = self.crear("01-01-a", "Sección", padre=self.actualizar(self.contabilidad, acepta_movimientos=False))
        self.assertEqual((hijo.codigo, hijo.nivel), ("01-01-A", 3))
        self.assertTrue(Bitacora.objects.filter(entidad="centro_costo", accion=Bitacora.Accion.CREAR).exists())

    def test_reglas_de_codigo_y_padre(self):
        casos = {
            "sin prefijo del padre": lambda: self.crear("02-01", "X", padre=self.matriz),
            "duplicado": lambda: self.crear("01", "X"),
            "caracteres inválidos": lambda: self.crear("01_9", "X", padre=self.matriz),
            "padre de detalle": lambda: self.crear("01-01-01", "X", padre=self.contabilidad),
        }
        for nombre, accion in casos.items():
            with self.subTest(nombre), self.assertRaises(ValidationError):
                accion()

    def test_vigencia_contenida_en_la_del_padre(self):
        with self.assertRaises(ValidationError):
            self.crear("01-09", "Antes que el padre", padre=self.matriz, vigente_desde=date(2025, 12, 1))
        self.actualizar(self.contabilidad, vigente_hasta=date(2026, 12, 31))
        self.actualizar(self.matriz, vigente_hasta=date(2026, 12, 31))
        with self.assertRaises(ValidationError):
            self.crear("01-09", "Sin fin con padre que cierra", padre=self.matriz)
        self.crear("01-09", "Contenida", padre=self.matriz, vigente_hasta=date(2026, 6, 30))

    def test_vigencia_hasta_anterior_a_desde(self):
        with self.assertRaises(ValidationError):
            self.crear("02", "X", vigente_hasta=date(2025, 12, 31))

    def test_constraint_bd_vigencia(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            CentroCosto.objects.filter(pk=self.matriz.pk).update(vigente_hasta=date(2025, 1, 1))


class ActualizarCentroTests(BaseCentros):
    def test_no_se_cierra_padre_con_subunidades_vigentes(self):
        with self.assertRaisesMessage(ValidationError, "subunidades"):
            self.actualizar(self.matriz, vigente_hasta=date(2026, 6, 30))
        self.actualizar(self.contabilidad, vigente_hasta=date(2026, 6, 30))
        self.actualizar(self.matriz, vigente_hasta=date(2026, 6, 30))
        evento = Bitacora.objects.filter(entidad="centro_costo", accion=Bitacora.Accion.MODIFICAR).latest("id")
        self.assertEqual(evento.valor_nuevo["vigente_hasta"], "2026-06-30")

    def test_codigo_y_padre_inmutables(self):
        for datos in ({"codigo": "09"}, {"padre": None}):
            with self.subTest(datos=datos), self.assertRaises(ValidationError):
                services.actualizar_centro(self.contabilidad, usuario=self.contador, datos=datos)

    def test_agrupacion_y_detalle(self):
        with self.assertRaises(ValidationError):
            self.actualizar(self.matriz, acepta_movimientos=True)  # tiene subunidades
        self.registrar_movimiento(self.contabilidad)
        with self.assertRaisesMessage(ValidationError, "movimientos"):
            self.actualizar(self.contabilidad, acepta_movimientos=False)

    def test_vigencia_no_puede_dejar_movimientos_fuera(self):
        self.registrar_movimiento(self.contabilidad, fecha=date(2026, 3, 10))
        with self.assertRaisesMessage(ValidationError, "fuera de la nueva vigencia"):
            self.actualizar(self.contabilidad, vigente_hasta=date(2026, 2, 28))
        self.actualizar(self.contabilidad, vigente_hasta=date(2026, 3, 31))

    def test_responsable_inactivo(self):
        inactivo = crear_usuario("ex", roles.JEFE_AREA)
        inactivo.is_active = False
        inactivo.save()
        with self.assertRaises(ValidationError):
            self.actualizar(self.contabilidad, responsable=inactivo)


class EliminarCentroTests(BaseCentros):
    def test_reglas_de_eliminacion(self):
        with self.assertRaisesMessage(ValidationError, "subunidades"):
            services.eliminar_centro(self.matriz, usuario=self.contador)
        self.registrar_movimiento(self.contabilidad)
        with self.assertRaisesMessage(ValidationError, "movimientos"):
            services.eliminar_centro(self.contabilidad, usuario=self.contador)
        libre = self.crear("01-02", "Libre", padre=self.matriz)
        services.eliminar_centro(libre, usuario=self.contador)
        self.assertFalse(CentroCosto.objects.filter(codigo="01-02").exists())
        self.assertTrue(Bitacora.objects.filter(entidad="centro_costo", accion=Bitacora.Accion.ELIMINAR).exists())


class ConsultasTests(BaseCentros):
    def test_vigente_en_y_arbol(self):
        self.crear("02", "Agencia cerrada", vigente_hasta=date(2026, 3, 31))
        vigentes = services.consultar_centros(vigente_en=date(2026, 5, 1))
        self.assertEqual([c.codigo for c in vigentes], ["01", "01-01"])
        arbol = services.arbol_centros()
        self.assertEqual([n["codigo"] for n in arbol], ["01", "02"])
        self.assertEqual(arbol[0]["hijos"][0]["codigo"], "01-01")


class CentrosApiTests(BaseCentros):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)
        self.jefe = crear_usuario("jefe", roles.JEFE_AREA)

    def test_lectura_para_todos_y_escritura_solo_contador(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/centros-costo/").data["count"], 2)
        self.assertEqual(self.client.get("/api/centros-costo/arbol/").status_code, 200)
        datos = {"codigo": "02", "nombre": "X", "tipo": "COSTO", "clase": "AREA", "vigente_desde": "2026-01-01"}
        self.assertEqual(self.client.post("/api/centros-costo/", datos, format="json").status_code, 403)

    def test_crud_como_contador(self):
        self.client.force_authenticate(self.contador)
        datos = {
            "codigo": "01-02",
            "nombre": "Créditos",
            "padre": self.matriz.pk,
            "tipo": "UTILIDAD",
            "clase": "DEPARTAMENTO",
            "responsable": self.jefe.pk,
            "vigente_desde": "2026-01-01",
        }
        resp = self.client.post("/api/centros-costo/", datos, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["responsable_nombre"], "Jefe")
        pk = resp.data["id"]
        resp = self.client.patch(f"/api/centros-costo/{pk}/", {"vigente_hasta": "2026-12-31"}, format="json")
        self.assertEqual(resp.data["vigente_hasta"], "2026-12-31")
        resp = self.client.patch(f"/api/centros-costo/{pk}/", {"codigo": "09"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self.client.delete(f"/api/centros-costo/{pk}/").status_code, 204)

    def test_usuarios_por_rol(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.get("/api/usuarios/", {"rol": roles.JEFE_AREA})
        self.assertEqual([u["username"] for u in resp.data], ["jefe"])


class CargarCentrosBaseTests(TestCase):
    def test_carga_idempotente(self):
        crear_usuario("contador", roles.CONTADOR)
        call_command("cargar_centros_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        total = CentroCosto.objects.count()
        self.assertEqual(total, 18)
        call_command("cargar_centros_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        self.assertEqual(CentroCosto.objects.count(), total)
        for centro in CentroCosto.objects.all():
            self.assertEqual(centro.acepta_movimientos, not centro.hijos.exists(), centro.codigo)
