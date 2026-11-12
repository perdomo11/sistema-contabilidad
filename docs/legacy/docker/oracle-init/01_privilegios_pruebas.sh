#!/bin/bash
# Se ejecuta una sola vez, al crear el volumen de Oracle (después de crear APP_USER).
# Otorga al usuario de la aplicación los privilegios que Django necesita para crear
# y destruir la base de pruebas (usuario y tablespace test_*) al correr `manage.py test`.
sqlplus -s / as sysdba <<EOF
ALTER SESSION SET CONTAINER = XEPDB1;
GRANT CREATE USER, ALTER USER, DROP USER TO ${APP_USER};
GRANT CREATE TABLESPACE, DROP TABLESPACE TO ${APP_USER};
GRANT CREATE SESSION, CREATE TABLE, CREATE SEQUENCE, CREATE PROCEDURE,
      CREATE TRIGGER, CREATE VIEW TO ${APP_USER} WITH ADMIN OPTION;
EXIT;
EOF
