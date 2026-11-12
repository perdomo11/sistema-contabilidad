#!/usr/bin/env bash
# Restaura el esquema de la aplicación desde un respaldo de Data Pump (T6.1).
# REEMPLAZA TODOS LOS DATOS ACTUALES por los del respaldo. Pide confirmación.
# Uso: bash scripts/restaurar.sh respaldos/AAAAMMDD_HHMMSS
# Ensayo sin tocar la aplicación: ESQUEMA_DESTINO=CONTABLE_ENSAYO bash scripts/restaurar.sh <carpeta>
source "$(dirname "$0")/_comun.sh"

carpeta=${1:?Indique la carpeta del respaldo, p. ej. respaldos/20261110_120000}
origen=$(esquema_app)
destino=${ESQUEMA_DESTINO:-$origen}
destino=${destino^^}
dir=$(directorio_data_pump)

echo "Se BORRARÁ el esquema $destino y se reemplazará por el respaldo de $carpeta."
read -r -p "Para confirmar, escriba el nombre del esquema ($destino): " respuesta
if [[ "${respuesta^^}" != "$destino" ]]; then
  echo "Cancelado."
  exit 1
fi

archivo=$(subir_respaldo "$carpeta" "$dir")
trap 'docker compose exec -T "$SERVICIO_DB" rm -f "$dir/$archivo" >/dev/null 2>&1 || true' EXIT

if [[ "$destino" == "$origen" ]]; then
  echo "Deteniendo el backend…"
  docker compose stop backend >/dev/null
fi
echo "Borrando el esquema $destino…"
borrar_esquema "$destino" >/dev/null
echo "Importando…"
remap=""
if [[ "$destino" != "$origen" ]]; then
  remap="remap_schema=$origen:$destino"
fi
data_pump impdp "schemas=$origen
$remap
directory=DATA_PUMP_DIR
dumpfile=$archivo
logfile=restauracion.log" >/dev/null 2>&1 || true
docker compose cp "$SERVICIO_DB:$dir/restauracion.log" "$carpeta/restauracion.log" >/dev/null 2>&1
docker compose exec -T "$SERVICIO_DB" rm -f "$dir/restauracion.log"

if [[ "$destino" == "$origen" ]]; then
  echo "Levantando el backend…"
  docker compose start backend >/dev/null
fi
if grep -q "completed" "$carpeta/restauracion.log"; then
  echo "Restauración terminada. Log: $carpeta/restauracion.log"
  echo "Recomendado: docker compose exec backend python manage.py verificar_integridad"
else
  echo "ERROR: la restauración falló. Log: $carpeta/restauracion.log" >&2
  exit 1
fi
