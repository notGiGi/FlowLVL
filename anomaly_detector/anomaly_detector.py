# anomaly_detector.py
import numpy as np
import pandas as pd
import logging
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector')

class AdaptiveEnsembleDetector:
    """Detector de anomalías con soporte para múltiples patrones"""
    
    def __init__(self, models_config=None):
        # Pesos para diferentes detectores
        self.model_weights = {"memory_leak": 0.7, "db_overload": 0.7, "memory_fragmentation": 0.7}
        
        # Umbrales por tipo de métrica
        self.thresholds = {
            # Memoria y GC
            "memory_usage": 65.0, 
            "gc_collection_time": 400.0,
            
            # Base de datos
            "active_connections": 85.0,
            "connection_wait_time": 150.0,
            
            # Redis
            "memory_fragmentation_ratio": 2.0,
            "hit_rate": 85.0  # Umbral inverso (por debajo es problemático)
        }
    
    def predict(self, data, threshold=0.65, update_weights=True):
        """Predice anomalías adaptando el enfoque al tipo de datos disponibles"""
        if not isinstance(data, dict):
            return False, 0.0, {}
        
        # Determinar qué tipo de anomalía podría ser
        anomaly_type = self._identify_anomaly_type(data)
        
        # Calcular score según el tipo de anomalía
        if anomaly_type == "memory_leak":
            score = self._detect_memory_leak(data)
        elif anomaly_type == "db_overload":
            score = self._detect_db_overload(data)
        elif anomaly_type == "memory_fragmentation":
            score = self._detect_memory_fragmentation(data)
        else:
            # Enfoque genérico si no se identifica un tipo específico
            score = self._generic_detection(data)
        
        # Determinar si es anomalía
        is_anomaly = score >= threshold
        
        # Crear detalles para diagnóstico
        details = {
            "anomaly_type": anomaly_type,
            "anomaly_score": score,
            "threshold": threshold,
            "metrics_analysis": self._analyze_metrics(data, anomaly_type)
        }
        
        return is_anomaly, score, details
    
    def _identify_anomaly_type(self, data):
        """Identifica qué tipo de anomalía podría estar presente según las métricas"""
        # Comprobar si hay métricas de leak de memoria
        if 'memory_usage' in data and 'gc_collection_time' in data:
            return "memory_leak"
        
        # Comprobar si hay métricas de sobrecarga de BD
        if 'active_connections' in data and 'connection_wait_time' in data:
            return "db_overload"
        
        # Comprobar si hay métricas de fragmentación de memoria
        if 'memory_fragmentation_ratio' in data and 'hit_rate' in data:
            return "memory_fragmentation"
        
        # Tipo general si no se puede identificar
        return "general"
    
    def _detect_memory_leak(self, data):
        """Detecta leak de memoria basado en uso de memoria y tiempo de GC"""
        memory = data.get('memory_usage', 0)
        gc_time = data.get('gc_collection_time', 0)
        
        # Calcular scores normalizados
        memory_factor = max(0, min(1, (memory - 55) / 30))  # 55-85% rango
        gc_factor = max(0, min(1, (gc_time - 300) / 500))   # 300-800ms rango
        
        # Combinar con peso
        return 0.6 * memory_factor + 0.4 * gc_factor
    
    def _detect_db_overload(self, data):
        """Detecta sobrecarga de base de datos"""
        connections = data.get('active_connections', 0)
        wait_time = data.get('connection_wait_time', 0)
        
        # Calcular scores normalizados con umbrales más bajos
        conn_factor = max(0, min(1, (connections - 70) / 50))  # 70-120 conexiones
        wait_factor = max(0, min(1, (wait_time - 100) / 300))  # 100-400ms
        
        # Añadir factor combinado (conexiones altas Y tiempo alto)
        combined_factor = 0
        if connections > 80 and wait_time > 200:
            combined_factor = 0.3
        
        # Combinar con pesos
        return 0.5 * conn_factor + 0.3 * wait_factor + combined_factor
    
    def _detect_memory_fragmentation(self, data):
        """Detecta fragmentación de memoria en Redis"""
        frag_ratio = data.get('memory_fragmentation_ratio', 0)
        hit_rate = data.get('hit_rate', 100)
        
        # Calcular scores normalizados
        # Fragmentación alta es problemática (>2.0)
        frag_factor = max(0, min(1, (frag_ratio - 1.5) / 3.0))  # 1.5-4.5 rango
        
        # Hit rate baja es problemática (<85%)
        hit_factor = max(0, min(1, (90 - hit_rate) / 30))  # 90-60% rango (invertido)
        
        # Ponderar más la fragmentación
        return 0.7 * frag_factor + 0.3 * hit_factor
    
    def _generic_detection(self, data):
        """Detección genérica basada en umbrales"""
        total_score = 0.0
        metrics_count = 0
        
        # Comprobar cada métrica contra su umbral
        for metric, value in data.items():
            if not isinstance(value, (int, float)) or metric == 'timestamp':
                continue
                
            metrics_count += 1
            
            # Aplicar umbrales específicos si existen
            if metric in self.thresholds:
                threshold = self.thresholds[metric]
                if metric == 'hit_rate':  # Caso especial (inverso)
                    score = max(0, min(1, (threshold - value) / threshold))
                else:
                    score = max(0, min(1, (value - threshold * 0.8) / (threshold * 0.4)))
                total_score += score
            # Para métricas sin umbral específico
            else:
                # Asumir que valores altos pueden ser problemáticos
                if value > 80:  # Umbral genérico
                    score = (value - 80) / 20  # 80-100 rango
                    total_score += score
        
        return total_score / max(1, metrics_count)
    
    def _analyze_metrics(self, data, anomaly_type):
        """Analiza las métricas para proporcionar contexto detallado"""
        analysis = {}
        
        if anomaly_type == "memory_leak":
            metrics_to_check = ['memory_usage', 'gc_collection_time']
        elif anomaly_type == "db_overload":
            metrics_to_check = ['active_connections', 'connection_wait_time']
        elif anomaly_type == "memory_fragmentation":
            metrics_to_check = ['memory_fragmentation_ratio', 'hit_rate']
        else:
            metrics_to_check = list(data.keys())
        
        for metric in metrics_to_check:
            if metric in data and isinstance(data[metric], (int, float)):
                value = data[metric]
                status = 'normal'
                
                # Verificar contra umbral si existe
                if metric in self.thresholds:
                    threshold = self.thresholds[metric]
                    
                    # Caso especial para hit_rate (inverso)
                    if metric == 'hit_rate':
                        if value < threshold * 0.9:
                            status = 'critical'
                        elif value < threshold:
                            status = 'warning'
                    else:
                        if value > threshold * 1.2:
                            status = 'critical'
                        elif value > threshold:
                            status = 'warning'
                    
                    analysis[metric] = {
                        'value': value,
                        'threshold': threshold,
                        'status': status
                    }
                else:
                    analysis[metric] = {
                        'value': value,
                        'status': 'unknown'
                    }
        
        return analysis

class AnomalyDetector:
    """Detector de anomalías principal"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.65)  # Umbral para considerar anomalía
        self.ensemble_detector = AdaptiveEnsembleDetector()
        logger.info("Detector de anomalías (simplificado) inicializado")
    
    def detect_anomalies(self, data):
        """Detecta anomalías en los datos proporcionados"""
        try:
            # Extraer métricas clave para análisis
            metrics = {}
            if isinstance(data, dict):
                metrics = data
            
            # Detectar anomalías usando el ensemble
            is_anomaly, anomaly_score, details = self.ensemble_detector.predict(
                metrics, threshold=self.anomaly_threshold
            )
            
            if is_anomaly:
                logger.info(f"Anomalía detectada con score {anomaly_score:.3f}")
            
            return is_anomaly, anomaly_score, details
            
        except Exception as e:
            logger.error(f"Error al detectar anomalías: {str(e)}")
            return False, 0, {"error": str(e)}