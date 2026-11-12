# DEPLOY_STATE — memoria del despliegue (Render + Neon)

Especificación: `DEPLOY_SPEC.md` (raíz). Si la sesión se reinicia, continuar en el primer ítem pendiente.

## Checklist
- [x] B0 Diagnóstico — **PUERTA 1 activada** (triggers PL/SQL). En espera de decisión del usuario.
- [!] B0.5 Exportación temprana — Oracle no accesible (contenedores apagados, sin `.env` local). B8 creará fixture demo.
- [ ] B1 Higiene del repositorio
- [ ] B2 Dependencias Python
- [ ] B3 settings.py por variables de entorno
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
- TIME_ZONE: se conserva `America/El_Salvador` (spec: solo si no hay otra definida).

## Secretos a rotar
- Ninguno detectado en git (actual ni historial).
