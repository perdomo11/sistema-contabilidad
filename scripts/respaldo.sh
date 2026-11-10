#!/usr/bin/env bash
# Respaldo del esquema de la aplicación con Oracle Data Pump (T6.1).
# Uso: bash scripts/respaldo.sh
# Resultado: respaldos/AAAAMMDD_HHMMSS/ con el .dmp, el log de expdp e info.txt.
source "$(dirname "$0")/_comun.sh"

marca=$(date +%Y%m%d_%H%M%S)
nombre="contable_$marca"
destino="respaldos/$marca"
esquema=$(esquema_app)
dir=$(directorio_data_pump)

echo "Respaldando el esquema $esquema…"
data_pump expdp "schemas=$esquema
directory=DATA_PUMP_DIR
dumpfile=$nombre.dmp
logfile=$nombre.log
reuse_dumpfiles=yes" >/dev/null 2>&1 || true

mkdir -p "$destino"
docker compose cp "$SERVICIO_DB:$dir/$nombre.log" "$destino/" >/dev/null 2>&1
if ! grep -q "successfully completed" "$destino/$nombre.log"; then
  echo "ERROR: el respaldo no se completó. Log: $destino/$nombre.log" >&2
  exit 1
fi
docker compose cp "$SERVICIO_DB:$dir/$nombre.dmp" "$destino/" >/dev/null 2>&1
docker compose exec -T "$SERVICIO_DB" rm -f "$dir/$nombre.dmp" "$dir/$nombre.log"

{
  echo "Fecha: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "Esquema: $esquema"
  echo "Commit: $(git rev-parse --short HEAD 2>/dev/null || echo desconocido)"
  echo "Filas por tabla:"
  contar_filas "$esquema" | sed 's/^/  /'
} >"$destino/info.txt"

echo "Respaldo listo en $destino ($(du -h "$destino/$nombre.dmp" | cut -f1))."
