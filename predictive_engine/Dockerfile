FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar la caché
COPY predictive_engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY predictive_engine/ .
COPY utils/ ./utils/

# Crear directorios necesarios
RUN mkdir -p /app/models/predictive
RUN mkdir -p /app/data

# Exponer puerto para métricas Prometheus
EXPOSE 8080

# Comando para ejecutar
CMD ["python", "predictive_engine.py"]