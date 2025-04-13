import os
import json
import logging
import time
import pandas as pd
import numpy as np
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine, text
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler, MinMaxScaler
import joblib
import threading
import re
import traceback

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('preprocessor')

class DataPreprocessor:
    def __init__(self):
        # Configuración de conexiones
        self.db_host = os.environ.get('DB_HOST', 'timescaledb')
        self.db_port = os.environ.get('DB_PORT', '5432')
        self.db_user = os.environ.get('DB_USER', 'predictor')
        self.db_password = os.environ.get('DB_PASSWORD', 'predictor_password')
        self.db_name = os.environ.get('DB_NAME', 'metrics_db')
        self.kafka_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        
        # Conectar a la base de datos
        self.db_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.engine = create_engine(self.db_url)
        
        # Crear tablas si no existen
        self.initialize_database()
        
        # Configurar consumidor Kafka para métricas
        self.metrics_consumer = KafkaConsumer(
            'raw_metrics',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='preprocessor_metrics'
        )
        
        # Configurar consumidor Kafka para logs
        self.logs_consumer = KafkaConsumer(
            'logs',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='preprocessor_logs'
        )
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Cargar o crear escaladores
        self.scalers = {}
        self.load_scalers()
        
        # Buffers de datos por servicio
        self.service_buffers = {}
        self.buffer_limit = 100  # Número máximo de métricas en buffer antes de procesamiento batch
        
        # Registros de servicios y métricas conocidas
        self.service_registry = {}
        self.known_metrics = {}
        
        # Intervalos de tiempo para procesamiento
        self.buffer_flush_interval = 60  # segundos
        
        logger.info("Preprocesador de datos inicializado correctamente")

    def initialize_database(self):
        """Inicializa la estructura de la base de datos si no existe"""
        try:
            # Crear extensión TimescaleDB
            self.engine.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;"))
            
            # Tabla para métricas procesadas
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS metrics (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service_id TEXT NOT NULL,
                    node_id TEXT,
                    metric_name TEXT NOT NULL,
                    metric_value DOUBLE PRECISION,
                    metric_labels JSONB,
                    metadata JSONB
                );
            """))
            
            # Convertir a tabla de series temporales
            try:
                self.engine.execute(text(
                    "SELECT create_hypertable('metrics', 'timestamp', if_not_exists => TRUE);"
                ))
            except:
                logger.warning("No se pudo crear hypertable para métricas, puede que ya exista")
            
            # Tabla para logs procesados
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS logs (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service_id TEXT NOT NULL,
                    log_level TEXT,
                    log_message TEXT,
                    log_file TEXT,
                    metadata JSONB
                );
            """))
            
            # Convertir a tabla de series temporales
            try:
                self.engine.execute(text(
                    "SELECT create_hypertable('logs', 'timestamp', if_not_exists => TRUE);"
                ))
            except:
                logger.warning("No se pudo crear hypertable para logs, puede que ya exista")
            
            # Tabla para anomalías detectadas
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS anomalies (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service_id TEXT NOT NULL,
                    node_id TEXT,
                    anomaly_score DOUBLE PRECISION,
                    anomaly_details JSONB,
                    metric_data JSONB
                );
            """))
            
            # Tabla para fallos detectados o reportados
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS failures (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service_id TEXT NOT NULL,
                    node_id TEXT,
                    failure_type TEXT,
                    failure_description TEXT,
                    failure_data JSONB
                );
            """))
            
            # Tabla para predicciones de fallos
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS failure_predictions (
                    timestamp TIMESTAMPTZ NOT NULL,
                    service_id TEXT NOT NULL,
                    node_id TEXT,
                    failure_probability DOUBLE PRECISION,
                    prediction_horizon INTEGER,
                    prediction_data JSONB
                );
            """))
            
            # Tabla para recomendaciones de acción
            self.engine.execute(text("""
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
            """))
            
            # Tabla para registro de servicios
            self.engine.execute(text("""
                CREATE TABLE IF NOT EXISTS services (
                    service_id TEXT PRIMARY KEY,
                    service_name TEXT,
                    service_type TEXT,
                    first_seen TIMESTAMPTZ NOT NULL,
                    last_seen TIMESTAMPTZ NOT NULL,
                    metadata JSONB
                );
            """))
            
            # Tabla para catálogo de métricas
            self.engine.execute(text("""
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
            """))
            
            # Índices para optimizar consultas
            self.engine.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_metrics_service_id ON metrics (service_id);
                CREATE INDEX IF NOT EXISTS idx_logs_service_id ON logs (service_id);
                CREATE INDEX IF NOT EXISTS idx_anomalies_service_id ON anomalies (service_id);
                CREATE INDEX IF NOT EXISTS idx_failures_service_id ON failures (service_id);
                CREATE INDEX IF NOT EXISTS idx_predictions_service_id ON failure_predictions (service_id);
                CREATE INDEX IF NOT EXISTS idx_recommendations_service_id ON recommendations (service_id);
            """))
            
            logger.info("Base de datos inicializada correctamente")
            
        except Exception as e:
            logger.error(f"Error al inicializar la base de datos: {str(e)}")
            logger.error(traceback.format_exc())

    def load_scalers(self):
        """Carga escaladores para cada servicio o crea nuevos si no existen"""
        try:
            # Directorio para almacenar escaladores
            scalers_dir = "/app/models/scalers"
            os.makedirs(scalers_dir, exist_ok=True)
            
            # Consultar servicios registrados
            query = "SELECT service_id FROM services"
            services_df = pd.read_sql(query, self.engine)
            
            if not services_df.empty:
                for service_id in services_df['service_id']:
                    scaler_path = os.path.join(scalers_dir, f"{service_id}_scaler.joblib")
                    
                    if os.path.exists(scaler_path):
                        self.scalers[service_id] = joblib.load(scaler_path)
                        logger.info(f"Scaler cargado para servicio: {service_id}")
            
        except Exception as e:
            logger.error(f"Error al cargar escaladores: {str(e)}")

    def save_scaler(self, service_id, scaler):
        """Guarda un escalador para un servicio específico"""
        try:
            scalers_dir = "/app/models/scalers"
            os.makedirs(scalers_dir, exist_ok=True)
            
            scaler_path = os.path.join(scalers_dir, f"{service_id}_scaler.joblib")
            joblib.dump(scaler, scaler_path)
            
            logger.info(f"Scaler guardado para servicio: {service_id}")
            
        except Exception as e:
            logger.error(f"Error al guardar scaler para servicio {service_id}: {str(e)}")

    def register_service(self, service_id, metadata={}):
        """Registra un servicio en la base de datos"""
        try:
            # Verificar si el servicio ya está registrado
            if service_id in self.service_registry:
                # Actualizar último visto
                query = """
                    UPDATE services 
                    SET last_seen = NOW(), 
                        metadata = metadata || %s::jsonb
                    WHERE service_id = %s
                """
                self.engine.execute(text(query), json.dumps(metadata), service_id)
                return
            
            # Extraer nombre y tipo del ID del servicio o de los metadatos
            service_name = metadata.get('service_name', service_id)
            service_type = metadata.get('service_type', 'unknown')
            
            # Insertar nuevo servicio
            query = """
                INSERT INTO services (
                    service_id, service_name, service_type, first_seen, last_seen, metadata
                ) VALUES (%s, %s, %s, NOW(), NOW(), %s)
                ON CONFLICT (service_id) 
                DO UPDATE SET 
                    last_seen = NOW(),
                    metadata = services.metadata || %s::jsonb
            """
            self.engine.execute(
                text(query), 
                service_id, service_name, service_type, 
                json.dumps(metadata), json.dumps(metadata)
            )
            
            # Actualizar registro local
            self.service_registry[service_id] = {
                'name': service_name,
                'type': service_type,
                'first_seen': datetime.now(),
                'last_seen': datetime.now()
            }
            
            logger.info(f"Servicio registrado: {service_id}")
            
        except Exception as e:
            logger.error(f"Error al registrar servicio {service_id}: {str(e)}")

    def register_metric(self, metric_name, service_id, data_type='numeric', unit='', description=''):
        """Registra una métrica en el catálogo"""
        try:
            # Crear clave única para esta métrica
            metric_key = f"{service_id}:{metric_name}"
            
            # Verificar si la métrica ya está registrada
            if metric_key in self.known_metrics:
                # Actualizar último visto
                query = """
                    UPDATE metric_catalog 
                    SET last_seen = NOW() 
                    WHERE metric_name = %s AND service_id = %s
                """
                self.engine.execute(text(query), metric_name, service_id)
                return
            
            # Inferir tipo de datos si no se proporciona
            if data_type == 'numeric':
                # Se podría inferir más detalladamente según el patrón de nombres
                if any(kw in metric_name.lower() for kw in ['count', 'total', 'sum', 'number']):
                    data_type = 'counter'
                elif any(kw in metric_name.lower() for kw in ['percent', 'ratio', 'utilization']):
                    data_type = 'gauge'
                elif any(kw in metric_name.lower() for kw in ['time', 'duration', 'latency']):
                    data_type = 'timer'
            
            # Inferir unidad si no se proporciona
            if not unit:
                if any(kw in metric_name.lower() for kw in ['percent', 'ratio']):
                    unit = '%'
                elif any(kw in metric_name.lower() for kw in ['time', 'duration', 'latency']):
                    unit = 'ms'
                elif any(kw in metric_name.lower() for kw in ['bytes', 'memory']):
                    unit = 'bytes'
            
            # Insertar nueva métrica
            query = """
                INSERT INTO metric_catalog (
                    metric_name, service_id, data_type, unit, description, first_seen, last_seen
                ) VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                ON CONFLICT (metric_name, service_id) 
                DO UPDATE SET 
                    last_seen = NOW(),
                    data_type = EXCLUDED.data_type,
                    unit = EXCLUDED.unit,
                    description = EXCLUDED.description
            """
            self.engine.execute(
                text(query), 
                metric_name, service_id, data_type, unit, description
            )
            
            # Actualizar registro local
            self.known_metrics[metric_key] = {
                'data_type': data_type,
                'unit': unit,
                'description': description,
                'first_seen': datetime.now(),
                'last_seen': datetime.now()
            }
            
            logger.debug(f"Métrica registrada: {metric_name} para servicio {service_id}")
            
        except Exception as e:
            logger.error(f"Error al registrar métrica {metric_name}: {str(e)}")

    def process_metrics(self, metrics_data):
        """Procesa los datos de métricas crudas"""
        try:
            # Extraer metadatos básicos
            service_id = metrics_data.get('service_id', 'unknown')
            collector_type = metrics_data.get('collector_type', 'unknown')
            timestamp_str = metrics_data.get('timestamp', datetime.now().isoformat())
            node_id = metrics_data.get('node_id', 'unknown')
            
            # Convertir timestamp si es string
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now()
            
            # Registrar servicio
            self.register_service(service_id, {
                'collector_type': collector_type,
                'last_timestamp': timestamp_str
            })
            
            # Extraer métricas numéricas y metadatos
            metrics = []
            for key, value in metrics_data.items():
                # Ignorar campos que no son métricas
                if key in ['service_id', 'collector_type', 'timestamp', 'node_id']:
                    continue
                
                # Si es un valor numérico, procesarlo como métrica
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    # Registrar métrica
                    self.register_metric(key, service_id)
                    
                    # Añadir a lista de métricas
                    metrics.append({
                        'timestamp': timestamp,
                        'service_id': service_id,
                        'node_id': node_id,
                        'metric_name': key,
                        'metric_value': float(value),
                        'metric_labels': {},
                        'metadata': {
                            'collector_type': collector_type
                        }
                    })
            
            # Si hay métricas, guardarlas en la base de datos
            if metrics:
                metrics_df = pd.DataFrame(metrics)
                metrics_df.to_sql('metrics', self.engine, if_exists='append', index=False)
            
            # Añadir a buffer para procesamiento por lotes
            if service_id not in self.service_buffers:
                self.service_buffers[service_id] = []
            
            # Añadir solo valores numéricos al buffer
            numeric_data = {
                'timestamp': timestamp,
                'node_id': node_id
            }
            
            for key, value in metrics_data.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    numeric_data[key] = value
            
            self.service_buffers[service_id].append(numeric_data)
            
            # Si el buffer alcanza el límite, procesarlo
            if len(self.service_buffers[service_id]) >= self.buffer_limit:
                self.process_service_buffer(service_id)
            
            return metrics
                
        except Exception as e:
            logger.error(f"Error al procesar métricas: {str(e)}")
            return []

    def process_service_buffer(self, service_id):
        """Procesa el buffer de un servicio y envía datos normalizados"""
        try:
            buffer = self.service_buffers[service_id]
            
            if not buffer:
                return
            
            # Convertir buffer a DataFrame
            buffer_df = pd.DataFrame(buffer)
            
            # Seleccionar solo columnas numéricas (excepto timestamp)
            numeric_cols = buffer_df.select_dtypes(include=['number']).columns.tolist()
            if 'timestamp' in numeric_cols:
                numeric_cols.remove('timestamp')
            
            if not numeric_cols:
                self.service_buffers[service_id] = []
                return
            
            # Preparar datos para normalización
            X = buffer_df[numeric_cols].fillna(0)
            
            # Normalizar datos con MinMaxScaler
            if service_id not in self.scalers:
                scaler = MinMaxScaler()
                X_scaled = scaler.fit_transform(X)
                self.scalers[service_id] = scaler
                self.save_scaler(service_id, scaler)
            else:
                # Si el scaler ya existe, intentar usarlo
                try:
                    scaler = self.scalers[service_id]
                    X_scaled = scaler.transform(X)
                except:
                    # Si falla (ej: nuevas métricas), crear uno nuevo
                    scaler = MinMaxScaler()
                    X_scaled = scaler.fit_transform(X)
                    self.scalers[service_id] = scaler
                    self.save_scaler(service_id, scaler)
            
            # Convertir datos normalizados de vuelta a DataFrame
            X_scaled_df = pd.DataFrame(X_scaled, columns=numeric_cols)
            
            # Añadir metadatos de vuelta
            X_scaled_df['timestamp'] = buffer_df['timestamp']
            if 'node_id' in buffer_df.columns:
                X_scaled_df['node_id'] = buffer_df['node_id']
            
            # Enviar cada fila normalizada a Kafka
            for i, row in X_scaled_df.iterrows():
                # Convertir a diccionario y añadir metadatos
                row_dict = row.to_dict()
                row_dict['service_id'] = service_id
                
                # Asegurarse de que timestamp sea string
                if isinstance(row_dict['timestamp'], (datetime, pd.Timestamp)):
                    row_dict['timestamp'] = row_dict['timestamp'].isoformat()
                
                # Enviar a Kafka
                self.producer.send('preprocessed_metrics', row_dict)
            
            # Limpiar buffer
            self.service_buffers[service_id] = []
            
            logger.debug(f"Buffer procesado para servicio {service_id}: {len(buffer)} métricas")
            
        except Exception as e:
            logger.error(f"Error al procesar buffer para servicio {service_id}: {str(e)}")
            # Mantener el buffer en caso de error
            if len(self.service_buffers[service_id]) > self.buffer_limit * 2:
                # Si el buffer crece demasiado, limpiarlo parcialmente
                self.service_buffers[service_id] = self.service_buffers[service_id][-self.buffer_limit:]

    def process_logs(self, log_data):
        """Procesa los datos de logs"""
        try:
            # Extraer metadatos básicos
            service_id = log_data.get('service_id', 'unknown')
            timestamp_str = log_data.get('timestamp', datetime.now().isoformat())
            log_level = log_data.get('log_level', 'UNKNOWN')
            log_message = log_data.get('log_message', '')
            log_file = log_data.get('log_file', '')
            
            # Convertir timestamp si es string
            if isinstance(timestamp_str, str):
                timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            else:
                timestamp = datetime.now()
            
            # Registrar servicio
            self.register_service(service_id, {
                'has_logs': True,
                'last_log_level': log_level,
                'last_log_timestamp': timestamp_str
            })
            
            # Crear entrada de log
            log_entry = {
                'timestamp': timestamp,
                'service_id': service_id,
                'log_level': log_level,
                'log_message': log_message,
                'log_file': log_file,
                'metadata': {
                    'preprocessed': True
                }
            }
            
            # Extraer información adicional del mensaje
            # Por ejemplo, códigos de error, stacktraces, etc.
            error_info = self.extract_error_info(log_message)
            if error_info:
                log_entry['metadata']['error_info'] = error_info
            
            # Guardar en la base de datos
            log_df = pd.DataFrame([log_entry])
            log_df.to_sql('logs', self.engine, if_exists='append', index=False)
            
            # Si es un error grave, registrarlo como un fallo potencial
            if log_level in ['ERROR', 'FATAL', 'CRITICAL']:
                failure_entry = {
                    'timestamp': timestamp,
                    'service_id': service_id,
                    'node_id': log_data.get('node_id', 'unknown'),
                    'failure_type': 'log_error',
                    'failure_description': log_message[:200],  # Truncar descripción
                    'failure_data': json.dumps({
                        'log_level': log_level,
                        'log_message': log_message,
                        'log_file': log_file
                    })
                }
                
                # Guardar en la tabla de fallos
                failure_df = pd.DataFrame([failure_entry])
                failure_df.to_sql('failures', self.engine, if_exists='append', index=False)
                
                # Enviar alerta a Kafka
                self.producer.send('failures', {
                    'timestamp': timestamp.isoformat(),
                    'service_id': service_id,
                    'node_id': log_data.get('node_id', 'unknown'),
                    'failure_type': 'log_error',
                    'failure_description': log_message[:200],
                    'log_level': log_level,
                    'log_file': log_file
                })
            
            # También enviar log procesado a Kafka
            log_entry['timestamp'] = timestamp.isoformat()
            log_entry['metadata'] = json.dumps(log_entry['metadata'])
            self.producer.send('processed_logs', log_entry)
            
            return log_entry
                
        except Exception as e:
            logger.error(f"Error al procesar log: {str(e)}")
            return None

    def extract_error_info(self, log_message):
        """Extrae información adicional de un mensaje de error"""
        error_info = {}
        
        # Buscar códigos de error comunes
        error_code_match = re.search(r'error\s+code[:\s]+(\d+)', log_message, re.IGNORECASE)
        if error_code_match:
            error_info['error_code'] = error_code_match.group(1)
        
        # Buscar excepciones
        exception_match = re.search(r'exception[:\s]+([\w\.]+Exception)', log_message, re.IGNORECASE)
        if exception_match:
            error_info['exception_type'] = exception_match.group(1)
        
        # Buscar stacktrace
        if 'Traceback' in log_message:
            error_info['has_stacktrace'] = True
        
        # Buscar componentes comunes en mensajes de error
        if re.search(r'database|db|sql|query', log_message, re.IGNORECASE):
            error_info['component'] = 'database'
        elif re.search(r'network|connection|connect|socket|http', log_message, re.IGNORECASE):
            error_info['component'] = 'network'
        elif re.search(r'memory|allocation|out of memory', log_message, re.IGNORECASE):
            error_info['component'] = 'memory'
        elif re.search(r'disk|file|io|read|write', log_message, re.IGNORECASE):
            error_info['component'] = 'disk'
        
        return error_info if error_info else None

    def flush_buffers_periodically(self):
        """Función para vaciar los buffers periódicamente"""
        while True:
            try:
                time.sleep(self.buffer_flush_interval)
                
                # Procesar cada buffer de servicio
                for service_id in list(self.service_buffers.keys()):
                    if self.service_buffers[service_id]:
                        self.process_service_buffer(service_id)
                
            except Exception as e:
                logger.error(f"Error al vaciar buffers: {str(e)}")

    def run(self):
        """Ejecuta el preprocesador en varios hilos"""
        # Iniciar hilo para vaciar buffers periódicamente
        buffer_thread = threading.Thread(target=self.flush_buffers_periodically, daemon=True)
        buffer_thread.start()
        
        # Iniciar hilos para consumir de múltiples tópicos
        metrics_thread = threading.Thread(target=self.consume_metrics, daemon=True)
        logs_thread = threading.Thread(target=self.consume_logs, daemon=True)
        
        metrics_thread.start()
        logs_thread.start()
        
        logger.info("Preprocesador de datos iniciado, esperando mensajes...")
        
        try:
            # Mantener el proceso principal vivo
            while True:
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("Preprocesador de datos detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el preprocesador de datos: {str(e)}")

    def consume_metrics(self):
        """Consume mensajes de métricas"""
        try:
            for message in self.metrics_consumer:
                self.process_metrics(message.value)
        except Exception as e:
            logger.error(f"Error en consumidor de métricas: {str(e)}")
            
    def consume_logs(self):
        """Consume mensajes de logs"""
        try:
            for message in self.logs_consumer:
                self.process_logs(message.value)
        except Exception as e:
            logger.error(f"Error en consumidor de logs: {str(e)}")


if __name__ == "__main__":
    # Esperar a que Kafka y la base de datos estén disponibles
    time.sleep(15)
    
    # Iniciar el preprocesador
    preprocessor = DataPreprocessor()
    preprocessor.run()