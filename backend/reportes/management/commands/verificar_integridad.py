import sys

from django.core.management.base import BaseCommand

from reportes import integridad

ICONO = {integridad.OK: "OK  ", integridad.ADVERTENCIA: "AVISO", integridad.FALLA: "FALLA"}


class Command(BaseCommand):
    help = (
        "Verifica las reglas contables sobre los datos reales (partida doble, centros, prorrateo, cuentas por "
        "pagar, presupuesto, reportes vs. balanza, triggers). Termina con código 1 si alguna falla."
    )

    def add_arguments(self, parser):
        parser.add_argument("--anio", type=int, help="Ejercicio para cuadrar reportes con la balanza (por defecto el actual).")

    def handle(self, *args, anio=None, **options):
        resultados = integridad.verificar(anio)
        for r in resultados:
            revisados = f" · {r['revisados']} revisado(s)" if r["revisados"] is not None else ""
            linea = f"[{ICONO[r['estado']]}] {r['descripcion']}{revisados}"
            estilo = {integridad.OK: self.style.SUCCESS, integridad.ADVERTENCIA: self.style.WARNING}.get(r["estado"], self.style.ERROR)
            self.stdout.write(estilo(linea))
            for d in r["detalle"]:
                self.stdout.write(f"        - {d}")
            if r["problemas"] > len(r["detalle"]):
                self.stdout.write(f"        … y {r['problemas'] - len(r['detalle'])} más")
        if integridad.hay_fallas(resultados):
            self.stdout.write(self.style.ERROR("Se encontraron fallas de integridad."))
            sys.exit(1)
        self.stdout.write(self.style.SUCCESS("Integridad verificada."))
