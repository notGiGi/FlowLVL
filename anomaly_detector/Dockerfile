# Dockerfile para anomaly_detector
# Guardar como: ./anomaly_detector/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorio para modelos
RUN mkdir -p /app/models

# Comando para ejecutar el detector de anomalías
CMD ["python", "anomaly_detector.py"]

# Dockerfile para predictive_engine
# Guardar como: ./predictive_engine/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorio para modelos
RUN mkdir -p /app/models/predictive

# Comando para ejecutar el motor predictivo
CMD ["python", "predictive_engine.py"]