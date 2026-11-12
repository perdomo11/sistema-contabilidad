# Sistema Contable: Centros de Costo, Presupuesto y Flujo de Efectivo

Sistema informático contable (caso de uso: banco) que asigna partidas a centros de costo,
distribuye el presupuesto institucional, genera estados de resultados segmentados y proyecta
el flujo de efectivo.

## Despliegue
- **URL:** https://sistema-contabilidad-d9u6.onrender.com/
- **Usuario de evaluación:** contador
- Guía paso a paso: [`DEPLOY.md`](DEPLOY.md)

```
  Navegador
     │  HTTPS
     ▼
┌──────────────────────────── Render (web service, Docker, plan free) ───────────────────────────┐
│  gunicorn ─► Django 5.2                                                                        │
│               ├─ /api/...      Django REST Framework + JWT                                     │
│               ├─ /admin/       Admin de Django                                                 │
│               ├─ /static/...   WhiteNoise: build de React (Vite) + estáticos del admin         │
│               └─ /* (resto)    index.html de React (React Router)                              │
└───────────────────────────────────────────────┬────────────────────────────────────────────────┘
                                                │ DATABASE_URL (TLS, conexión directa)
                                                ▼
                                   Neon PostgreSQL (aws-us-east-1)
                         tablas + 14 triggers de reglas contables (PL/pgSQL)
```

> **Arranque en frío:** en el plan gratuito, Render suspende el servicio tras ~15 minutos sin tráfico y
> Neon suspende el cómputo de la base. La primera petición después de una pausa puede tardar **30–60
> segundos**; las siguientes son normales.

## Desarrollo local
Requisitos: Python 3.12 y Node 22.
```bash
python -m venv .venv && . .venv/Scripts/activate       # Windows Git Bash (Linux/macOS: .venv/bin/activate)
pip install -r backend/requirements.txt
cp .env.example backend/.env                            # DJANGO_DEBUG=True; sin DATABASE_URL usa SQLite
cd backend && python manage.py migrate && python manage.py runserver
# en otra terminal
cd frontend && npm ci && npm run dev                    # http://localhost:5173 (proxy de /api a :8000)
```
Para trabajar sobre PostgreSQL define `DATABASE_URL` en `backend/.env` (nunca la de producción).

## Usuarios y roles
```bash
python manage.py createsuperuser        # administrador (/admin/)
python manage.py crear_usuarios_demo    # contador, tesorero, jefe, auditor (solo con DJANGO_DEBUG=True)
```
Roles: Contador, Tesorero, Jefe de área, Auditor. Se asignan en `/admin/`.

## Datos de ejemplo
```bash
python manage.py cargar_fixture fixtures/demo.json      # catálogo, centros, ejercicio 2026 y asientos de muestra
# o los datos base por partes:
python manage.py cargar_catalogo_base --usuario contador
python manage.py cargar_centros_base --usuario contador
python manage.py cargar_asignacion_base --usuario contador
python manage.py cargar_prorrateo_base --usuario contador --anio 2026
python manage.py cargar_flujo_base --usuario contador
```

## Pruebas e integridad
```bash
python manage.py test                   # usar DATABASE_URL de un PostgreSQL local: las pruebas de triggers lo requieren
python manage.py verificar_integridad   # reglas contables sobre los datos reales
```
Matriz de reglas y pruebas: [`docs/PRUEBAS.md`](docs/PRUEBAS.md).

## Manuales
- [Manual de usuario](docs/MANUAL_USUARIO.md)
- [Manual técnico](docs/MANUAL_TECNICO.md)

## Estructura
- `backend/`: Django 5.2 + Django REST Framework (proyecto `config`), `entrypoint.sh` del contenedor
- `frontend/`: React 18 + Vite + React-Bootstrap
- `Dockerfile`, `render.yaml`: imagen única y Blueprint de Render
- `docs/`: documento base, plan de tareas, especificación de cada tarea, manuales y pruebas
- `docs/legacy/`: configuración anterior (Oracle XE + docker compose, respaldos con Data Pump)
