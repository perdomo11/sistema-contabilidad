"""Pruebas de T4.1: presupuesto institucional anual."""
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from usuarios import roles
from usuarios.models import Bitacora

from . import services
from .models import PresupuestoInstitucional, VersionPresupuesto

Estado, Tipo = PresupuestoInstitucional.Estado, VersionPresupuesto.Tipo


def crear_usuario(username, *nombres_roles):
    usuario = User.objects.create_user(username=username, password="Prueba_2026!")
    usuario.groups.set(Group.objects.filter(name__in=nombres_roles))
    return usuario


class BasePresupuesto(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)

    def crear(self, anio=2027, monto="1000000.00", **kwargs):
        return services.crear_presupuesto(usuario=self.contador, anio=anio, monto=monto, **kwargs)

    def aprobar(self, p, referencia="Acta JD 12/2026"):
        return services.aprobar_presupuesto(p, usuario=self.contador, referencia=referencia)

    def versiones(self, p):
        return list(p.versiones.order_by("numero").values_list("numero", "tipo", "monto"))


class PresupuestoInstitucionalTests(BasePresupuesto):
    def test_alta_crea_version_inicial(self):
        p = self.crear(descripcion="Lineamientos 2027")
        self.assertEqual((p.estado, p.version, p.monto), (Estado.BORRADOR, 1, Decimal("1000000.00")))
        self.assertEqual(self.versiones(p), [(1, Tipo.INICIAL, Decimal("1000000.00"))])
        self.assertIsNone(p.versiones.get().monto_anterior)

    def test_validaciones_de_alta(self):
        self.crear()
        with self.assertRaises(ValidationError) as e:
            self.crear()
        self.assertIn("anio", e.exception.message_dict)
        for monto in ("0", "-5", "10.123", "abc"):
            with self.subTest(monto=monto), self.assertRaises(ValidationError):
                self.crear(anio=2028, monto=monto)
        with self.assertRaises(ValidationError):
            self.crear(anio=1999)

    def test_ajuste_en_borrador(self):
        p = self.crear()
        p = services.cambiar_monto(p, usuario=self.contador, monto="1200000")
        self.assertEqual((p.version, p.monto, p.estado), (2, Decimal("1200000.00"), Estado.BORRADOR))
        v = p.versiones.get(numero=2)
        self.assertEqual((v.tipo, v.monto_anterior), (Tipo.AJUSTE, Decimal("1000000.00")))
        with self.assertRaises(ValidationError):
            services.cambiar_monto(p, usuario=self.contador, monto="1200000.00")  # igual al vigente

    def test_aprobacion_exige_referencia(self):
        p = self.crear()
        with self.assertRaises(ValidationError) as e:
            self.aprobar(p, referencia="  ")
        self.assertIn("referencia", e.exception.message_dict)
        p = self.aprobar(p)
        self.assertEqual((p.estado, p.version, p.referencia_aprobacion), (Estado.APROBADO, 2, "Acta JD 12/2026"))
        self.assertEqual(p.aprobado_por, self.contador)
        self.assertEqual(self.versiones(p)[-1], (2, Tipo.APROBACION, Decimal("1000000.00")))
        with self.assertRaises(ValidationError):
            self.aprobar(p)  # ya aprobado

    def test_modificacion_de_aprobado_exige_motivo_y_referencia(self):
        p = self.aprobar(self.crear())
        with self.assertRaises(ValidationError) as e:
            services.cambiar_monto(p, usuario=self.contador, monto="900000")
        self.assertEqual(set(e.exception.message_dict), {"motivo", "referencia"})
        p = services.cambiar_monto(
            p, usuario=self.contador, monto="900000", motivo="Recorte por menor captación", referencia="Acta JD 03/2027"
        )
        self.assertEqual((p.version, p.monto), (3, Decimal("900000.00")))
        v = p.versiones.get(numero=3)
        self.assertEqual((v.tipo, v.motivo, v.monto_anterior), (Tipo.MODIFICACION, "Recorte por menor captación", Decimal("1000000.00")))

    def test_cerrado_no_admite_cambios(self):
        p = self.crear()
        with self.assertRaises(ValidationError):
            services.cerrar_presupuesto(p, usuario=self.contador)  # borrador
        p = services.cerrar_presupuesto(self.aprobar(p), usuario=self.contador)
        self.assertEqual(p.estado, Estado.CERRADO)
        with self.assertRaises(ValidationError):
            services.cambiar_monto(p, usuario=self.contador, monto="5", motivo="x", referencia="y")
        with self.assertRaises(ValidationError):
            services.actualizar_descripcion(p, usuario=self.contador, descripcion="Otra")

    def test_bitacora(self):
        p = self.crear()
        p = services.cambiar_monto(p, usuario=self.contador, monto="1500000")
        p = self.aprobar(p)
        services.cerrar_presupuesto(p, usuario=self.contador)
        eventos = list(Bitacora.objects.filter(entidad="presupuesto").order_by("fecha", "id"))
        self.assertEqual(
            [e.accion for e in eventos],
            [Bitacora.Accion.CREAR, Bitacora.Accion.MODIFICAR, Bitacora.Accion.APROBAR, Bitacora.Accion.CERRAR],
        )
        self.assertEqual((eventos[1].valor_anterior["monto"], eventos[1].valor_nuevo["monto"]), ("1000000.00", "1500000.00"))


class PresupuestoBaseDeDatosTests(BasePresupuesto):
    """Reglas garantizadas en Oracle aunque se salte el servicio."""

    def test_monto_positivo_en_bd(self):
        p = self.crear()
        with self.assertRaises(IntegrityError), transaction.atomic():
            VersionPresupuesto.objects.create(
                presupuesto=p, numero=2, tipo=Tipo.AJUSTE, monto=0, monto_anterior=p.monto, registrado_por=self.contador
            )

    def test_aprobado_sin_referencia_en_bd(self):
        p = self.crear()
        with self.assertRaises(IntegrityError), transaction.atomic():
            PresupuestoInstitucional.objects.filter(pk=p.pk).update(estado=Estado.APROBADO)

    def test_monto_sin_version_en_bd(self):
        p = self.crear()
        with self.assertRaises(DatabaseError), transaction.atomic():
            PresupuestoInstitucional.objects.filter(pk=p.pk).update(monto=Decimal("5.00"))

    def test_versiones_inmutables_y_sin_eliminacion(self):
        p = self.crear()
        with self.assertRaises(DatabaseError), transaction.atomic():
            VersionPresupuesto.objects.filter(presupuesto=p).update(motivo="cambiado")
        with self.assertRaises(DatabaseError), transaction.atomic():
            PresupuestoInstitucional.objects.filter(pk=p.pk).delete()

    def test_cerrado_inmutable_en_bd(self):
        p = services.cerrar_presupuesto(self.aprobar(self.crear()), usuario=self.contador)
        with self.assertRaises(DatabaseError), transaction.atomic():
            PresupuestoInstitucional.objects.filter(pk=p.pk).update(descripcion="cambiada")


class PresupuestoApiTests(BasePresupuesto):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

    def test_flujo_completo_contador(self):
        self.client.force_authenticate(self.contador)
        resp = self.client.post("/api/presupuestos/", {"anio": 2027, "monto": "750000.00"}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        pk = resp.data["id"]
        self.assertEqual(len(resp.data["versiones"]), 1)
        resp = self.client.post(f"/api/presupuestos/{pk}/cambiar-monto/", {"monto": "800000.00"}, format="json")
        self.assertEqual((resp.status_code, resp.data["versiones"][-1]["variacion"]), (200, "50000.00"))
        resp = self.client.post(f"/api/presupuestos/{pk}/aprobar/", {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("referencia", resp.data)
        resp = self.client.post(f"/api/presupuestos/{pk}/aprobar/", {"referencia": "Acta 1"}, format="json")
        self.assertEqual((resp.status_code, resp.data["estado"]), (200, "APROBADO"))
        resp = self.client.patch(f"/api/presupuestos/{pk}/", {"descripcion": "Plan 2027"}, format="json")
        self.assertEqual((resp.status_code, resp.data["descripcion"]), (200, "Plan 2027"))
        resp = self.client.post(f"/api/presupuestos/{pk}/cerrar/", format="json")
        self.assertEqual((resp.status_code, resp.data["estado"]), (200, "CERRADO"))
        resp = self.client.post(f"/api/presupuestos/{pk}/cambiar-monto/", {"monto": "1", "motivo": "a", "referencia": "b"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual([p["anio"] for p in self.client.get("/api/presupuestos/").data], [2027])
        self.assertEqual(self.client.post("/api/presupuestos/", {"anio": 2027, "monto": "1"}, format="json").status_code, 400)

    def test_otros_roles_solo_consultan(self):
        p = self.crear()
        for rol in (roles.JEFE_AREA, roles.AUDITOR, roles.TESORERO):
            with self.subTest(rol=rol):
                self.client.force_authenticate(crear_usuario(f"u-{rol}", rol))
                self.assertEqual(self.client.get(f"/api/presupuestos/{p.pk}/").status_code, 200)
                self.assertEqual(self.client.post("/api/presupuestos/", {"anio": 2028, "monto": "1"}, format="json").status_code, 403)
                self.assertEqual(self.client.post(f"/api/presupuestos/{p.pk}/aprobar/", {"referencia": "x"}, format="json").status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/presupuestos/").status_code, 401)
