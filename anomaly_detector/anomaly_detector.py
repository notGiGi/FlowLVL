# anomaly_detector/main.py

import os
import json
import logging
import time
import threading
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine, text
from enhanced_detector import EnhancedAnomalyDetector

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector_service')

class AnomalyDetectorService:
    """Servicio de detección de anomalías con soporte para múltiples algoritmos"""
    
    def __init__(self):
        # Configuración desde variables de entorno
        self.db_host = os.environ.get('DB_HOST', 'timescaledb')
        self.db_port = os.environ.get('DB_PORT', '5432')
        self.db_user = os.environ.get('DB_USER', 'predictor')
        self.db_password = os.environ.get('DB_PASSWORD', 'predictor_password')
        self.db_name = os.environ.get('DB_NAME', 'metrics_db')
        self.kafka_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        self.anomaly_threshold = float(os.environ.get('ANOMALY_THRESHOLD', '0.3'))
        
        # Conectar a la base de datos
        self.db_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.engine = create_engine(self.db_url)
        
        # Configurar consumidor Kafka
        self.consumer = KafkaConsumer(
            'preprocessed_metrics',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='anomaly_detector'
        )
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Crear detector de anomalías mejorado
        self.detector = EnhancedAnomalyDetector(config={
            'anomaly_threshold': self.anomaly_threshold,
            'models_dir': '/app/models/anomaly'
        })
        
        # Control de estado del servicio
        self.running = False
        self.health_status = {
            'status': 'starting',
            'last_update': time.time(),
            'processed_messages': 0,
            'detected_anomalies': 0,
            'errors': 0
        }
        
        logger.info("Servicio de detección de anomalías inicializado")
    
    def start(self):
        """Inicia el servicio de detección de anomalías"""
        if self.running:
            logger.warning("El servicio ya está en ejecución")
            return
        
        self.running = True
        
        # Iniciar hilo de procesamiento de métricas
        self.processing_thread = threading.Thread(target=self.process_metrics, daemon=True)
        self.processing_thread.start()
        
        # Iniciar hilo de monitoreo de salud
        self.health_thread = threading.Thread(target=self.monitor_health, daemon=True)
        self.health_thread.start()
        
        logger.info("Servicio de detección de anomalías iniciado")
        
        # Mantener hilo principal vivo
        try:
            while self.running:
                time.sleep(10)
                
                # Verificar estado de hilos
                if not self.processing_thread.is_alive():
                    logger.error("Hilo de procesamiento caído, reiniciando...")
                    self.processing_thread = threading.Thread(target=self.process_metrics, daemon=True)
                    self.processing_thread.start()
                
                if not self.health_thread.is_alive():
                    logger.error("Hilo de monitoreo caído, reiniciando...")
                    self.health_thread = threading.Thread(target=self.monitor_health, daemon=True)
                    self.health_thread.start()
                
        except KeyboardInterrupt:
            logger.info("Recibida señal de interrupción, deteniendo servicio...")
            self.stop()
    
    def stop(self):
        """Detiene el servicio de detección de anomalías"""
        self.running = False
        logger.info("Servicio de detección de anomalías detenido")
    
    def process_metrics(self):
        """Procesa métricas de Kafka y detecta anomalías"""
        consecutive_errors = 0
        backoff_time = 1  # segundos
        
        while self.running:
            try:
                # Reinicio del backoff si no hay errores
                if consecutive_errors == 0:
                    backoff_time = 1
                
                # Leer mensajes
                message_count = 0
                message_batch = self.consumer.poll(timeout_ms=1000, max_records=100)
                
                # Procesar mensajes
                for topic_partition, messages in message_batch.items():
                    for message in messages:
                        try:
                            metrics_data = message.value
                            
                            if not isinstance(metrics_data, dict):
                                logger.warning(f"Formato de mensaje inválido: {metrics_data}")
                                continue
                            
                            # Extraer información básica
                            service_id = metrics_data.get('service_id', 'unknown')
                            timestamp = metrics_data.get('timestamp', None)
                            
                            # Detectar anomalías
                            is_anomaly, anomaly_score, details = self.detector.detect_anomalies(metrics_data)
                            
                            # Actualizar estadísticas
                            message_count += 1
                            self.health_status['processed_messages'] += 1
                            
                            # Si se detectó una anomalía
                            if is_anomaly:
                                self.health_status['detected_anomalies'] += 1
                                self.handle_anomaly(service_id, timestamp, anomaly_score, metrics_data, details)
                        
                        except Exception as e:
                            logger.error(f"Error al procesar mensaje: {str(e)}")
                            self.health_status['errors'] += 1
                
                # Resetear contador de errores consecutivos
                if message_count > 0:
                    consecutive_errors = 0
                    backoff_time = 1
                
                # Breve pausa para evitar saturación de CPU si no hay mensajes
                if message_count == 0:
                    time.sleep(0.1)
                
            except Exception as e:
                # Error al consumir mensajes
                consecutive_errors += 1
                self.health_status['errors'] += 1
                logger.error(f"Error en el procesamiento de métricas (intento {consecutive_errors}): {str(e)}")
                
                # Aplicar backoff exponencial con jitter
                sleep_time = min(60, backoff_time * (1 + 0.1 * (2 * np.random.random() - 1)))
                logger.info(f"Esperando {sleep_time:.2f}s antes de reintentar")
                time.sleep(sleep_time)
                backoff_time = min(60, backoff_time * 2)
    
    def handle_anomaly(self, service_id, timestamp, anomaly_score, metrics_data, details):
        """Maneja una anomalía detectada"""
        try:
            # Crear registro de anomalía
            anomaly_record = {
                'timestamp': timestamp or self.get_current_timestamp(),
                'service_id': service_id,
                'node_id': metrics_data.get('node_id', 'unknown'),
                'anomaly_score': float(anomaly_score),
                'anomaly_type': details.get('anomaly_type', 'unknown'),
                'anomaly_details': json.dumps(details),
                'metric_data': json.dumps(metrics_data)
            }
            
            # Almacenar en la base de datos
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                        INSERT INTO anomalies (
                            timestamp, service_id, node_id, anomaly_score, 
                            anomaly_details, metric_data
                        ) VALUES (
                            :timestamp, :service_id, :node_id, :anomaly_score, 
                            :anomaly_details::jsonb, :metric_data::jsonb
                        )
                    """),
                    {
                        'timestamp': timestamp or self.get_current_timestamp(),
                        'service_id': service_id,
                        'node_id': metrics_data.get('node_id', 'unknown'),
                        'anomaly_score': float(anomaly_score),
                        'anomaly_details': json.dumps(details),
                        'metric_data': json.dumps(metrics_data)
                    }
                )
            
            # Enviar a Kafka para notificaciones y acciones
            kafka_message = {
                'timestamp': timestamp or self.get_current_timestamp(),
                'service_id': service_id,
                'anomaly_score': float(anomaly_score),
                'anomaly_type': details.get('anomaly_type', 'unknown'),
                'details': details,
                'metrics': {k: v for k, v in metrics_data.items() if k not in ['timestamp', 'service_id', 'node_id']}
            }
            
            self.producer.send('anomalies', kafka_message)
            
            logger.info(f"Anomalía detectada en {service_id}: {details.get('anomaly_type', 'unknown')} (score: {anomaly_score:.3f})")
            
        except Exception as e:
            logger.error(f"Error al manejar anomalía: {str(e)}")
            self.health_status['errors'] += 1
    
    def get_current_timestamp(self):
        """Obtiene timestamp actual en formato ISO"""
        return datetime.now().isoformat()
    
    def monitor_health(self):
        """Monitorea la salud del servicio y publica métricas"""
        while self.running:
            try:
                # Actualizar estado
                self.health_status['status'] = 'healthy'
                self.health_status['last_update'] = time.time()
                
                # Publicar métricas de salud
                health_metrics = {
                    'timestamp': self.get_current_timestamp(),
                    'service': 'anomaly_detector',
                    'status': self.health_status['status'],
                    'metrics': {
                        'processed_messages': self.health_status['processed_messages'],
                        'detected_anomalies': self.health_status['detected_anomalies'],
                        'errors': self.health_status['errors'],
                        'uptime_seconds': time.time() - self.health_status.get('start_time', time.time())
                    }
                }
                
                self.producer.send('service_health', health_metrics)
                
                # Publicar métricas adicionales si es necesario
                # Esperar antes de la próxima actualización
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Error en monitoreo de salud: {str(e)}")
                time.sleep(5)  # Tiempo más corto para recuperarse rápido

# Punto de entrada
if __name__ == "__main__":
    # Esperar a que Kafka y la base de datos estén disponibles (simple backoff)
    max_retries = 10
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Probar conexión a base de datos
            engine = create_engine(f"postgresql://{os.environ.get('DB_USER', 'predictor')}:{os.environ.get('DB_PASSWORD', 'predictor_password')}@{os.environ.get('DB_HOST', 'timescaledb')}:{os.environ.get('DB_PORT', '5432')}/{os.environ.get('DB_NAME', 'metrics_db')}")
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("Conexión a base de datos establecida")
            break
        except Exception as e:
            retry_count += 1
            wait_time = 5 * retry_count
            logger.warning(f"Error al conectar a la base de datos (intento {retry_count}/{max_retries}): {str(e)}")
            logger.warning(f"Esperando {wait_time}s antes de reintentar...")
            time.sleep(wait_time)
    
    if retry_count >= max_retries:
        logger.error("No se pudo conectar a la base de datos después de varios intentos")
        exit(1)
    
    # Iniciar servicio
    service = AnomalyDetectorService()
    service.start()