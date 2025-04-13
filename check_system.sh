# Script para verificar el estado del sistema
# Guardar como: check_system.sh
#!/bin/bash

# Verificar el estado de los servicios Docker
echo "Verificando el estado de los servicios..."
docker-compose ps

# Verificar la conexión a la API
echo ""
echo "Verificando la conexión a la API..."
curl -s http://localhost:8000/health

# Verificar la conexión a Kafka
echo ""
echo "Verificando la conexión a Kafka..."
docker-compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092

# Verificar la conexión a la base de datos
echo ""
echo "Verificando la conexión a TimescaleDB..."
docker-compose exec timescaledb psql -U predictor -d metrics_db -c "SELECT 'Conexión exitosa';"