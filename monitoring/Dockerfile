FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar la caché de Docker
COPY monitoring/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de monitoring
COPY monitoring/ .
COPY utils/ ./utils/

# Copiar archivo de configuración
COPY config/ ./config/

# Crear directorios necesarios
RUN mkdir -p /app/data/profiles
RUN mkdir -p /app/models/profiles

# Exponer puerto para métricas Prometheus (opcional)
EXPOSE 8080

# Entrypoint
CMD ["python", "service_profiler_service.py"]