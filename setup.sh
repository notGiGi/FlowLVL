#!/bin/bash
# setup.sh - Script para clonar el repositorio e inicializar el sistema

# Verificar si Docker y Docker Compose están instalados
if ! command -v docker &> /dev/null; then
    echo "Docker no está instalado. Por favor, instálelo antes de continuar."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "Docker Compose no está instalado. Por favor, instálelo antes de continuar."
    exit 1
fi

# Crear la estructura de directorios
mkdir -p predictive-maintenance
cd predictive-maintenance

# Crear directorios para cada componente
mkdir -p collectors preprocessor anomaly_detector predictive_engine action_recommender api dashboard
mkdir -p prometheus grafana grafana/provisioning/datasources grafana/provisioning/dashboards

# Copiar archivos de configuración
echo "Copiando archivos de configuración..."

# Colocar tu docker-compose.yml aquí
# Colocar tus Dockerfiles en los directorios correspondientes
# Colocar tus archivos de código en los directorios correspondientes

# Construir e iniciar los contenedores
echo "Construyendo e iniciando los contenedores..."
docker-compose build
docker-compose up -d

echo "Esperando a que los servicios estén disponibles..."
sleep 30

echo "¡Sistema inicializado correctamente!"
echo "Puedes acceder al dashboard en http://localhost:3001"
echo "Puedes acceder a Grafana en http://localhost:3000 (usuario: admin, contraseña: admin)"
echo "La API REST está disponible en http://localhost:8000"