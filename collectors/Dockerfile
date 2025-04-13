# Dockerfile para collectors
# Guardar como: ./collectors/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorio para configuración
RUN mkdir -p /app/config

# Comando para ejecutar el collector
CMD ["python", "collector.py"]