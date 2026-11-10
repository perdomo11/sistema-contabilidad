#!/usr/bin/env bash
# Verifica un respaldo importándolo en un esquema temporal y comparando las filas por tabla con
# el esquema actual. No modifica los datos de la aplicación (T6.1).
# Uso: bash scripts/verificar_respaldo.sh respaldos/AAAAMMDD_HHMMSS
source "$(dirname "$0")/_comun.sh"

carpeta=${1:?Indique la carpeta del respaldo, p. ej. respaldos/20261110_120000}
esquema=$(esquema_app)
temporal="${esquema}_VERIF"
dir=$(directorio_data_pump)

archivo=$(subir_respaldo "$carpeta" "$dir")
limpiar() {
  borrar_esquema "$temporal" >/dev/null 2>&1 || true
  docker compose exec -T "$SERVICIO_DB" rm -f "$dir/$archivo" "$dir/verificacion.log" >/dev/null 2>&1 || true
}
trap limpiar EXIT

echo "Importando $archivo en el esquema temporal $temporal…"
borrar_esquema "$temporal" >/dev/null
data_pump impdp "schemas=$esquema
remap_schema=$esquema:$temporal
directory=DATA_PUMP_DIR
dumpfile=$archivo
logfile=verificacion.log" >/dev/null 2>&1 || true
docker compose cp "$SERVICIO_DB:$dir/verificacion.log" "$carpeta/verificacion.log" >/dev/null 2>&1
if ! grep -q "completed" "$carpeta/verificacion.log"; then
  echo "ERROR: la importación de prueba falló. Log: $carpeta/verificacion.log" >&2
  exit 1
fi

echo "Comparando filas por tabla (respaldo vs. base actual)…"
contar_filas "$temporal" >"$carpeta/.filas_respaldo"
contar_filas "$esquema" >"$carpeta/.filas_actual"
tablas=$(wc -l <"$carpeta/.filas_respaldo")
errores=$(grep -c "ORA-" "$carpeta/verificacion.log" || true)
echo "Tablas en el respaldo: $tablas · errores ORA- en la importación: $errores"
if diff "$carpeta/.filas_respaldo" "$carpeta/.filas_actual" >"$carpeta/diferencias.txt"; then
  echo "OK: el respaldo tiene las mismas filas por tabla que la base actual."
  rm -f "$carpeta/diferencias.txt"
else
  echo "Diferencias (< respaldo, > base actual; normales si hubo movimientos después del respaldo):"
  cat "$carpeta/diferencias.txt"
fi
rm -f "$carpeta/.filas_respaldo" "$carpeta/.filas_actual"
echo "Se elimina el esquema temporal $temporal."
