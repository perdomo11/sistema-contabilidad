# Imagen única para Render: Django sirve la API, el admin y el build de React (WhiteNoise).

# --- Etapa 1: build del frontend ---------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund --loglevel=error
COPY frontend/ ./
RUN npm run build

# --- Etapa 2: backend --------------------------------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend_dist

WORKDIR /app

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./
COPY --from=frontend /frontend/dist /app/frontend_dist

# Clave solo para collectstatic (no queda en la imagen como ENV).
RUN DJANGO_SECRET_KEY=solo-build-collectstatic-no-se-usa-en-ejecucion-7f3c9a1e DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh \
    && useradd --create-home --uid 10001 app

USER app
EXPOSE 10000
CMD ["./entrypoint.sh"]
