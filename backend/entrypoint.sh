#!/bin/sh
set -e

python manage.py migrate --noinput

# Superusuario inicial (idempotente: si ya existe, sigue).
if [ -n "$DJANGO_SUPERUSER_USERNAME" ]; then
  python manage.py createsuperuser --noinput || true
fi

# Datos de demostración: solo si la base aún no tiene asientos (los asientos
# contabilizados son inmutables, recargar el fixture fallaría).
if [ "$LOAD_DEMO_DATA" = "1" ]; then
  if python manage.py shell -c "import sys; from contabilidad.models import Asiento; sys.exit(0 if Asiento.objects.exists() else 1)"; then
    echo "LOAD_DEMO_DATA: la base ya tiene asientos; no se recarga fixtures/demo.json"
  else
    # loaddata en una transacción, con los triggers de reglas en pausa y verificación de integridad.
    python manage.py cargar_fixture fixtures/demo.json
  fi
fi

exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-10000} \
  --workers ${WEB_CONCURRENCY:-2} --timeout 60 --access-logfile -
