# init-timescaledb.sh - Script para inicializar TimescaleDB
# Guardar como: ./db-init/init-timescaledb.sh

#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Crear extensión TimescaleDB si no existe
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    
    -- Crear usuario y base de datos para la aplicación
    CREATE USER predictor WITH PASSWORD 'predictor_password';
    CREATE DATABASE metrics_db;
    GRANT ALL PRIVILEGES ON DATABASE metrics_db TO predictor;
    
    -- Conectar a la base de datos de la aplicación
    \c metrics_db
    
    -- Crear extensión TimescaleDB en la base de datos de la aplicación
    CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
    
    -- Dar permisos al usuario predictor
    GRANT ALL ON SCHEMA public TO predictor;
EOSQL

# Conectar a la base de datos metrics_db para crear las tablas
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "metrics_db" <<-EOSQL
    -- Tabla para métricas procesadas
    CREATE TABLE IF NOT EXISTS metrics (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        node_id TEXT,
        metric_name TEXT NOT NULL,
        metric_value DOUBLE PRECISION,
        metric_labels JSONB,
        metadata JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('metrics', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para logs procesados
    CREATE TABLE IF NOT EXISTS logs (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        log_level TEXT,
        log_message TEXT,
        log_file TEXT,
        metadata JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('logs', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para anomalías detectadas
    CREATE TABLE IF NOT EXISTS anomalies (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        node_id TEXT,
        anomaly_score DOUBLE PRECISION,
        anomaly_details JSONB,
        metric_data JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('anomalies', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para fallos detectados o reportados
    CREATE TABLE IF NOT EXISTS failures (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        node_id TEXT,
        failure_type TEXT,
        failure_description TEXT,
        failure_data JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('failures', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para predicciones de fallos
    CREATE TABLE IF NOT EXISTS failure_predictions (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        node_id TEXT,
        failure_probability DOUBLE PRECISION,
        prediction_horizon INTEGER,
        prediction_data JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('failure_predictions', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para recomendaciones de acción
    CREATE TABLE IF NOT EXISTS recommendations (
        timestamp TIMESTAMPTZ NOT NULL,
        service_id TEXT NOT NULL,
        node_id TEXT,
        issue_type TEXT,
        action_id TEXT,
        executed BOOLEAN,
        success BOOLEAN,
        recommendation_data JSONB
    );
    
    -- Convertir a tabla de series temporales
    SELECT create_hypertable('recommendations', 'timestamp', if_not_exists => TRUE);
    
    -- Tabla para registro de servicios
    CREATE TABLE IF NOT EXISTS services (
        service_id TEXT PRIMARY KEY,
        service_name TEXT,
        service_type TEXT,
        first_seen TIMESTAMPTZ NOT NULL,
        last_seen TIMESTAMPTZ NOT NULL,
        metadata JSONB
    );
    
    -- Tabla para catálogo de métricas
    CREATE TABLE IF NOT EXISTS metric_catalog (
        metric_name TEXT NOT NULL,
        service_id TEXT NOT NULL,
        data_type TEXT,
        unit TEXT,
        description TEXT,
        first_seen TIMESTAMPTZ NOT NULL,
        last_seen TIMESTAMPTZ NOT NULL,
        PRIMARY KEY (metric_name, service_id)
    );
    
    -- Crear índices para optimizar consultas
    CREATE INDEX IF NOT EXISTS idx_metrics_service_id ON metrics (service_id);
    CREATE INDEX IF NOT EXISTS idx_logs_service_id ON logs (service_id);
    CREATE INDEX IF NOT EXISTS idx_anomalies_service_id ON anomalies (service_id);
    CREATE INDEX IF NOT EXISTS idx_failures_service_id ON failures (service_id);
    CREATE INDEX IF NOT EXISTS idx_predictions_service_id ON failure_predictions (service_id);
    CREATE INDEX IF NOT EXISTS idx_recommendations_service_id ON recommendations (service_id);
    
    -- Dar permisos a todas las tablas al usuario predictor
    GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO predictor;
    GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO predictor;
EOSQL