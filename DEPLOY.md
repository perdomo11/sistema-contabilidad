# Despliegue: Render (Docker) + Neon (PostgreSQL)

Guía paso a paso **fuera de VS Code**. El repositorio ya está preparado en la rama `deploy`:
`Dockerfile` (React + Django en una sola imagen), `render.yaml` (Blueprint) y `backend/entrypoint.sh`
(migraciones, superusuario y datos de demostración opcionales).

Tiempo total estimado: **45–60 minutos**.

---

## 1. Neon: base de datos  ·  ⏱ 5 min
- [ ] En https://console.neon.tech abre tu proyecto (o créalo) en la región **AWS US West 2 (Oregon)**,
      la más cercana a Render `oregon`. Si el proyecto está en otra región funciona igual, con más latencia.
- [ ] **Connect** → rama `main`, base `neondb`, rol dueño → desactiva **Connection pooling** (conexión
      directa: el host **no** debe contener `-pooler`) → copia la URL.
- [ ] Pégala en el archivo **`.env.produccion`** en la raíz del repositorio (ignorado por git), una sola línea:
      ```
      DATABASE_URL=postgresql://USUARIO:CLAVE@HOST/neondb?sslmode=require
      ```
- [ ] Si algún cliente da error con `channel_binding`, quita `&channel_binding=require` de la URL.

**Verificar:** `git check-ignore .env.produccion` imprime la ruta (está ignorado) y en Neon → *Tables*
la base aparece vacía.

---

## 2. Carga de datos en Neon  ·  ⏱ 5–10 min
Crea las tablas y los 14 triggers contables, y carga los datos: `fixtures/demo.json` (catálogo base,
18 centros, ejercicio 2026, 5 asientos cuadrados) o tu exportación `datos.json` si la tienes.
`cargar_fixture` carga en **una transacción**, pausa solo los triggers de reglas mientras inserta (los
asientos contabilizados se insertan antes que sus líneas), los reactiva y **revierte todo** si la
verificación de integridad falla.

Requisitos: Python 3.12 y `pip install -r backend/requirements.txt` (en un `.venv`).

**PowerShell** (la URL solo vive en el proceso de esta terminal):
```powershell
cd backend
Get-Content ..\.env.produccion | Where-Object { $_ -match '^\s*([A-Z_]+)=(.*)$' } | ForEach-Object { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') }
$env:PYTHONUTF8 = "1"
python manage.py migrate --noinput
python manage.py cargar_fixture fixtures/demo.json      # o: ..\datos.json
python manage.py verificar_integridad
Remove-Item Env:DATABASE_URL
```

**bash** (la URL solo vive dentro del subshell):
```bash
cd backend
( set -a; . ../.env.produccion; set +a; export PYTHONUTF8=1
  python manage.py migrate --noinput &&
  python manage.py cargar_fixture fixtures/demo.json &&  # o: ../datos.json
  python manage.py verificar_integridad )
```

Para exportar datos de otra base (por ejemplo, la Oracle local) a `datos.json`, con la configuración de esa base:
```bash
PYTHONUTF8=1 python manage.py dumpdata --natural-foreign --natural-primary -e contenttypes -e auth.permission \
  -e admin.logentry -e sessions --indent 2 -o ../datos.json   # en Windows, PYTHONUTF8=1 evita un JSON en cp1252
```

**Verificar:** la salida termina con `Fixture cargado y verificado.` y todas las líneas en `[OK]`,
incluida `Triggers de reglas en PostgreSQL (14 esperados, habilitados)`.

> Alternativa sin terminal: en Render define `LOAD_DEMO_DATA=1` y el contenedor carga
> `fixtures/demo.json` al arrancar, solo si la base no tiene asientos.

---

## 3. Merge de `deploy` en `main` y push  ·  ⏱ 5 min
```bash
git switch main
git merge --no-ff deploy
git push origin main
```
**Verificar:** en GitHub, `main` contiene `Dockerfile`, `render.yaml` y `DEPLOY.md`, y **no**
contiene `.env`, `.env.produccion`, `datos.json` ni `*.sqlite3`.

---

## 4. Render: Blueprint  ·  ⏱ 15–20 min (el primer build tarda)
- [ ] https://dashboard.render.com → **New** → **Blueprint** → conecta el repositorio → rama `main`.
- [ ] Render lee `render.yaml` (servicio web `sistema-contabilidad`, Docker, plan free, región oregon) y pide
      los valores marcados `sync: false`:
      | Variable | Valor |
      |---|---|
      | `DATABASE_URL` | la misma URL de `.env.produccion` |
      | `DJANGO_SUPERUSER_USERNAME` | usuario administrador de evaluación |
      | `DJANGO_SUPERUSER_EMAIL` | un correo de contacto |
      | `DJANGO_SUPERUSER_PASSWORD` | contraseña fuerte (no la reutilices) |
      `DJANGO_SECRET_KEY` se genera sola; `DJANGO_DEBUG=False` y `WEB_CONCURRENCY=2` ya vienen definidos.
- [ ] **Apply**. Sigue el log: `npm run build` → `collectstatic` → `migrate` → `gunicorn`.

**Verificar:** el servicio queda **Live** y el health check (`/api/health/`) en verde.

---

## 5. Verificación en producción  ·  ⏱ 5 min
Sustituye `https://TU-SERVICIO.onrender.com` por la URL de Render.
- [ ] `https://TU-SERVICIO.onrender.com/api/health/` → `{"status":"ok","db":"postgresql"}`
- [ ] `https://TU-SERVICIO.onrender.com/` → pantalla de inicio de sesión.
- [ ] Recarga directamente una ruta interna (p. ej. `/asientos`) → carga la app, sin 404.
- [ ] `/admin/` → login del admin **con estilos**; entra con el superusuario. Crea ahí los usuarios por rol
      (Contador, Tesorero, Jefe de área, Auditor) si los necesitas.
- [ ] **CRUD:** inicia sesión en la app, crea un asiento en borrador, contabilízalo, consulta el libro diario
      y la balanza; intenta editar el asiento contabilizado (debe impedirlo) y corrígelo con un asiento de reversión.

---

## 6. Monitoreo con UptimeRobot  ·  ⏱ 5 min
- [ ] https://uptimerobot.com → **Add New Monitor** → tipo **HTTP(s)** →
      URL `https://TU-SERVICIO.onrender.com/api/health/` → intervalo **5 minutos**.

**Verificar:** el monitor queda en **Up**. Además evita que el plan free se duerma en horario de uso
(Render free suspende tras ~15 min sin tráfico; el límite mensual de horas del plan sigue aplicando).

---

## 7. Si falla
| Síntoma | Causa probable | Solución |
|---|---|---|
| `exec ./entrypoint.sh: no such file or directory` | Finales de línea CRLF | El Dockerfile ya ejecuta `sed -i 's/\r$//'`; confirma que `.gitattributes` tiene `*.sh text eol=lf` y haz `git add --renormalize .` |
| **400 Bad Request** | Host fuera de `ALLOWED_HOSTS` | Render añade `RENDER_EXTERNAL_HOSTNAME` solo; para un dominio propio agrega `DJANGO_ALLOWED_HOSTS=midominio.com` |
| **403 CSRF** en `/admin/` | Origen no confiable | Define `DJANGO_CSRF_TRUSTED_ORIGINS=https://midominio.com` (el de Render ya se incluye) |
| **404** en `/static/assets/...` o pantalla en blanco | `base` de Vite o build ausente | `vite.config.js` usa `base: "/static/"` al compilar; revisa en el log que `npm run build` y `collectstatic` terminaron |
| **500** al arrancar / `ImproperlyConfigured` | Falta `DJANGO_SECRET_KEY` con `DEBUG=False` | Verifica que la variable existe (Blueprint con `generateValue: true`) |
| `SSL connection required` / `channel binding` | URL de Neon | Usa `?sslmode=require`; quita `&channel_binding=require` si el cliente no lo soporta |
| `connection refused` / timeouts esporádicos | URL con `-pooler` o Neon suspendido | Usa la conexión directa; el primer acceso tras inactividad tarda unos segundos (Neon se reactiva solo) |
| Build **OOM** (killed) | Memoria del builder | Reintenta el deploy; si persiste, sube temporalmente de plan para el build |
| Primera respuesta tarda **30–60 s** | Arranque en frío del plan free (Render y Neon) | Normal; UptimeRobot (paso 6) lo reduce |
| `Partida doble...` o `inmutable` al cargar datos | Se usó `loaddata` directo | Usa `python manage.py cargar_fixture <archivo>` (paso 2) |
