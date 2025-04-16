FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements primero para aprovechar la caché
COPY notification_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY notification_service/ .
COPY utils/ ./utils/

# Exponer puerto para métricas Prometheus
EXPOSE 8080

# Comando para ejecutar
CMD ["python", "notification_service.py"]