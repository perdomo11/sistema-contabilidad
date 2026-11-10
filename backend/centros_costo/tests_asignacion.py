"""Pruebas de T2.2: asignación directa y por regla (cuenta→centro, proveedor→centro)."""
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
from tesoreria import services as tesoreria
from usuarios import roles
from usuarios.models import Bitacora

from . import services
from .models import CentroCosto, ReglaAsignacion

T, C = CentroCosto.Tipo, CentroCosto.Clase
ENERO = date(2026, 1, 1)
MARZO = date(2026, 3, 15)


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BaseAsignacion(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)
        c = self.contador
        activo = contabilidad.crear_cuenta(usuario=c, codigo="1", nombre="Activo", tipo=Cuenta.Tipo.ACTIVO, acepta_movimientos=False)
        self.bancos = contabilidad.crear_cuenta(
            usuario=c, codigo="1102", nombre="Bancos", padre=activo, exenta_centro_costo=True
        )
        gastos = contabilidad.crear_cuenta(usuario=c, codigo="5", nombre="Gastos", tipo=Cuenta.Tipo.GASTO, acepta_movimientos=False)
        self.generales = contabilidad.crear_cuenta(
            usuario=c, codigo="5202", nombre="Gastos generales", padre=gastos, acepta_movimientos=False
        )
        self.energia = contabilidad.crear_cuenta(usuario=c, codigo="520201", nombre="Energía", padre=self.generales)
        self.mantenimiento = contabilidad.crear_cuenta(
            usuario=c, codigo="520205", nombre="Mantenimiento", padre=self.generales
        )
        self.salarios = contabilidad.crear_cuenta(usuario=c, codigo="5201", nombre="Salarios", padre=gastos)
        contabilidad.crear_ejercicio(usuario=c, anio=2026)

        self.matriz = self.centro("01", "Casa matriz", acepta_movimientos=False)
        self.gerencia = self.centro("01-01", "Gerencia", padre=self.matriz)
        self.tecnologia = self.centro("01-02", "Tecnología", padre=self.matriz)
        self.rrhh = self.centro("01-03", "Recursos humanos", padre=self.matriz)

        self.software = tesoreria.crear_proveedor(usuario=c, nit="0614-010101-101-1", nombre="Software, S.A.")
        self.vigilancia = tesoreria.crear_proveedor(usuario=c, nit="0614-020202-102-2", nombre="Vigilancia, S.A.")

    def centro(self, codigo, nombre, **kwargs):
        datos = {"tipo": T.COSTO, "clase": C.DEPARTAMENTO, "vigente_desde": ENERO, **kwargs}
        return services.crear_centro(usuario=self.contador, codigo=codigo, nombre=nombre, **datos)

    def regla(self, centro, cuenta=None, proveedor=None, desde=ENERO, hasta=None, descripcion=""):
        return services.crear_regla(
            usuario=self.contador,
            cuenta=cuenta,
            proveedor=proveedor,
            centro_costo=centro,
            vigente_desde=desde,
            vigente_hasta=hasta,
            descripcion=descripcion,
        )

    def borrador(self, cuenta, centro=None, proveedor=None, fecha=MARZO):
        return contabilidad.crear_asiento(
            usuario=self.contador,
            fecha=fecha,
            concepto="Pago",
            proveedor=proveedor,
            lineas=[
                {"cuenta": cuenta, "centro_costo": centro, "debe": "100", "haber": 0},
                {"cuenta": self.bancos, "debe": 0, "haber": "100"},
            ],
        )

    def primera_linea(self, asiento):
        return asiento.lineas.select_related("centro_costo", "regla_asignacion").get(numero_linea=1)


class CrearReglaTests(BaseAsignacion):
    def test_crea_y_registra_en_bitacora(self):
        regla = self.regla(self.gerencia, cuenta=self.energia, descripcion="Energía de matriz")
        self.assertEqual(regla.criterio, "cuenta 520201")
        evento = Bitacora.objects.get(entidad="regla_asignacion", accion=Bitacora.Accion.CREAR)
        self.assertEqual(evento.valor_nuevo["centro_costo"], "01-01")

    def test_requiere_cuenta_o_proveedor(self):
        with self.assertRaises(ValidationError) as ctx:
            self.regla(self.gerencia)
        self.assertIn("cuenta", ctx.exception.message_dict)

    def test_restriccion_de_bd_cuenta_o_proveedor(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ReglaAsignacion.objects.create(
                centro_costo=self.gerencia, vigente_desde=ENERO, creado_por=self.contador, modificado_por=self.contador
            )

    def test_centro_de_agrupacion_no_es_destino(self):
        with self.assertRaises(ValidationError) as ctx:
            self.regla(self.matriz, cuenta=self.energia)
        self.assertIn("centro_costo", ctx.exception.message_dict)

    def test_cuenta_exenta_o_inactiva(self):
        with self.assertRaises(ValidationError):
            self.regla(self.gerencia, cuenta=self.bancos)
        contabilidad.actualizar_cuenta(self.energia, usuario=self.contador, datos={"activa": False})
        with self.assertRaises(ValidationError):
            self.regla(self.gerencia, cuenta=self.energia)

    def test_proveedor_inactivo(self):
        tesoreria.actualizar_proveedor(self.software, usuario=self.contador, datos={"activo": False})
        with self.assertRaises(ValidationError) as ctx:
            self.regla(self.tecnologia, proveedor=self.software)
        self.assertIn("proveedor", ctx.exception.message_dict)

    def test_vigencia_dentro_de_la_del_centro(self):
        with self.assertRaises(ValidationError):
            self.regla(self.gerencia, cuenta=self.energia, desde=date(2025, 12, 1))
        services.actualizar_centro(self.rrhh, usuario=self.contador, datos={"vigente_hasta": date(2026, 6, 30)})
        with self.assertRaises(ValidationError):
            self.regla(self.rrhh, cuenta=self.energia)  # sin fin, pero el centro cierra en junio
        self.regla(self.rrhh, cuenta=self.energia, hasta=date(2026, 6, 30))

    def test_no_se_traslapan_reglas_iguales(self):
        self.regla(self.gerencia, cuenta=self.energia, hasta=date(2026, 6, 30))
        with self.assertRaises(ValidationError):
            self.regla(self.tecnologia, cuenta=self.energia, desde=date(2026, 6, 1))
        # Desde el día siguiente al cierre sí se permite; y otra combinación nunca choca.
        self.regla(self.tecnologia, cuenta=self.energia, desde=date(2026, 7, 1))
        self.regla(self.tecnologia, cuenta=self.energia, proveedor=self.software)


class ActualizarEliminarReglaTests(BaseAsignacion):
    def test_inmutables_y_cierre_de_vigencia(self):
        regla = self.regla(self.gerencia, cuenta=self.energia)
        with self.assertRaises(ValidationError):
            services.actualizar_regla(regla, usuario=self.contador, datos={"centro_costo": self.tecnologia})
        regla = services.actualizar_regla(regla, usuario=self.contador, datos={"vigente_hasta": date(2026, 6, 30)})
        self.assertEqual(regla.vigente_hasta, date(2026, 6, 30))
        self.assertTrue(Bitacora.objects.filter(entidad="regla_asignacion", accion=Bitacora.Accion.MODIFICAR).exists())

    def test_no_deja_fuera_asientos_ya_asignados(self):
        regla = self.regla(self.gerencia, cuenta=self.energia)
        self.borrador(self.energia, fecha=MARZO)
        with self.assertRaises(ValidationError):
            services.actualizar_regla(regla, usuario=self.contador, datos={"vigente_hasta": date(2026, 2, 28)})
        services.actualizar_regla(regla, usuario=self.contador, datos={"vigente_hasta": MARZO})

    def test_eliminar_solo_si_nunca_se_aplico(self):
        libre = self.regla(self.tecnologia, cuenta=self.mantenimiento)
        services.eliminar_regla(libre, usuario=self.contador)
        usada = self.regla(self.gerencia, cuenta=self.energia)
        self.borrador(self.energia)
        with self.assertRaises(ValidationError):
            services.eliminar_regla(usada, usuario=self.contador)

    def test_centro_destino_protegido(self):
        self.regla(self.gerencia, cuenta=self.energia)
        with self.assertRaises(ValidationError):
            services.actualizar_centro(self.gerencia, usuario=self.contador, datos={"vigente_hasta": date(2026, 6, 30)})
        with self.assertRaises(ValidationError):
            services.eliminar_centro(self.gerencia, usuario=self.contador)


class ResolucionTests(BaseAsignacion):
    def test_regla_por_cuenta_y_por_ancestro(self):
        self.regla(self.gerencia, cuenta=self.generales)  # agrupación 5202
        self.assertEqual(services.resolver_regla(self.energia, None, MARZO).centro_costo, self.gerencia)
        especifica = self.regla(self.tecnologia, cuenta=self.energia)
        self.assertEqual(services.resolver_regla(self.energia, None, MARZO), especifica)
        self.assertIsNone(services.resolver_regla(self.salarios, None, MARZO))

    def test_prioridad_proveedor_y_cuenta(self):
        por_cuenta = self.regla(self.gerencia, cuenta=self.mantenimiento)
        solo_proveedor = self.regla(self.rrhh, proveedor=self.software)
        ambos = self.regla(self.tecnologia, cuenta=self.generales, proveedor=self.software)
        self.assertEqual(services.resolver_regla(self.mantenimiento, self.software, MARZO), ambos)
        self.assertEqual(services.resolver_regla(self.salarios, self.software, MARZO), solo_proveedor)
        self.assertEqual(services.resolver_regla(self.mantenimiento, self.vigilancia, MARZO), por_cuenta)
        self.assertEqual(services.resolver_regla(self.mantenimiento, None, MARZO), por_cuenta)

    def test_vigencia_de_la_regla(self):
        self.regla(self.gerencia, cuenta=self.energia, hasta=date(2026, 2, 28))
        self.regla(self.tecnologia, cuenta=self.energia, desde=date(2026, 3, 1))
        self.assertEqual(services.resolver_regla(self.energia, None, date(2026, 2, 10)).centro_costo, self.gerencia)
        self.assertEqual(services.resolver_regla(self.energia, None, MARZO).centro_costo, self.tecnologia)

    def test_cuenta_exenta_no_recibe_regla(self):
        self.regla(self.gerencia, proveedor=self.vigilancia)
        self.assertIsNone(services.resolver_regla(self.bancos, self.vigilancia, MARZO))


class AsientosConReglaTests(BaseAsignacion):
    def test_regla_completa_el_centro_y_queda_trazada(self):
        regla = self.regla(self.gerencia, cuenta=self.energia)
        asiento = self.borrador(self.energia)
        linea = self.primera_linea(asiento)
        self.assertEqual(linea.centro_costo, self.gerencia)
        self.assertEqual(linea.regla_asignacion, regla)
        self.assertEqual(linea.asignacion, "REGLA")
        banco = asiento.lineas.get(numero_linea=2)
        self.assertIsNone(banco.centro_costo)
        self.assertIsNone(banco.asignacion)
        contabilidad.contabilizar_asiento(asiento, usuario=self.contador)

    def test_asignacion_directa_prevalece(self):
        self.regla(self.gerencia, cuenta=self.energia)
        linea = self.primera_linea(self.borrador(self.energia, centro=self.rrhh))
        self.assertEqual(linea.centro_costo, self.rrhh)
        self.assertIsNone(linea.regla_asignacion)
        self.assertEqual(linea.asignacion, "DIRECTA")

    def test_sin_centro_ni_regla(self):
        with self.assertRaises(ValidationError) as ctx:
            self.borrador(self.salarios)
        self.assertIn("no hay regla de asignación aplicable", str(ctx.exception))

    def test_proveedor_en_el_asiento(self):
        self.regla(self.tecnologia, cuenta=self.mantenimiento, proveedor=self.software)
        self.regla(self.gerencia, cuenta=self.mantenimiento)
        asiento = self.borrador(self.mantenimiento, proveedor=self.software)
        self.assertEqual(asiento.proveedor, self.software)
        self.assertEqual(self.primera_linea(asiento).centro_costo, self.tecnologia)
        # Al editar el borrador sin proveedor, la regla se vuelve a resolver.
        asiento = contabilidad.actualizar_asiento(
            asiento,
            usuario=self.contador,
            fecha=MARZO,
            concepto="Pago",
            lineas=[
                {"cuenta": self.mantenimiento, "debe": "100", "haber": 0},
                {"cuenta": self.bancos, "debe": 0, "haber": "100"},
            ],
        )
        self.assertIsNone(asiento.proveedor)
        self.assertEqual(self.primera_linea(asiento).centro_costo, self.gerencia)

    def test_proveedor_inactivo_rechazado(self):
        tesoreria.actualizar_proveedor(self.vigilancia, usuario=self.contador, datos={"activo": False})
        with self.assertRaises(ValidationError) as ctx:
            self.borrador(self.energia, centro=self.gerencia, proveedor=self.vigilancia)
        self.assertIn("proveedor", ctx.exception.message_dict)

    def test_reversion_copia_regla_y_proveedor(self):
        self.regla(self.gerencia, proveedor=self.vigilancia)
        asiento = contabilidad.contabilizar_asiento(
            self.borrador(self.energia, proveedor=self.vigilancia), usuario=self.contador
        )
        reversion = contabilidad.revertir_asiento(asiento, usuario=self.contador, motivo="Error", fecha=MARZO)
        self.assertEqual(reversion.proveedor, self.vigilancia)
        original, revertida = self.primera_linea(asiento), self.primera_linea(reversion)
        self.assertEqual(revertida.regla_asignacion, original.regla_asignacion)
        self.assertEqual(revertida.centro_costo, self.gerencia)

    def test_restriccion_de_bd_regla_con_centro(self):
        regla = self.regla(self.gerencia, cuenta=self.energia)
        linea = self.primera_linea(self.borrador(self.energia))
        from contabilidad.models import LineaAsiento

        with self.assertRaises(IntegrityError), transaction.atomic():
            LineaAsiento.objects.filter(pk=linea.pk).update(centro_costo=None, regla_asignacion=regla)


class ReglasApiTests(BaseAsignacion):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.auditor = crear_usuario("auditor", roles.AUDITOR)

    def test_permisos(self):
        self.client.force_authenticate(self.auditor)
        self.assertEqual(self.client.get("/api/reglas-asignacion/").status_code, 200)
        datos = {"cuenta": self.energia.pk, "centro_costo": self.gerencia.pk, "vigente_desde": "2026-01-01"}
        self.assertEqual(self.client.post("/api/reglas-asignacion/", datos, format="json").status_code, 403)

    def test_crud_y_resolver(self):
        self.client.force_authenticate(self.contador)
        datos = {"cuenta": self.energia.pk, "centro_costo": self.gerencia.pk, "vigente_desde": "2026-01-01"}
        resp = self.client.post("/api/reglas-asignacion/", datos, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(resp.data["centro_codigo"], "01-01")
        self.assertFalse(resp.data["aplicada"])
        self.assertEqual(self.client.post("/api/reglas-asignacion/", datos, format="json").status_code, 400)

        resp = self.client.get(
            "/api/reglas-asignacion/resolver/",
            {"fecha": "2026-03-15", "cuentas": f"{self.energia.pk},{self.salarios.pk}", "proveedor": ""},
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data[self.energia.pk]["centro_codigo"], "01-01")
        self.assertIsNone(resp.data[self.salarios.pk])

        resp = self.client.patch(f"/api/reglas-asignacion/{pk}/", {"centro_costo": self.rrhh.pk}, format="json")
        self.assertEqual(resp.status_code, 400)
        resp = self.client.patch(f"/api/reglas-asignacion/{pk}/", {"vigente_hasta": "2026-12-31"}, format="json")
        self.assertEqual(resp.data["vigente_hasta"], "2026-12-31")
        lista = self.client.get("/api/reglas-asignacion/", {"vigente_en": "2027-01-15"})
        self.assertEqual(lista.data["count"], 0)
        self.assertEqual(self.client.delete(f"/api/reglas-asignacion/{pk}/").status_code, 204)

    def test_asiento_por_api_con_proveedor_y_regla(self):
        self.regla(self.tecnologia, proveedor=self.software)
        self.client.force_authenticate(self.contador)
        resp = self.client.post(
            "/api/asientos/",
            {
                "fecha": "2026-03-15",
                "concepto": "Licencias",
                "proveedor": self.software.pk,
                "lineas": [
                    {"cuenta": self.mantenimiento.pk, "debe": "50", "haber": "0"},
                    {"cuenta": self.bancos.pk, "debe": "0", "haber": "50"},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["proveedor_nombre"], "Software, S.A.")
        self.assertEqual(resp.data["lineas"][0]["asignacion"], "REGLA")
        self.assertEqual(resp.data["lineas"][0]["centro_codigo"], "01-02")
        self.assertIsNone(resp.data["lineas"][1]["asignacion"])


class CargarAsignacionBaseTests(TestCase):
    def test_carga_idempotente(self):
        crear_usuario("contador", roles.CONTADOR)
        salida = {"stdout": StringIO(), "stderr": StringIO()}
        call_command("cargar_catalogo_base", usuario="contador", **salida)
        call_command("cargar_centros_base", usuario="contador", **salida)
        call_command("cargar_asignacion_base", usuario="contador", **salida)
        self.assertEqual(salida["stderr"].getvalue(), "")
        self.assertEqual(ReglaAsignacion.objects.count(), 7)
        call_command("cargar_asignacion_base", usuario="contador", **salida)
        self.assertEqual(ReglaAsignacion.objects.count(), 7)
