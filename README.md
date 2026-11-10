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

## Estructura
- `backend/`: Django 5.2 + Django REST Framework (proyecto `config`)
- `frontend/`: React 18 + Vite + React-Bootstrap
- `docs/`: documento base, plan de tareas y especificación de cada tarea
