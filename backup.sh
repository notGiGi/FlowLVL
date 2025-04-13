# Script para realizar copias de seguridad
# Guardar como: backup.sh
#!/bin/bash

BACKUP_DIR="./backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Crear directorio de copias de seguridad si no existe
mkdir -p $BACKUP_DIR

# Respaldar la base de datos
echo "Realizando copia de seguridad de la base de datos..."
docker-compose exec -T timescaledb pg_dump -U predictor metrics_db > $BACKUP_DIR/db_backup_$TIMESTAMP.sql

# Respaldar los modelos entrenados
echo "Realizando copia de seguridad de los modelos..."
mkdir -p $BACKUP_DIR/models_$TIMESTAMP
docker cp $(docker-compose ps -q anomaly_detector):/app/models $BACKUP_DIR/models_$TIMESTAMP/anomaly_detector
docker cp $(docker-compose ps -q predictive_engine):/app/models $BACKUP_DIR/models_$TIMESTAMP/predictive_engine
docker cp $(docker-compose ps -q action_recommender):/app/models $BACKUP_DIR/models_$TIMESTAMP/action_recommender
docker cp $(docker-compose ps -q preprocessor):/app/models $BACKUP_DIR/models_$TIMESTAMP/preprocessor

# Comprimir la copia de seguridad
echo "Comprimiendo la copia de seguridad..."
tar -czf $BACKUP_DIR/backup_$TIMESTAMP.tar.gz $BACKUP_DIR/db_backup_$TIMESTAMP.sql $BACKUP_DIR/models_$TIMESTAMP

# Limpiar archivos temporales
rm $BACKUP_DIR/db_backup_$TIMESTAMP.sql
rm -rf $BACKUP_DIR/models_$TIMESTAMP

echo "Copia de seguridad completada: $BACKUP_DIR/backup_$TIMESTAMP.tar.gz"