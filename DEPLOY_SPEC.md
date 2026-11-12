# DEPLOY_SPEC — Opción 4: Render (monolito Docker) + Neon Postgres

## Parámetros (editar si hace falta)
- SERVICIO_RENDER: sistema-contabilidad
- REGION_RENDER: oregon
- ZONA_HORARIA: America/Bogota
- RAMA: deploy

## Objetivo
Dejar el repositorio listo para desplegar con un Blueprint de Render: una sola imagen Docker
donde Django sirve la API, el admin y el build de React (WhiteNoise). BD Postgres en Neon vía
DATABASE_URL. Oracle y Cloudflare quedan fuera.
Éxito = B7 en verde + DEPLOY.md listo para que el usuario solo haga clics.

## Reglas
### Seguridad
- S1 Nunca muestres valores de secretos (SECRET_KEY, contraseñas, DATABASE_URL, tokens, correos).
  Reporta archivo:línea con el valor enmascarado ("ab***").
- S2 Los secretos solo van en archivos .env* ignorados por git. Lee DATABASE_URL de
  .env.produccion e inyéctala solo en el entorno del proceso. No la escribas en ningún otro sitio.
- S3 Pide confirmación explícita antes de: escribir en una BD remota, borrar funcionalidad,
  cambiar la versión mayor de Django o reescribir el historial de git.
- S4 Sin push. Trabaja en la rama RAMA con un commit por bloque ("deploy: Bx ...").

### Economía de tokens
- E1 No leas: node_modules, venv/.venv, dist, build, staticfiles, .git, lockfiles, *.min.*,
  binarios ni el contenido de migraciones (solo nombres, salvo que tengan RunSQL).
- E2 Descubre con `git ls-files` y `git grep -n` filtrados, limitando la salida a 60 líneas.
  Lee solo los archivos que vas a modificar o los rangos relevantes.
- E3 No reimprimas archivos ni diffs en el chat. Máximo 5 líneas de reporte por bloque.
- E4 Comandos silenciosos: `npm ci --no-audit --no-fund --loglevel=error`, `pip install -q`.
  Si fallan, muestra solo las últimas 30 líneas.
- E5 No leas otros documentos largos de docs/. Esta especificación es suficiente.

### Continuidad
- C1 docs/DEPLOY_STATE.md es tu memoria. Créalo en B0 con: checklist B0–B9, hallazgos clave
  (≤40 líneas), decisiones y "secretos a rotar". Actualízalo al cerrar cada bloque.
  Si la sesión se reinicia, lee primero DEPLOY_STATE.md y continúa en el primer ítem pendiente.
- C2 Solo marca [x] si se cumple la "Aceptación" del bloque. Si no puedes, marca [!] con el
  motivo y continúa con lo que no dependa de ese ítem.
- C3 Detecta el SO (PowerShell o bash) y usa comandos compatibles.

## B0 Diagnóstico (solo lectura, excepto DEPLOY_STATE.md)
Determina y anota:
a) Rutas: manage.py, paquete del proyecto (settings/urls/wsgi), apps, carpeta del frontend,
   package.json, Vite o CRA, React Router, versiones de Django, Python y Node.
b) BD y driver actuales, y de dónde salen las credenciales.
c) Dependencia de Oracle:
   `git grep -n -i -E "DUAL|ROWNUM|NVL\(|SYSDATE|TO_DATE|NEXTVAL|CONNECT BY|DECODE\(|MERGE INTO|VARCHAR2|callproc|cursor\.var|TRIGGER|PROCEDURE"`
   `git grep -n -E "\.raw\(|cursor\(\)|\.execute\(|\.extra\(|RunSQL|managed\s*=\s*False|connection\.vendor"`
   `git ls-files "*.sql"`
d) API: prefijo(s) de rutas, DRF, autenticación (sesión, JWT o token) y CORS.
e) Frontend: URLs absolutas (localhost, 127.0.0.1, http://), dónde se define la base de la
   API, variables VITE_/REACT_APP_ y referencias en JS a archivos de public/ con ruta absoluta.
f) Contabilidad: importes en FloatField (solo reportar), numeración consecutiva mediante
   secuencias o triggers, reportes con SQL crudo, PDF/Excel escritos a disco, FileField/MEDIA.
g) Seguridad: archivos sensibles versionados
   (`git ls-files | grep -i -E "\.env|wallet|\.pem|sqlite3|tnsnames|secret|credential"`),
   lo mismo en el historial (`git log --all --name-only --format=`), y valores hardcodeados
   en settings (solo archivo:línea).
h) Datos: ¿la BD local es accesible? Conteo de filas por modelo con un script de una sola
   ejecución que imprima solo números. Si no es accesible, anótalo; no es un bloqueo.

PUERTA: detente y pregúntame SOLO si ocurre alguna de estas condiciones:
1. La lógica depende de PL/SQL, triggers o procedimientos.
2. Hay modelos con managed=False.
3. Django < 4.2.
4. No encuentras manage.py o package.json.
5. Hay más de 10 consultas crudas específicas de Oracle.
En cualquier otro caso, continúa sin esperar.

## B0.5 Exportación temprana de datos (solo si la BD actual es Oracle u otra no-SQLite)
- Si B0 determinó que la BD actual es accesible y NO es SQLite, ejecuta AHORA, con la
  configuración y el driver actuales y sin modificar nada:
  `python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes
   -e auth.permission -e admin.logentry -e sessions --indent 2 -o datos.json`
- Verifica `git check-ignore datos.json` y anota en DEPLOY_STATE los conteos por modelo
  (y las sumas de debe/haber si existen) como referencia para B8.
- Si la BD no es accesible, márcalo [!] y continúa; B8 creará un fixture de demostración.
- En B8, si datos.json ya existe, NO vuelvas a exportar: úsalo.


## B1 Higiene del repositorio
- PRIMERO actualiza .gitignore (lista de abajo) y verifica con `git check-ignore` que
  .env.produccion, .env y datos*.json están ignorados. SOLO DESPUÉS, si hay cambios sin commit,
  haz el commit "wip: estado previo" y crea la rama RAMA. Nunca uses `git add -A` sin revisar
  antes `git status`.
- .gitignore: .env, .env.*, !.env.example, *.sqlite3, datos*.json, wallet/, node_modules,
  dist, build, staticfiles, __pycache__, .venv, venv.
- .dockerignore: lo mismo + .git, docs, *.md (excepto lo necesario).
- .gitattributes: `* text=auto` y `*.sh text eol=lf`. Después: `git add --renormalize .`
- Archivos sensibles versionados → `git rm --cached`, y anótalos en "secretos a rotar".

Aceptación: `git ls-files` no muestra archivos sensibles.

## B2 Dependencias Python
En el requirements.txt junto a manage.py (adapta si se usa otro gestor):
- Conserva lo que el proyecto usa.
- Añade gunicorn, whitenoise, dj-database-url, psycopg[binary] y python-dotenv.
- Elimina cx_Oracle y oracledb.
- Mantén la versión de Django si es ≥4.2. Si no está fijada, fija la mayor.menor instalada
  (por ejemplo, `Django>=5.1,<5.2`).
- Usa un .venv local (ignorado) para las pruebas.

Aceptación: la instalación en .venv funciona y `python manage.py check` pasa.

## B3 settings.py controlado por variables de entorno
- Carga `.env` junto a manage.py si existe (python-dotenv) y no falla si no existe.
- SECRET_KEY = DJANGO_SECRET_KEY. DEBUG = DJANGO_DEBUG (por defecto False).
  Con DEBUG=False y clave ausente o de desarrollo → ImproperlyConfigured.
- ALLOWED_HOSTS = DJANGO_ALLOWED_HOSTS (separados por comas) + RENDER_EXTERNAL_HOSTNAME
  si existe. En DEBUG, añade localhost y 127.0.0.1.
- CSRF_TRUSTED_ORIGINS = DJANGO_CSRF_TRUSTED_ORIGINS + https://RENDER_EXTERNAL_HOSTNAME.
- DATABASES:
  - Con DATABASE_URL → `dj_database_url.parse(url, conn_max_age=60,
    conn_health_checks=True, ssl_require=<False si el host es local>)`.
  - Sin DATABASE_URL → SQLite en BASE_DIR/db.sqlite3.
  - Elimina toda la configuración de Oracle.
- Estáticos:
  - STATIC_URL = "/static/" y STATIC_ROOT = BASE_DIR/"staticfiles".
  - FRONTEND_DIST = env FRONTEND_DIST (por defecto, la ruta relativa al build local del frontend).
  - STATICFILES_DIRS incluye FRONTEND_DIST solo si existe.
  - WhiteNoiseMiddleware justo después de SecurityMiddleware.
  - STORAGES: "default" estándar y "staticfiles" =
    whitenoise.storage.CompressedManifestStaticFilesStorage. WHITENOISE_MANIFEST_STRICT = False.
- Solo si DEBUG=False:
  - SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https").
  - SECURE_SSL_REDIRECT = env DJANGO_SECURE_SSL_REDIRECT (por defecto True).
  - SECURE_REDIRECT_EXEMPT = [r"^api/health/$"].
  - SESSION_COOKIE_SECURE y CSRF_COOKIE_SECURE = True.
  - SECURE_HSTS_SECONDS = 3600 (sin preload) y SECURE_CONTENT_TYPE_NOSNIFF = True.
- CORS (solo si corsheaders ya está instalado):
  - Orígenes desde DJANGO_CORS_ALLOWED_ORIGINS (vacío por defecto).
  - En DEBUG, añade http://localhost:5173 y http://localhost:3000.
  - Nunca CORS_ALLOW_ALL_ORIGINS.
- Zona horaria:
  - TIME_ZONE = ZONA_HORARIA si no hay otra definida.
  - USE_TZ: no lo cambies si hoy es False; solo repórtalo.
- LOGGING por consola, nivel INFO.
- Crea `.env.example` (sin valores reales) y un `.env` local con DJANGO_DEBUG=True.

Aceptación:
- `check` pasa con DEBUG=True.
- `check --deploy` con DJANGO_DEBUG=False y una clave de prueba no muestra errores.
- Los warnings restantes quedan justificados en DEPLOY_STATE.

## B4 urls.py y vistas
- GET /api/health/: ejecuta SELECT 1 y responde {"status":"ok","db":connection.vendor}.
  Si falla, responde 503. Sin autenticación.
- Si la API no cuelga de un prefijo único `api/`, muévela bajo `api/` con include y anota el
  cambio para B5. Si ya cuelga de `api/`, no la toques.
- Vista SPA: devuelve FRONTEND_DIST/index.html leído del disco como HttpResponse, no como
  plantilla de Django. Si el build no existe, devuelve un 404 con un mensaje claro.
  Regístrala al final con un re_path catch-all que excluya `^(api|admin|static|media)/`.
- Conserva el servicio de media en DEBUG si ya existía.

Aceptación: `check` pasa y las rutas existentes siguen resolviendo.

## B5 Frontend
- Un único cliente HTTP (instancia de axios o wrapper de fetch) con
  `baseURL = import.meta.env.VITE_API_URL || "/api"`. En CRA: REACT_APP_API_URL.
- Sustituye TODAS las URLs absolutas y ajusta las rutas si el prefijo cambió en B4.
- Autenticación:
  - JWT o token → conserva los interceptores actuales.
  - Sesión → `withCredentials`, cabecera X-CSRFToken desde la cookie csrftoken, y un endpoint
    GET /api/csrf/ con ensure_csrf_cookie que la app llama al arrancar.
- Vite:
  - `base: command === "build" ? "/static/" : "/"`.
  - `server.proxy` de /api, /admin y /media → http://127.0.0.1:8000.
- CRA: `"homepage": "/static/"` y `"proxy"` en package.json.
- Referencias en JS a archivos de public/ con ruta absoluta →
  `${import.meta.env.BASE_URL}archivo` (en CRA: `process.env.PUBLIC_URL`).

Aceptación:
- `npm run build` funciona.
- `git grep -n -E "localhost|127\.0\.0\.1|http://"` en src no devuelve resultados injustificados.

## B6 Contenedor y Render
Dockerfile en la raíz, multi-stage:
- Etapa frontend: node:22-alpine (o la versión que exija `engines`). `npm ci` (o `npm install`
  si no hay lockfile) y `npm run build`.
- Etapa final: python:3.12-slim (salvo incompatibilidad).
  - ENV PYTHONDONTWRITEBYTECODE=1 y PYTHONUNBUFFERED=1.
  - `pip install --no-cache-dir -r requirements.txt`.
  - Copia el backend y el build a /app/frontend_dist. ENV FRONTEND_DIST=/app/frontend_dist.
  - collectstatic --noinput en un RUN, con DJANGO_SECRET_KEY de build y DJANGO_DEBUG=False
    pasados solo en ese RUN (no como ENV).
  - `sed -i 's/\r$//'` y `chmod +x` sobre entrypoint.sh.
  - Usuario no root.

entrypoint.sh (finales de línea LF):
```sh
#!/bin/sh
set -e
python manage.py migrate --noinput
# si existe DJANGO_SUPERUSER_USERNAME: createsuperuser --noinput || true
# si LOAD_DEMO_DATA=1: loaddata fixtures/demo.json
exec gunicorn <proyecto>.wsgi:application --bind 0.0.0.0:${PORT:-10000} \
  --workers ${WEB_CONCURRENCY:-2} --timeout 60 --access-logfile -
```

render.yaml:
- type web, name SERVICIO_RENDER, runtime docker, plan free, region REGION_RENDER.
- dockerfilePath ./Dockerfile, dockerContext ., healthCheckPath /api/health/.
- envVars:
  - DJANGO_SECRET_KEY con `generateValue: true`.
  - DJANGO_DEBUG "False" y WEB_CONCURRENCY "2".
  - DATABASE_URL, DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL y
    DJANGO_SUPERUSER_PASSWORD con `sync: false`.

Mueve a docs/legacy/ la configuración de Oracle o Cloudflare que ya no aplique y anótalo.

## B7 Verificación local (reporta OK o FALLO por punto)
1. `npm run build`.
2. `check --deploy`.
3. Con Docker:
   - `docker build -t app .`
   - `docker run` con DJANGO_SECRET_KEY de prueba, DJANGO_DEBUG=False,
     DJANGO_SECURE_SSL_REDIRECT=False, DJANGO_ALLOWED_HOSTS=localhost y `-p 8000:10000`.
   - Comprueba con curl:
     - `/` → HTML con el div raíz de React.
     - `/api/health/` → 200.
     - Un asset en `/static/assets/...` → 200.
     - Una ruta interna de React → 200.
     - `/admin/login/` → 200 y su CSS → 200.
   - Detén y elimina el contenedor al terminar.
   Sin Docker: ejecuta collectstatic y luego `runserver --insecure` (o gunicorn) con
   DEBUG=False, y haz las mismas pruebas.
4. Busca secretos y referencias a localhost remanentes.

## B8 Datos (PEDIR CONFIRMACIÓN antes de tocar Neon)
- Si hay datos en la BD local accesible:
  - `dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission
    -e admin.logentry -e sessions --indent 2 -o datos.json`, en la raíz.
  - Verifica que el archivo está ignorado con `git check-ignore datos.json`.
- Si existe .env.produccion:
  - Muéstrame los comandos (migrate + loaddata) con la URL enmascarada y espera "OK NEON".
  - Después compara los conteos por modelo entre origen y Neon. Si existen modelos de
    asientos o movimientos, compara también las sumas de debe y haber.
- Si no existe .env.produccion: deja los comandos exactos (PowerShell y bash) en DEPLOY.md.
- Si no hay datos: crea fixtures/demo.json con un plan de cuentas básico y algunos asientos
  cuadrados, coherente con los modelos reales y sin datos personales. Comprueba que carga en
  SQLite.

## B9 Entregables
DEPLOY.md, solo con pasos fuera de VS Code. Cada paso con casilla [ ], tiempo estimado y
forma de verificarlo:
1. Neon: crear el proyecto en la región más cercana a REGION_RENDER, con conexión directa
   (sin pooler). Copiar la URL y quitar `&channel_binding=require` si da error.
2. Carga de datos: comandos exactos.
3. Merge de RAMA en main y push.
4. Render → New → Blueprint, rellenando los valores sync:false.
5. Verificación en producción: health, rutas internas, admin y CRUD.
6. UptimeRobot apuntando a /api/health/ cada 5 minutos.
7. "Si falla": CRLF en entrypoint, 400 por ALLOWED_HOSTS, 403 de CSRF, 404 de assets por la
   `base`, 500 por SECRET_KEY, errores SSL o channel_binding de Neon, OOM en el build y
   arranque en frío.

README.md, con una sección "Despliegue" que incluya:
- La URL como marcador de posición.
- El usuario de evaluación como marcador de posición, sin contraseña.
- Un diagrama ASCII de la arquitectura.
- Un aviso sobre el arranque en frío.

## Salida final en el chat (≤20 líneas)
Estado de B0–B9, ítems [!] con su motivo, secretos a rotar y los 3 próximos pasos del usuario.
