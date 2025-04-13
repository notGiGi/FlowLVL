# Script para restaurar copias de seguridad
# Guardar como: restore.sh
#!/bin/bash

if [ $# -ne 1 ]; then
    echo "Uso: $0 <archivo_de_copia_de_seguridad>"
    exit 1
fi

BACKUP_FILE=$1
TEMP_DIR="./backup_temp"

# Verificar que el archivo exista
if [ ! -f $BACKUP_FILE ]; then
    echo "El archivo de copia de seguridad no existe: $BACKUP_FILE"
    exit 1
fi

# Crear directorio temporal
mkdir -p $TEMP_DIR

# Extraer el archivo
echo "Extrayendo la copia de seguridad..."
tar -xzf $BACKUP_FILE -C $TEMP_DIR

# Restaurar la base de datos
echo "Restaurando la base de datos..."
DB_BACKUP=$(find $TEMP_DIR -name "db_backup_*.sql" | head -n 1)
if [ -f "$DB_BACKUP" ]; then
    docker-compose exec -T timescaledb psql -U predictor -d metrics_db -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
    docker-compose exec -T timescaledb psql -U predictor -d metrics_db < $DB_BACKUP
else
    echo "No se encontró el archivo de copia de seguridad de la base de datos."
fi

# Restaurar los modelos
echo "Restaurando los modelos..."
MODELS_DIR=$(find $TEMP_DIR -name "models_*" -type d | head -n 1)
if [ -d "$MODELS_DIR" ]; then
    if [ -d "$MODELS_DIR/anomaly_detector" ]; then
        docker cp $MODELS_DIR/anomaly_detector $(docker-compose ps -q anomaly_detector):/app/
    fi
    if [ -d "$MODELS_DIR/predictive_engine" ]; then
        docker cp $MODELS_DIR/predictive_engine $(docker-compose ps -q predictive_engine):/app/
    fi
    if [ -d "$MODELS_DIR/action_recommender" ]; then
        docker cp $MODELS_DIR/action_recommender $(docker-compose ps -q action_recommender):/app/
    fi
    if [ -d "$MODELS_DIR/preprocessor" ]; then
        docker cp $MODELS_DIR/preprocessor $(docker-compose ps -q preprocessor):/app/
    fi
else
    echo "No se encontró el directorio de modelos."
fi

# Limpiar directorio temporal
rm -rf $TEMP_DIR

echo "Reiniciando servicios para aplicar los cambios..."
docker-compose restart

echo "Restauración completada."