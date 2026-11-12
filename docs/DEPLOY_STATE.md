# DEPLOY_STATE — memoria del despliegue (Render + Neon)

Especificación: `DEPLOY_SPEC.md` (raíz). Si la sesión se reinicia, continuar en el primer ítem pendiente.

## Checklist
- [x] B0 Diagnóstico — PUERTA 1 activada (triggers PL/SQL) → usuario eligió portarlos (B3.5).
- [!] B0.5 Exportación temprana — Oracle no accesible (contenedores apagados, sin `.env` local). B8 creará fixture demo.
- [x] B1 Higiene del repositorio (.gitignore, .dockerignore, renormalize; nada sensible versionado)
- [x] B2 Dependencias Python (+whitenoise, dj-database-url, psycopg[binary], python-dotenv; −oracledb; .venv Python 3.12)
- [x] B3 settings.py por variables de entorno (check OK; check --deploy solo W005/W021; migrate OK en SQLite)
- [ ] B3.5 Triggers en PL/pgSQL (migraciones solo postgresql + pruebas + integridad)
- [ ] B4 urls.py y vistas (health, SPA)
- [ ] B5 Frontend
- [ ] B6 Contenedor y Render
- [ ] B7 Verificación local
- [ ] B8 Datos (confirmación antes de tocar Neon)
- [ ] B9 Entregables (DEPLOY.md, README)

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

## Warnings justificados (check --deploy)
- W005 HSTS sin includeSubDomains: el dominio *.onrender.com no es nuestro; no se fuerza a subdominios.
- W021 HSTS sin preload: la spec pide explícitamente "sin preload".

## Secretos a rotar
- Ninguno detectado en git (actual ni historial).
