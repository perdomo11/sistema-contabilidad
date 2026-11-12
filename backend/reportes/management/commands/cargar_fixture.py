"""Carga un fixture (datos.json o fixtures/demo.json) respetando las reglas contables.

`loaddata` inserta cada asiento antes que sus líneas, así que los triggers de reglas (partida doble al
contabilizar, líneas inmutables, etc.) rechazarían un asiento ya contabilizado. Por eso, en PostgreSQL:

1. Todo ocurre en UNA transacción.
2. Se desactivan solo los triggers de usuario (`DISABLE TRIGGER USER`; las claves foráneas siguen activas)
   de las tablas que tienen triggers de reglas. Basta con ser dueño de las tablas (no requiere superusuario).
3. Se ejecuta `loaddata` y se reactivan los triggers.
4. Se ejecuta la verificación de integridad (partida doble, centros, prorrateo, cuentas por pagar, ventas,
   presupuesto, triggers habilitados). Si algo falla, se revierte toda la carga.

En otros motores (SQLite) solo se ejecuta loaddata + verificación.
"""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from reportes import integridad


def _tablas_con_triggers(cursor):
    cursor.execute(
        "select distinct c.relname from pg_trigger t join pg_class c on c.oid = t.tgrelid"
        " where not t.tgisinternal and upper(t.tgname) = any(%s)",
        [list(integridad.TRIGGERS)],
    )
    return sorted(fila[0] for fila in cursor.fetchall())


class Command(BaseCommand):
    help = "Carga un fixture en una transacción (en PostgreSQL con los triggers de reglas en pausa) y verifica la integridad."

    def add_arguments(self, parser):
        parser.add_argument("archivo", help="Ruta del fixture JSON (p. ej. datos.json o fixtures/demo.json).")
        parser.add_argument("--anio", type=int, help="Ejercicio para cuadrar reportes con la balanza.")

    def handle(self, *args, archivo, anio=None, **options):
        postgres = connection.vendor == "postgresql"
        with transaction.atomic():
            tablas = []
            if postgres:
                with connection.cursor() as cursor:
                    tablas = _tablas_con_triggers(cursor)
                    for tabla in tablas:
                        cursor.execute(f'ALTER TABLE "{tabla}" DISABLE TRIGGER USER')
                self.stdout.write(f"Triggers de reglas en pausa en {len(tablas)} tabla(s).")
            call_command("loaddata", archivo, verbosity=options.get("verbosity", 1))
            if postgres:
                with connection.cursor() as cursor:
                    for tabla in tablas:
                        cursor.execute(f'ALTER TABLE "{tabla}" ENABLE TRIGGER USER')
            resultados = integridad.verificar(anio)
            for r in resultados:
                self.stdout.write(f"[{r['estado']}] {r['descripcion']}")
                for d in r["detalle"]:
                    self.stdout.write(f"    - {d}")
            if integridad.hay_fallas(resultados):
                raise CommandError("La verificación de integridad falló; la carga se revirtió por completo.")
        self.stdout.write(self.style.SUCCESS("Fixture cargado y verificado."))
