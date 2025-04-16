import os
import json
import time
import logging
import threading
import redis
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from prometheus_client import start_http_server, Counter, Gauge, Summary

# Importar componentes necesarios
from monitoring.service_profiler import ServiceProfiler
from utils.metrics import MetricsCollector

# Configurar logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('service_profiler_service')

class ServiceProfilerService:
    """
    Servicio principal que ejecuta el perfilador de servicios y gestiona
    las actualizaciones automáticas de perfiles y recomendaciones.
    """
    
    def __init__(self, config=None):
        """
        Inicializa el servicio de perfilador
        
        Args:
            config: Configuración opcional
        """
        self.config = config or {}
        
        # Cargar configuración desde variables de entorno
        self._load_config_from_env()
        
        # Inicializar componentes
        self.service_profiler = ServiceProfiler(config=self.config)
        self.metrics = MetricsCollector(config=self.config)
        
        # Conexión a Redis para recepción de métricas
        self.redis_client = self._initialize_redis()
        
        # Control para threads
        self.running = True
        self.threads = []
        
        # Iniciar threads de trabajo
        self._start_workers()
        
        # Iniciar servidor de métricas Prometheus
        self._start_metrics_server()
        
        logger.info("Servicio de perfilador iniciado")
    
    def _load_config_from_env(self):
        """Carga configuración desde variables de entorno"""
        # Redis
        self.config.setdefault('redis_host', os.environ.get('REDIS_HOST', 'localhost'))
        self.config.setdefault('redis_port', int(os.environ.get('REDIS_PORT', 6379)))
        self.config.setdefault('redis_password', os.environ.get('REDIS_PASSWORD', ''))
        
        # Directorios y rutas
        self.config.setdefault('profiles_dir', os.environ.get('PROFILES_DIR', './data/profiles'))
        self.config.setdefault('models_dir', os.environ.get('MODELS_DIR', './models/profiles'))
        
        # Intervalos y configuración
        self.config.setdefault('metrics_process_interval', int(os.environ.get('METRICS_PROCESS_INTERVAL', 10)))
        self.config.setdefault('profile_update_interval', int(os.environ.get('PROFILE_UPDATE_INTERVAL', 3600)))
        self.config.setdefault('metrics_batch_size', int(os.environ.get('METRICS_BATCH_SIZE', 100)))
        
        # Métricas
        self.config.setdefault('metrics_enabled', os.environ.get('METRICS_ENABLED', 'true').lower() == 'true')
        self.config.setdefault('metrics_port', int(os.environ.get('METRICS_PORT', 8080)))
    
    def _initialize_redis(self):
        """Inicializa conexión a Redis"""
        try:
            client = redis.Redis(
                host=self.config['redis_host'],
                port=self.config['redis_port'],
                password=self.config['redis_password'],
                decode_responses=True
            )
            # Verificar conexión
            client.ping()
            logger.info(f"Conexión a Redis establecida: {self.config['redis_host']}:{self.config['redis_port']}")
            return client
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Error al conectar a Redis: {str(e)}")
            logger.warning("Utilizando modo fallback sin Redis")
            return None
    
    def _start_workers(self):
        """Inicia threads de trabajo"""
        # Thread para procesar métricas
        metrics_thread = threading.Thread(target=self._process_metrics_queue)
        metrics_thread.daemon = True
        self.threads.append(metrics_thread)
        metrics_thread.start()
        
        # Thread para actualizar perfiles
        profile_thread = threading.Thread(target=self._update_profiles_periodically)
        profile_thread.daemon = True
        self.threads.append(profile_thread)
        profile_thread.start()
        
        logger.info(f"Workers iniciados: {len(self.threads)} threads")
    
    def _start_metrics_server(self):
        """Inicia servidor HTTP para métricas Prometheus"""
        if self.config['metrics_enabled']:
            try:
                start_http_server(self.config['metrics_port'])
                logger.info(f"Servidor de métricas iniciado en puerto {self.config['metrics_port']}")
            except Exception as e:
                logger.error(f"Error al iniciar servidor de métricas: {str(e)}")
    
    def _process_metrics_queue(self):
        """Procesa cola de métricas desde Redis"""
        if not self.redis_client:
            logger.warning("Redis no disponible, procesamiento de cola deshabilitado")
            return
        
        metrics_queue = "metrics:queue"
        batch_size = self.config['metrics_batch_size']
        
        while self.running:
            try:
                # Procesar métricas en lotes
                batch = []
                
                # Obtener hasta batch_size elementos de la cola
                for _ in range(batch_size):
                    # BLPOP con timeout para no bloquear indefinidamente
                    result = self.redis_client.blpop([metrics_queue], timeout=1)
                    if not result:
                        break
                    
                    # Extraer datos
                    _, metrics_data = result
                    
                    try:
                        # Parsear datos de métricas
                        metrics = json.loads(metrics_data)
                        batch.append(metrics)
                    except json.JSONDecodeError:
                        logger.error(f"Error al parsear métricas: {metrics_data}")
                
                # Procesar lote si hay elementos
                if batch:
                    self._process_metrics_batch(batch)
                else:
                    # Esperar un poco si no hay datos
                    time.sleep(self.config['metrics_process_interval'])
                    
            except Exception as e:
                logger.error(f"Error en procesamiento de cola de métricas: {str(e)}")
                time.sleep(5)  # Esperar antes de reintentar
    
    def _process_metrics_batch(self, metrics_batch):
        """
        Procesa un lote de métricas
        
        Args:
            metrics_batch: Lista de datos de métricas
        """
        start_time = time.time()
        processed = 0
        
        try:
            for metrics in metrics_batch:
                # Extraer información esencial
                service_id = metrics.get('service_id')
                timestamp = metrics.get('timestamp')
                
                if not service_id:
                    logger.warning("Métricas sin service_id, ignorando")
                    continue
                
                # Filtrar campos no numéricos o especiales
                filtered_metrics = {}
                for k, v in metrics.items():
                    if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float)):
                        filtered_metrics[k] = v
                
                # Añadir al perfilador de servicios
                self.service_profiler.add_metrics_data(service_id, filtered_metrics, timestamp)
                processed += 1
            
            # Registrar métricas de rendimiento
            process_time = time.time() - start_time
            logger.debug(f"Procesadas {processed} métricas en {process_time:.3f}s")
            
            # Actualizar métricas Prometheus
            if self.config['metrics_enabled']:
                self.metrics.system_health.set(1.0)  # Sistema saludable
                
        except Exception as e:
            logger.error(f"Error al procesar lote de métricas: {str(e)}")
    
    def _update_profiles_periodically(self):
        """Actualiza perfiles de servicio periódicamente"""
        update_interval = self.config['profile_update_interval']
        
        while self.running:
            try:
                # Obtener servicios con perfiles existentes
                profiles = self.service_profiler.service_profiles
                
                if profiles:
                    logger.info(f"Actualizando perfiles para {len(profiles)} servicios")
                    
                    for service_id in profiles:
                        try:
                            # Actualizar perfil
                            self.service_profiler.update_service_profile(service_id)
                            logger.info(f"Perfil actualizado para {service_id}")
                            
                            # Pequeña pausa entre actualizaciones
                            time.sleep(1)
                            
                        except Exception as e:
                            logger.error(f"Error al actualizar perfil para {service_id}: {str(e)}")
                
                # Esperar hasta próxima actualización
                time.sleep(update_interval)
                
            except Exception as e:
                logger.error(f"Error en actualización periódica de perfiles: {str(e)}")
                time.sleep(60)  # Esperar antes de reintentar
    
    def process_metrics(self, metrics):
        """
        Procesa métricas directamente (sin Redis)
        
        Args:
            metrics: Datos de métricas
        """
        try:
            # Extraer información esencial
            service_id = metrics.get('service_id')
            timestamp = metrics.get('timestamp', datetime.now().isoformat())
            
            if not service_id:
                logger.warning("Métricas sin service_id, ignorando")
                return False
            
            # Filtrar campos no numéricos o especiales
            filtered_metrics = {}
            for k, v in metrics.items():
                if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float)):
                    filtered_metrics[k] = v
            
            # Añadir al perfilador de servicios
            self.service_profiler.add_metrics_data(service_id, filtered_metrics, timestamp)
            
            # Si hay Redis, encolar para procesamiento asíncrono
            if self.redis_client:
                try:
                    metrics_queue = "metrics:queue"
                    metrics_data = json.dumps(metrics)
                    self.redis_client.rpush(metrics_queue, metrics_data)
                except Exception as e:
                    logger.error(f"Error al encolar métricas en Redis: {str(e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error al procesar métricas: {str(e)}")
            return False
    
    def get_profile(self, service_id):
        """
        Obtiene perfil de un servicio
        
        Args:
            service_id: ID del servicio
            
        Returns:
            Dict: Perfil del servicio
        """
        return self.service_profiler.get_service_profile(service_id)
    
    def get_threshold_recommendations(self, service_id):
        """
        Obtiene recomendaciones de umbrales para un servicio
        
        Args:
            service_id: ID del servicio
            
        Returns:
            Dict: Recomendaciones de umbrales
        """
        return self.service_profiler.get_threshold_recommendations(service_id)
    
    def detect_anomaly(self, service_id, metrics):
        """
        Detecta anomalías basadas en el perfil del servicio
        
        Args:
            service_id: ID del servicio
            metrics: Métricas actuales
            
        Returns:
            Tuple (is_anomaly, anomaly_score, details)
        """
        return self.service_profiler.detect_anomaly(service_id, metrics)
    
    def stop(self):
        """Detiene el servicio"""
        self.running = False
        
        # Esperar a que terminen los threads
        for thread in self.threads:
            if thread.is_alive():
                thread.join(timeout=5)
        
        logger.info("Servicio detenido")

# Para ejecución directa
if __name__ == "__main__":
    # Obtener configuración de variables de entorno
    config = {
        'redis_host': os.environ.get('REDIS_HOST', 'localhost'),
        'redis_port': int(os.environ.get('REDIS_PORT', 6379)),
        'redis_password': os.environ.get('REDIS_PASSWORD', ''),
        'profiles_dir': os.environ.get('PROFILES_DIR', './data/profiles'),
        'models_dir': os.environ.get('MODELS_DIR', './models/profiles'),
        'metrics_enabled': os.environ.get('METRICS_ENABLED', 'true').lower() == 'true',
        'metrics_port': int(os.environ.get('METRICS_PORT', 8080))
    }
    
    # Iniciar servicio
    service = ServiceProfilerService(config)
    
    # Mantener ejecución
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Recibida señal de interrupción, deteniendo servicio...")
        service.stop()