#!/usr/bin/env bash
# Funciones comunes de los scripts de respaldo (T6.1). Se cargan con `source`.
# Las credenciales NO pasan por la línea de comandos del host: se usan las variables
# ORACLE_PASSWORD y APP_USER que ya tiene el contenedor oracle-db (definidas desde .env).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
export MSYS_NO_PATHCONV=1 # Git Bash en Windows: no convertir rutas del contenedor

SERVICIO_DB=oracle-db

# Ejecuta SQL*Plus como SYSTEM en XEPDB1 con el texto recibido por la entrada estándar.
sql_system() {
  docker compose exec -T "$SERVICIO_DB" bash -c 'sqlplus -s -L "system/${ORACLE_PASSWORD}@localhost/XEPDB1"'
}

# Ejecuta expdp o impdp con un archivo de parámetros temporal dentro del contenedor.
# Uso: data_pump expdp|impdp "<parámetros, uno por línea>"
data_pump() {
  local herramienta=$1 parametros=$2
  printf '%s\n' "$parametros" | docker compose exec -T "$SERVICIO_DB" bash -c "
    set -e
    parfile=\$(mktemp)
    trap 'rm -f \"\$parfile\"' EXIT
    printf 'userid=\"system/%s@localhost/XEPDB1\"\n' \"\$ORACLE_PASSWORD\" > \"\$parfile\"
    cat >> \"\$parfile\"
    $herramienta parfile=\"\$parfile\"
  "
}

esquema_app() {
  # </dev/null: `docker compose exec` consumiría la entrada estándar (p. ej. la confirmación de restaurar.sh).
  docker compose exec -T "$SERVICIO_DB" bash -c 'echo "${APP_USER^^}"' </dev/null | tr -d '\r'
}

directorio_data_pump() {
  printf "set heading off feedback off pagesize 0\nselect directory_path from dba_directories where directory_name = 'DATA_PUMP_DIR';\nexit\n" |
    sql_system | tr -d '\r' | sed '/^[[:space:]]*$/d' | head -1 | xargs
}

# Cuenta las filas de cada tabla de un esquema: líneas "TABLA FILAS", ordenadas.
contar_filas() {
  local esquema=$1
  sql_system <<SQL | tr -d '\r' | sed '/^[[:space:]]*$/d' | sort
set heading off feedback off pagesize 0 linesize 200 serveroutput on
declare
  n number;
begin
  for t in (select table_name from dba_tables where owner = '$esquema' and nested = 'NO' order by table_name) loop
    execute immediate 'select count(*) from "$esquema"."' || t.table_name || '"' into n;
    dbms_output.put_line(t.table_name || ' ' || n);
  end loop;
end;
/
exit
SQL
}

# Termina las sesiones abiertas de un usuario (para poder borrarlo).
cerrar_sesiones() {
  local esquema=$1
  sql_system <<SQL >/dev/null
set feedback off
begin
  for s in (select sid, serial# as serie from v\$session where username = '$esquema') loop
    execute immediate 'alter system kill session ''' || s.sid || ',' || s.serie || ''' immediate';
  end loop;
end;
/
exit
SQL
}

borrar_esquema() {
  local esquema=$1
  cerrar_sesiones "$esquema"
  sql_system <<SQL
set feedback off
whenever sqlerror exit 1
declare
  n number;
begin
  select count(*) into n from dba_users where username = '$esquema';
  if n > 0 then
    execute immediate 'drop user "$esquema" cascade';
  end if;
end;
/
exit
SQL
}

# Copia el .dmp de una carpeta de respaldo al directorio de Data Pump; imprime su nombre.
subir_respaldo() {
  local carpeta=$1 dir=$2 dmp
  dmp=$(ls "$carpeta"/*.dmp 2>/dev/null | head -1 || true)
  if [[ -z "$dmp" ]]; then
    echo "No hay archivo .dmp en $carpeta" >&2
    return 1
  fi
  docker compose cp "$dmp" "$SERVICIO_DB:$dir/" >/dev/null 2>&1
  docker compose exec -T -u root "$SERVICIO_DB" chown oracle "$dir/$(basename "$dmp")" </dev/null >/dev/null 2>&1 || true
  basename "$dmp"
}
