import numpy as np
import pandas as pd
import logging
import json
import os
from datetime import datetime
import traceback
from concurrent.futures import ThreadPoolExecutor

# Importar componentes nuevos
from utils.retry import retry_with_backoff
from utils.metrics import MetricsCollector
from monitoring.service_profiler import ServiceProfiler

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector')

class ImprovedAnomalyDetector:
    """
    Detector de anomalías mejorado con capacidades de adaptación dinámica a cada servicio,
    tolerancia a fallos y procesamiento concurrente.
    """
    
    def __init__(self, config=None):
        """
        Inicializa el detector de anomalías mejorado
        
        Args:
            config: Configuración opcional
        """
        self.config = config or {}
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.6)
        
        # Inicializar perfilador de servicios
        self.service_profiler = ServiceProfiler(config=self.config)
        
        # Inicializar colector de métricas
        self.metrics = MetricsCollector(config=self.config)
        
        # Caché para resultados recientes
        self.recent_results = {}
        
        # Configuración de concurrencia
        self.max_workers = self.config.get('max_workers', 4)
        self.executor = ThreadPoolExecutor(max_workers=self.max_workers)
        
        # Mapa de tipos de anomalía por patrones de métricas
        self.anomaly_type_patterns = {
            "memory_leak": ["memory_usage", "gc_collection_time"],
            "db_overload": ["active_connections", "connection_wait_time"],
            "memory_fragmentation": ["memory_fragmentation_ratio", "hit_rate"],
            "high_cpu": ["cpu_usage", "cpu_throttling"],
            "disk_space": ["disk_usage", "iops"],
            "network_saturation": ["network_in", "network_out", "packet_loss"],
            "response_time": ["latency", "response_time_ms", "processing_time"]
        }
        
        logger.info("Detector de anomalías mejorado inicializado")
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def detect_anomalies(self, data):
        """
        Detecta anomalías en los datos proporcionados con tolerancia a fallos
        
        Args:
            data: Diccionario con métricas y metadatos del servicio
            
        Returns:
            Tuple (is_anomaly, anomaly_score, details)
        """
        try:
            start_time = datetime.now()
            
            # Extraer información clave
            service_id = data.get('service_id', 'unknown_service')
            timestamp = data.get('timestamp', datetime.now().isoformat())
            
            # Extraer métricas (excluyendo campos especiales)
            metrics = {k: v for k, v in data.items() 
                      if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float, bool))}
            
            # Medir tiempo de detección
            with self.metrics.time_detection(service_id):
                # Detectar anomalía con el perfilador
                is_anomaly, anomaly_score, profile_details = self.service_profiler.detect_anomaly(
                    service_id, metrics
                )
                
                # Determinar tipo de anomalía
                anomaly_type = self._identify_anomaly_type(metrics)
                
                # Registrar métrica
                self.metrics.record_anomaly(
                    service_id=service_id,
                    is_anomaly=is_anomaly,
                    anomaly_score=anomaly_score,
                    anomaly_type=anomaly_type
                )
                
                # Construir detalles completos
                details = {
                    "anomaly_type": anomaly_type,
                    "anomaly_score": anomaly_score,
                    "threshold": self.anomaly_threshold,
                    "metrics": metrics,
                    "profile_details": profile_details,
                    "detection_time_ms": (datetime.now() - start_time).total_seconds() * 1000
                }
                
                # Guardar en caché de resultados recientes
                self.recent_results[service_id] = {
                    "timestamp": timestamp,
                    "is_anomaly": is_anomaly,
                    "anomaly_score": anomaly_score,
                    "anomaly_type": anomaly_type
                }
                
                # Registrar información
                if is_anomaly:
                    logger.info(f"Anomalía detectada en {service_id} con score {anomaly_score:.3f}, tipo: {anomaly_type}")
                else:
                    logger.debug(f"No se detectó anomalía en {service_id} (score: {anomaly_score:.3f})")
                
                # Enviar métricas periódicamente
                self.metrics.push_metrics()
                
                return is_anomaly, anomaly_score, details
            
        except Exception as e:
            logger.error(f"Error en detect_anomalies: {str(e)}")
            logger.error(traceback.format_exc())
            return False, 0.0, {"error": str(e)}
    
    def detect_anomalies_async(self, data, callback=None):
        """
        Versión asíncrona de detect_anomalies para procesamiento en paralelo
        
        Args:
            data: Datos para detección
            callback: Función de callback opcional (recibe resultados)
            
        Returns:
            Future object
        """
        def _callback_wrapper(future):
            try:
                result = future.result()
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"Error en callback de detección asíncrona: {str(e)}")
        
        future = self.executor.submit(self.detect_anomalies, data)
        
        if callback:
            future.add_done_callback(_callback_wrapper)
            
        return future
    
    def _identify_anomaly_type(self, metrics):
        """
        Identifica el tipo de anomalía basado en las métricas disponibles
        
        Args:
            metrics: Diccionario de métricas
            
        Returns:
            String con tipo de anomalía
        """
        best_match = None
        max_match_count = 0
        
        # Buscar el patrón con más coincidencias de métricas
        for anomaly_type, required_metrics in self.anomaly_type_patterns.items():
            match_count = sum(1 for metric in required_metrics if metric in metrics)
            
            # Si hay coincidencia total, devolver inmediatamente
            if match_count == len(required_metrics):
                return anomaly_type
            
            # Si hay coincidencia parcial mejor que la actual
            if match_count > max_match_count and match_count >= 1:
                max_match_count = match_count
                best_match = anomaly_type
        
        return best_match or "unknown"
    
    def get_service_status(self, service_id):
        """
        Obtiene el estado actual de un servicio
        
        Args:
            service_id: ID del servicio
            
        Returns:
            Dict con estado actual
        """
        # Obtener último resultado
        last_result = self.recent_results.get(service_id)
        
        # Obtener perfil
        profile = self.service_profiler.get_service_profile(service_id)
        
        if not last_result:
            return {
                "service_id": service_id,
                "status": "unknown",
                "profile_available": profile is not None
            }
        
        # Determinar estado
        if last_result["is_anomaly"]:
            status = "anomaly"
        else:
            status = "normal"
        
        return {
            "service_id": service_id,
            "status": status,
            "last_updated": last_result["timestamp"],
            "anomaly_score": last_result["anomaly_score"],
            "anomaly_type": last_result.get("anomaly_type", "unknown"),
            "profile_available": profile is not None
        }
    
    def batch_detection(self, data_items):
        """
        Procesa múltiples detecciones en paralelo
        
        Args:
            data_items: Lista de diccionarios con datos para detección
            
        Returns:
            Lista de resultados
        """
        futures = []
        results = []
        
        # Enviar cada item para procesamiento asíncrono
        for data in data_items:
            future = self.detect_anomalies_async(data)
            futures.append(future)
        
        # Recopilar resultados
        for future in futures:
            is_anomaly, score, details = future.result()
            results.append({
                "is_anomaly": is_anomaly,
                "score": score,
                "details": details
            })
        
        return results