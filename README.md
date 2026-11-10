# Sistema Contable: Centros de Costo, Presupuesto y Flujo de Efectivo

Sistema informático contable (caso de uso: banco) que asigna partidas a centros de costo,
distribuye el presupuesto institucional, genera estados de resultados segmentados y proyecta
el flujo de efectivo.

## Requisitos
- Docker y Docker Compose

## Puesta en marcha
```bash
cp .env.example .env
docker compose up --build
```
La primera vez Oracle XE tarda de 2 a 4 minutos en quedar *healthy*; el backend espera a que lo esté.

| Servicio | URL                               |
|----------|-----------------------------------|
| Frontend | http://localhost:5173             |
| Backend  | http://localhost:8000/api/health/ |
| Oracle   | localhost:1521, servicio `XEPDB1` |

## Usuarios y roles
```bash
docker compose exec backend python manage.py createsuperuser       # administrador (/admin/)
docker compose exec backend python manage.py crear_usuarios_demo   # contador, tesorero, jefe, auditor
```
Roles: Contador, Tesorero, Jefe de área, Auditor. Se asignan en http://localhost:8000/admin/.

## Datos de ejemplo
```bash
docker compose exec backend python manage.py cargar_catalogo_base --usuario contador
docker compose exec backend python manage.py cargar_centros_base --usuario contador
docker compose exec backend python manage.py cargar_asignacion_base --usuario contador
docker compose exec backend python manage.py cargar_prorrateo_base --usuario contador --anio 2026
docker compose exec backend python manage.py cargar_flujo_base --usuario contador
```

## Pruebas e integridad
```bash
docker compose exec backend python manage.py test                  # suite completa contra Oracle
docker compose exec backend python manage.py verificar_integridad  # reglas contables sobre los datos reales
```
Matriz de reglas y pruebas: [`docs/PRUEBAS.md`](docs/PRUEBAS.md).

## Respaldos (Git Bash en Windows)
```bash
bash scripts/respaldo.sh                                   # respaldos/AAAAMMDD_HHMMSS/
bash scripts/verificar_respaldo.sh respaldos/<carpeta>     # prueba el respaldo sin tocar los datos
bash scripts/restaurar.sh respaldos/<carpeta>              # reemplaza los datos (pide confirmación)
```

## Manuales
- [Manual de usuario](docs/MANUAL_USUARIO.md)
- [Manual técnico](docs/MANUAL_TECNICO.md)

## Estructura
- `backend/`: Django 5.2 + Django REST Framework (proyecto `config`)
- `frontend/`: React 18 + Vite + React-Bootstrap
- `docs/`: documento base, plan de tareas, especificación de cada tarea, manuales y pruebas
- `scripts/`: respaldo, verificación y restauración de la base (Oracle Data Pump)
