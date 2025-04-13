# Dockerfile para preprocessor
# Guardar como: ./preprocessor/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorio para modelos
RUN mkdir -p /app/models/scalers

# Comando para ejecutar el preprocessor
CMD ["python", "preprocessor.py"]