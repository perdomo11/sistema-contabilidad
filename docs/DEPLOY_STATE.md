# DEPLOY_STATE — memoria del despliegue (Render + Neon)

Especificación: `DEPLOY_SPEC.md` (raíz). Si la sesión se reinicia, continuar en el primer ítem pendiente.

## Checklist
- [x] B0 Diagnóstico — PUERTA 1 activada (triggers PL/SQL) → usuario eligió portarlos (B3.5).
- [!] B0.5 Exportación temprana — Oracle no accesible (contenedores apagados, sin `.env` local). B8 creará fixture demo.
- [x] B1 Higiene del repositorio (.gitignore, .dockerignore, renormalize; nada sensible versionado)
- [x] B2 Dependencias Python (+whitenoise, dj-database-url, psycopg[binary], python-dotenv; −oracledb; .venv Python 3.12)
- [x] B3 settings.py por variables de entorno (check OK; check --deploy solo W005/W021; migrate OK en SQLite)
- [x] B3.5 14 triggers portados a PL/pgSQL (`*_triggers_postgresql.py` en usuarios/contabilidad/presupuesto/tesoreria/ventas, solo vendor postgresql); `integridad.triggers()` revisa pg_trigger; suite completa en PostgreSQL 16 local: 341 pruebas OK
- [x] B4 urls.py y vistas: health = SELECT 1 → {status, db} / 503 sin detalle; vista SPA (`config/spa.py`) catch-all al final; API ya bajo `api/` (sin cambios de prefijo)
- [x] B5 Frontend: `API_BASE`/`urlApi` en `src/api.js` (VITE_API_URL || "/api"), JWT intacto; Vite `base` /static/ en build y proxy /api,/admin,/media; build OK; sin URLs absolutas en src
- [x] B6 Dockerfile multi-stage (node:22-alpine → python:3.12-slim, usuario no root), `backend/entrypoint.sh`, `render.yaml`; Oracle/compose → `docs/legacy/`
- [x] B7 Verificación SIN Docker (Docker Desktop desapareció del equipo durante la sesión): build OK; check --deploy OK (W005/W021); runserver --nostatic DEBUG=False sobre Postgres local: `/` 200 con #root, health 200, asset 200, ruta React 200, admin 200 + CSS 200; sin secretos ni localhost injustificados. `docker build` NO probado → se prueba en Render
- [x] B8 Neon ("OK NEON" del usuario): PG 18, base vacía → 66 migraciones; `cargar_fixture fixtures/demo.json` (269 objetos) con integridad [OK] y 14 triggers habilitados. Conteos por modelo idénticos a origen; debe = haber = 534,400.00 en ambos; trigger de inmutabilidad verificado
- [x] B9 DEPLOY.md (7 pasos) y README (Despliegue, diagrama, arranque en frío; desarrollo local sin compose)

## Hallazgos clave (B0)
- a) `backend/manage.py`; proyecto `backend/config` (settings/urls/wsgi/asgi). Apps: usuarios, contabilidad,
  centros_costo, presupuesto, tesoreria, reportes, ventas. Frontend `frontend/` (Vite 5, React 18.3,
  react-router-dom 6.28, package-lock presente). Django 5.2 (`>=5.2,<5.3`), Python 3.12 (imagen), Node 20 (imagen).
- b) BD Oracle XE 21c, driver `oracledb`; credenciales por env (`DB_HOST/PORT/NAME/USER/PASSWORD`) desde `.env` (docker compose).
- c) Oracle: 14 triggers PL/SQL creados en migraciones con `RunPython` + cursor crudo (contabilidad 0004/0006,
  presupuesto 0002/0004, tesoreria 0003/0006, usuarios 0003, ventas 0002). Todas con guarda
  `connection.vendor != "oracle"` → en Postgres se omiten (migran, pero sin reglas en BD).
  SQL crudo en runtime: `config/health.py` (v$version / DUAL), `reportes/integridad.py` (user_triggers, guardado por vendor).
  Pruebas con cursor crudo: `contabilidad/tests.py:590`, `usuarios/tests.py:127,135`. Sin `managed=False`, sin `*.sql`.
- d) API bajo `api/` (reportes en `api/reportes/`), health en `/api/health/`. DRF + SimpleJWT (Bearer). Sin corsheaders.
- e) Frontend: wrapper `fetch` en `frontend/src/api.js` con rutas relativas `/api/...`; sin URLs absolutas ni VITE_*.
- f) Sin FloatField. Sin FileField/MEDIA. Excel se genera en memoria (respuesta HTTP). Numeración de asientos/documentos
  en servicios (no secuencias Oracle explícitas).
- g) Versionado solo `.env.example`; historial limpio. `settings.py:21` SECRET_KEY por defecto de desarrollo ("cl***").
  `settings.py:134-136` datos de empresa ficticios por defecto (no secretos).
- h) Oracle no accesible ahora (servicios apagados, falta `.env`).
- TIME_ZONE ya definido (`America/El_Salvador`) → se conserva. USE_TZ = True.

## Decisiones
- PUERTA 1 (usuario): **portar los 14 triggers a PL/pgSQL** en migraciones nuevas solo para `postgresql`, con pruebas.
  Bloque extra B3.5 (después de B3, cuando DATABASE_URL funcione) y agregar los triggers PG a `integridad.py`.
- Neon (usuario): **el usuario pega la URL directa (sin pooler) en `.env.produccion`**; no se usa `neon init`.
- Variables renombradas: SECRET_KEY→DJANGO_SECRET_KEY, DEBUG→DJANGO_DEBUG, ALLOWED_HOSTS→DJANGO_ALLOWED_HOSTS; DB_* eliminadas.
  `.env` local en `backend/.env` (junto a manage.py).
- TIME_ZONE: se conserva `America/El_Salvador` (spec: solo si no hay otra definida).

- Carga de fixtures: `loaddata` directo falla con triggers (asiento contabilizado se inserta antes que sus líneas).
  Nuevo comando `cargar_fixture` (reportes): una transacción, `DISABLE TRIGGER USER` solo en las 11 tablas con triggers,
  loaddata, `ENABLE`, `integridad.verificar()`; si falla, rollback. `entrypoint.sh` lo usa con LOAD_DEMO_DATA=1.
- `select_for_update()` + `select_related` en FK anulables → `of=("self",)` (12 llamadas; Postgres no permite FOR UPDATE en outer join).
- Windows: `dumpdata -o` escribe en cp1252 → usar PYTHONUTF8=1.
- Pruebas locales en Postgres: `pgserver` (PG 16 embebido) + `tzdata` + `nodejs-wheel` solo en `.venv` (no en requirements).
- `docker-compose.yml`, Dockerfiles por servicio, `docker/oracle-init`, `scripts/` (Data Pump) → `docs/legacy/` (+README).

- Región: Neon ya existía en aws-us-east-1 → `render.yaml` region `virginia` (no oregon) para misma zona.
- `.env.produccion` con `&channel_binding=require`: no se puede hacer `source` en bash; DEPLOY.md usa `grep | cut`.

## Warnings justificados (check --deploy)
- W005 HSTS sin includeSubDomains: el dominio *.onrender.com no es nuestro; no se fuerza a subdominios.
- W021 HSTS sin preload: la spec pide explícitamente "sin preload".

## Secretos a rotar
- Ninguno detectado en git (actual ni historial).
