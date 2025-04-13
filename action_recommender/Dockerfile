# Dockerfile para action_recommender
# Guardar como: ./action_recommender/Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Instalar dependencias
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código
COPY . .

# Crear directorios necesarios
RUN mkdir -p /app/models/recommender
RUN mkdir -p /app/policies

# Comando para ejecutar el recomendador de acciones
CMD ["python", "action_recommender.py"]