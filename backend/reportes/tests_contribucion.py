"""Pruebas de T3.2: clasificación de cuentas y enfoque de contribución (Tabla 1)."""
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from contabilidad import services as contabilidad
from contabilidad.models import Cuenta
from usuarios import roles

from . import services
from .tests import DESDE, HASTA, BaseReportes, crear_usuario

V, F = Cuenta.Comportamiento.VARIABLE, Cuenta.Comportamiento.FIJO


class ClasificacionCuentasTests(BaseReportes):
    def test_herencia_y_valores_por_defecto(self):
        clasif = contabilidad.clasificacion_resultados()
        self.assertEqual(clasif[self.energia.pk], {"rubro_resultado": "GASTO_OPERACION", "comportamiento_costo": "FIJO", "controlable": True})
        self.assertEqual(clasif[self.intereses.pk]["rubro_resultado"], "INGRESO_OPERACION")
        self.assertIsNone(clasif[self.bancos.pk]["rubro_resultado"])
        contabilidad.actualizar_cuenta(self.g52, usuario=self.contador, datos={"comportamiento_costo": V})
        contabilidad.actualizar_cuenta(self.agua, usuario=self.contador, datos={"comportamiento_costo": F, "controlable": False})
        clasif = contabilidad.clasificacion_resultados()
        self.assertEqual(clasif[self.energia.pk]["comportamiento_costo"], "VARIABLE")  # heredado de 52
        self.assertEqual((clasif[self.agua.pk]["comportamiento_costo"], clasif[self.agua.pk]["controlable"]), ("FIJO", False))
        # Vacío vuelve a heredar.
        contabilidad.actualizar_cuenta(self.agua, usuario=self.contador, datos={"comportamiento_costo": "", "controlable": None})
        self.assertEqual(contabilidad.clasificacion_resultados()[self.agua.pk]["comportamiento_costo"], "VARIABLE")

    def test_arbol_incluye_clasificacion(self):
        contabilidad.actualizar_cuenta(self.g52, usuario=self.contador, datos={"controlable": False})
        nodos = {}

        def recorrer(lista):
            for n in lista:
                nodos[n["codigo"]] = n
                recorrer(n["hijos"])

        recorrer(contabilidad.arbol_cuentas())
        self.assertIsNone(nodos["5201"]["controlable"])
        self.assertFalse(nodos["5201"]["clasificacion_heredada"]["controlable"])
        self.assertFalse(nodos["5201"]["clasificacion_efectiva"]["controlable"])

    def test_validaciones(self):
        with self.assertRaises(ValidationError):
            contabilidad.actualizar_cuenta(self.energia, usuario=self.contador, datos={"rubro_resultado": "INGRESO_OPERACION"})
        with self.assertRaises(ValidationError):
            contabilidad.actualizar_cuenta(self.intereses, usuario=self.contador, datos={"comportamiento_costo": V})
        with self.assertRaises(ValidationError):
            contabilidad.actualizar_cuenta(self.bancos, usuario=self.contador, datos={"controlable": True})
        with self.assertRaises(IntegrityError), transaction.atomic():
            Cuenta.objects.filter(pk=self.bancos.pk).update(rubro_resultado="GASTO_OPERACION")

    def test_api_y_bitacora(self):
        client = APIClient()
        client.force_authenticate(self.contador)
        resp = client.patch(f"/api/cuentas/{self.agua.pk}/", {"comportamiento_costo": "VARIABLE", "controlable": False}, format="json")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual((resp.data["comportamiento_costo"], resp.data["controlable"]), ("VARIABLE", False))
        from usuarios.models import Bitacora

        evento = Bitacora.objects.filter(entidad="cuenta", accion=Bitacora.Accion.MODIFICAR).latest("fecha")
        self.assertEqual(evento.valor_nuevo["comportamiento_costo"], "VARIABLE")

class EnfoqueContribucionTests(BaseReportes):
    def setUp(self):
        super().setUp()
        # Energía variable; agua fija controlable (por defecto); alquiler fijo no controlable.
        contabilidad.actualizar_cuenta(self.energia, usuario=self.contador, datos={"comportamiento_costo": V})
        self.alquiler = contabilidad.crear_cuenta(
            usuario=self.contador, codigo="5203", nombre="Alquiler", padre=self.g52, controlable=False
        )
        self.gasto(self.alquiler, self.negocios, "200")

    def reporte(self, **kwargs):
        return services.enfoque_contribucion(desde=DESDE, hasta=HASTA, **kwargs)

    def test_estructura_de_la_tabla_1(self):
        r = self.reporte(nivel_cuentas=3)
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01", "02", "90"])
        self.assertEqual(r["ingresos"]["valores"], ["1000.00", "500.00", "0.00"])
        self.assertEqual(r["variables"]["valores"], ["300.00", "0.00", "0.00"])
        self.assertEqual(r["margen_contribucion"]["valores"], ["700.00", "500.00", "0.00"])
        self.assertEqual(r["margen_contribucion"]["razon"], ["70.00", "100.00", None, "80.00"])
        self.assertEqual(r["fijos_controlables"]["valores"], ["0.00", "100.00", "0.00"])
        self.assertEqual(r["margen_controlable"]["valores"], ["700.00", "400.00", "0.00"])
        self.assertEqual(r["no_controlables"]["valores"], ["200.00", "0.00", "0.00"])
        self.assertEqual([f["cuenta"]["codigo"] for f in r["no_controlables"]["filas"]], ["5203"])
        self.assertEqual(r["resultado_segmento"]["valores"], ["500.00", "400.00", "0.00"])
        self.assertEqual((r["costos_comunes"], r["resultado"]), ("0.00", "900.00"))

    def test_mismo_resultado_que_el_absorbente(self):
        self.prorratear()
        contribucion = self.reporte()
        absorbente = services.estado_resultados(desde=DESDE, hasta=HASTA)
        self.assertEqual(contribucion["resultado_segmento"]["valores"], absorbente["resultado"]["valores"])
        self.assertEqual(contribucion["resultado"], absorbente["resultado"]["total"])

    def test_prorrateo_es_no_controlable(self):
        self.prorratear()
        r = self.reporte(centro=self.matriz)
        self.assertEqual([c["codigo"] for c in r["columnas"]], ["01-01", "01-02"])
        # Gerencia: su energía es variable directa y lo distribuido resta en no controlables; queda en cero.
        self.assertEqual(r["variables"]["valores"], ["300.00", "0.00"])
        self.assertEqual(r["no_controlables"]["valores"], ["-300.00", "275.00"])
        self.assertEqual(r["resultado_segmento"]["valores"], ["0.00", "725.00"])
        prorrateadas = [f for f in r["no_controlables"]["filas"] if f["prorrateo"]]
        self.assertEqual(len(prorrateadas), 1)
        # Lo prorrateado nunca afecta el margen controlable del responsable.
        self.assertEqual(r["margen_controlable"]["valores"], ["-300.00", "1000.00"])

    def test_api(self):
        client = APIClient()
        client.force_authenticate(crear_usuario("jefe", roles.JEFE_AREA))
        resp = client.get("/api/reportes/enfoque-contribucion/", {"desde": "2026-01-01", "hasta": "2026-12-31"})
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["resultado"], "900.00")


class CatalogoBaseClasificadoTests(TestCase):
    def setUp(self):
        self.contador = crear_usuario("contador", roles.CONTADOR)

    def test_catalogo_base_clasificado(self):
        call_command("cargar_catalogo_base", usuario="contador", stdout=StringIO(), stderr=StringIO())
        clasif = contabilidad.clasificacion_resultados()
        por_codigo = {c.codigo: clasif[c.pk] for c in Cuenta.objects.filter(codigo__in=["5101", "520201", "520204", "4301"])}
        self.assertEqual(por_codigo["5101"]["rubro_resultado"], "COSTO_INTERMEDIACION")
        self.assertEqual(por_codigo["5101"]["comportamiento_costo"], "VARIABLE")
        self.assertTrue(por_codigo["520201"]["controlable"])
        self.assertFalse(por_codigo["520204"]["controlable"])
        self.assertEqual(por_codigo["4301"]["rubro_resultado"], "INGRESO_NO_OPERACION")
