FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar la caché de Docker
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de API
COPY api/ .
COPY utils/ ./utils/

# Copiar componentes compartidos
COPY anomaly_detector/ ./anomaly_detector/
COPY action_recommender/ ./action_recommender/
COPY predictive_engine/ ./predictive_engine/
COPY monitoring/ ./monitoring/

# Crear directorios necesarios
RUN mkdir -p /app/config
RUN mkdir -p /app/data
RUN mkdir -p /app/models

# Exponer puerto
EXPOSE 8000

# Verificación de salud para startup probe
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Entrypoint
CMD ["uvicorn", "controller:create_api_app", "--host", "0.0.0.0", "--port", "8000"]