import time
import logging
from threading import Lock
from prometheus_client import Counter, Gauge, Histogram, Summary, push_to_gateway, CollectorRegistry

logger = logging.getLogger('metrics')

class MetricsCollector:
    _instance = None
    _lock = Lock()
    
    def __new__(cls, *args, **kwargs):
        """Implementar como singleton"""
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(MetricsCollector, cls).__new__(cls)
                cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, config=None):
        """Inicializar métricas de Prometheus"""
        if getattr(self, "_initialized", False):
            return
            
        self.config = config or {}
        self.enabled = self.config.get('metrics_enabled', True)
        self.push_gateway_url = self.config.get('push_gateway', 'pushgateway:9091')
        self.push_interval = self.config.get('push_interval', 15)  # segundos
        
        if not self.enabled:
            logger.info("Sistema de métricas deshabilitado")
            return
            
        try:
            self.registry = CollectorRegistry()
            
            # Definir métricas
            # Anomalías
            self.anomaly_detected = Counter(
                'predictive_anomaly_detected_total',
                'Número total de anomalías detectadas',
                ['service_id', 'anomaly_type'],
                registry=self.registry
            )
            
            self.anomaly_score = Gauge(
                'predictive_anomaly_score',
                'Score de anomalía actual',
                ['service_id'],
                registry=self.registry
            )
            
            # Predicciones
            self.prediction_made = Counter(
                'predictive_prediction_made_total',
                'Número total de predicciones realizadas',
                ['service_id', 'prediction_type'],
                registry=self.registry
            )
            
            self.prediction_accuracy = Gauge(
                'predictive_prediction_accuracy',
                'Precisión de las predicciones (0-1)',
                ['service_id', 'prediction_type'],
                registry=self.registry
            )
            
            # Acciones
            self.action_recommended = Counter(
                'predictive_action_recommended_total',
                'Número total de acciones recomendadas',
                ['service_id', 'action_id'],
                registry=self.registry
            )
            
            self.action_executed = Counter(
                'predictive_action_executed_total',
                'Número total de acciones ejecutadas',
                ['service_id', 'action_id', 'result'],
                registry=self.registry
            )
            
            # Rendimiento
            self.detection_time = Histogram(
                'predictive_detection_time_seconds',
                'Tiempo de detección de anomalías',
                ['service_id'],
                registry=self.registry
            )
            
            self.recommendation_time = Histogram(
                'predictive_recommendation_time_seconds',
                'Tiempo de recomendación de acciones',
                ['service_id'],
                registry=self.registry
            )
            
            # Estado del sistema
            self.system_health = Gauge(
                'predictive_system_health',
                'Estado de salud del sistema (0-1)',
                registry=self.registry
            )
            
            self._initialized = True
            logger.info("Sistema de métricas inicializado")
            
        except Exception as e:
            logger.error(f"Error al inicializar sistema de métricas: {str(e)}")
            self.enabled = False
    
    def push_metrics(self, job_name='predictive_maintenance'):
        """Envía métricas al Push Gateway de Prometheus"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return False
        
        try:
            push_to_gateway(self.push_gateway_url, job=job_name, registry=self.registry)
            return True
        except Exception as e:
            logger.warning(f"Error al enviar métricas a {self.push_gateway_url}: {str(e)}")
            return False
    
    def record_anomaly(self, service_id, is_anomaly, anomaly_score, anomaly_type='unknown'):
        """Registra una detección de anomalía"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return
        
        try:
            # Actualizar score de anomalía
            self.anomaly_score.labels(service_id=service_id).set(anomaly_score)
            
            # Incrementar contador si es anomalía
            if is_anomaly:
                self.anomaly_detected.labels(
                    service_id=service_id,
                    anomaly_type=anomaly_type
                ).inc()
        except Exception as e:
            logger.warning(f"Error al registrar métricas de anomalía: {str(e)}")
    
    def time_detection(self, service_id):
        """Timer para medir tiempo de detección"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return TimerDummy()
        
        return TimerMetric(self.detection_time.labels(service_id=service_id))
    
    def time_recommendation(self, service_id):
        """Timer para medir tiempo de recomendación"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return TimerDummy()
        
        return TimerMetric(self.recommendation_time.labels(service_id=service_id))
    
    def record_action_recommendation(self, service_id, action_id):
        """Registra una recomendación de acción"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return
        
        try:
            self.action_recommended.labels(
                service_id=service_id,
                action_id=action_id
            ).inc()
        except Exception as e:
            logger.warning(f"Error al registrar métrica de recomendación: {str(e)}")
    
    def record_action_execution(self, service_id, action_id, success):
        """Registra una ejecución de acción"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return
        
        try:
            self.action_executed.labels(
                service_id=service_id,
                action_id=action_id,
                result='success' if success else 'failure'
            ).inc()
        except Exception as e:
            logger.warning(f"Error al registrar métrica de ejecución: {str(e)}")
    
    def update_system_health(self, health_score):
        """Actualiza el estado de salud del sistema"""
        if not self.enabled or not getattr(self, "_initialized", False):
            return
        
        try:
            self.system_health.set(health_score)
        except Exception as e:
            logger.warning(f"Error al actualizar métrica de salud: {str(e)}")


class TimerMetric:
    """Utilidad para medir tiempo con context manager"""
    
    def __init__(self, histogram):
        self.histogram = histogram
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is not None:
            self.histogram.observe(time.time() - self.start_time)


class TimerDummy:
    """Timer dummy cuando las métricas están deshabilitadas"""
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass