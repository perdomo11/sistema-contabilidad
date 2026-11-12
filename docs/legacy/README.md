# Configuración heredada (Oracle + docker compose)

Estos archivos corresponden al entorno original (Oracle XE 21c + `docker compose`) y ya no se usan
en el despliegue en Render + Neon (PostgreSQL). Se conservan como referencia:

| Archivo | Uso original |
|---|---|
| `docker-compose.yml` | Servicios `oracle-db`, `backend` (runserver) y `frontend` (Vite) |
| `backend.Dockerfile`, `frontend.Dockerfile` | Imágenes por servicio del compose |
| `docker/oracle-init/` | Privilegios del usuario de pruebas en Oracle |
| `scripts/` | Respaldos con Data Pump (`respaldo.sh`, `verificar_respaldo.sh`, `restaurar.sh`) |

Notas:
- El backend ya no incluye el driver `oracledb`; para volver a Oracle habría que reinstalarlo y
  restaurar `DATABASES` en `config/settings.py`.
- Los triggers de Oracle siguen en sus migraciones originales (solo se ejecutan con `vendor == "oracle"`);
  sus equivalentes en PostgreSQL están en las migraciones `*_triggers_postgresql.py`.
- En PostgreSQL (Neon), los respaldos se hacen con el historial/branching de Neon o con `pg_dump`.
