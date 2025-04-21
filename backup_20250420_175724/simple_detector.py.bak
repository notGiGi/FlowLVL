# -*- coding: utf-8 -*-
import numpy as np
import json
import logging
import os
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("anomaly_detector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('simple_detector')

class SimpleAnomalyDetector:
    """Detector de anomalías simplificado para prueba real"""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Parámetros de configuración
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.7)
        self.min_history_points = self.config.get('min_history_points', 5)
        
        # Directorio para almacenar datos
        self.data_dir = self.config.get('data_dir', './data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Historial de métricas por servicio
        self.metrics_history = {}
        
        # Umbrales por servicio
        self.thresholds = self.load_thresholds()
        
        # Definiciones de patrones de anomalía
        self.anomaly_patterns = {
            "memory_leak": {
                "metrics": ["memory_usage", "gc_collection_time"],
                "conditions": {
                    "memory_usage": lambda x, t: x > t.get("memory_usage", 70),
                    "gc_collection_time": lambda x, t: x > t.get("gc_collection_time", 400)
                },
                "severity": lambda metrics, t: 0.5 + 0.5 * min(1.0, (
                    (metrics.get("memory_usage", 0) / t.get("memory_usage", 70) - 1) * 0.7 +
                    (metrics.get("gc_collection_time", 0) / t.get("gc_collection_time", 400) - 1) * 0.3
                ))
            },
            "db_overload": {
                "metrics": ["active_connections", "connection_wait_time"],
                "conditions": {
                    "active_connections": lambda x, t: x > t.get("active_connections", 80),
                    "connection_wait_time": lambda x, t: x > t.get("connection_wait_time", 200)
                },
                "severity": lambda metrics, t: 0.5 + 0.5 * min(1.0, (
                    (metrics.get("active_connections", 0) / t.get("active_connections", 80) - 1) * 0.6 +
                    (metrics.get("connection_wait_time", 0) / t.get("connection_wait_time", 200) - 1) * 0.4
                ))
            },
            "high_cpu": {
                "metrics": ["cpu_usage"],
                "conditions": {
                    "cpu_usage": lambda x, t: x > t.get("cpu_usage", 80)
                },
                "severity": lambda metrics, t: 0.5 + 0.5 * min(1.0, 
                    (metrics.get("cpu_usage", 0) / t.get("cpu_usage", 80) - 1)
                )
            },
            "redis_fragmentation": {
                "metrics": ["memory_fragmentation_ratio", "hit_rate"],
                "conditions": {
                    "memory_fragmentation_ratio": lambda x, t: x > t.get("memory_fragmentation_ratio", 1.5),
                    "hit_rate": lambda x, t: x < t.get("hit_rate", 80)
                },
                "severity": lambda metrics, t: 0.5 + 0.5 * min(1.0, (
                    (metrics.get("memory_fragmentation_ratio", 1) / t.get("memory_fragmentation_ratio", 1.5) - 1) * 0.7 +
                    (1 - (metrics.get("hit_rate", 100) / t.get("hit_rate", 80))) * 0.3
                ))
            }
        }
        
        logger.info("Detector de anomalías simple inicializado")
    
    def load_thresholds(self):
        """Carga umbrales desde archivo"""
        threshold_file = os.path.join(self.data_dir, 'thresholds.json')
        
        default_thresholds = {
            "default": {
                "memory_usage": 70,
                "cpu_usage": 80,
                "gc_collection_time": 400,
                "active_connections": 80,
                "connection_wait_time": 200,
                "memory_fragmentation_ratio": 1.5,
                "hit_rate": 80
            }
        }
        
        try:
            if os.path.exists(threshold_file):
                with open(threshold_file, 'r') as f:
                    thresholds = json.load(f)
                logger.info(f"Umbrales cargados desde {threshold_file}")
                return thresholds
            else:
                return default_thresholds
        except Exception as e:
            logger.error(f"Error al cargar umbrales: {str(e)}")
            return default_thresholds
    
    def save_thresholds(self):
        """Guarda umbrales en archivo"""
        threshold_file = os.path.join(self.data_dir, 'thresholds.json')
        
        try:
            with open(threshold_file, 'w') as f:
                json.dump(self.thresholds, f, indent=2)
            logger.info(f"Umbrales guardados en {threshold_file}")
        except Exception as e:
            logger.error(f"Error al guardar umbrales: {str(e)}")
    
    def add_metric_point(self, service_id, metrics):
        """Añade un punto de métricas al historial"""
        try:
            if service_id not in self.metrics_history:
                self.metrics_history[service_id] = []
            
            # Filtrar solo campos numéricos
            numeric_metrics = {}
            for key, value in metrics.items():
                if key not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                    numeric_metrics[key] = value
            
            # Añadir timestamp si no existe
            if 'timestamp' not in metrics:
                metrics['timestamp'] = datetime.now().isoformat()
            
            # Guardar punto completo (con valores no numéricos)
            self.metrics_history[service_id].append(metrics)
            
            # Limitar tamaño del historial
            max_history = self.config.get('max_history_points', 100)
            if len(self.metrics_history[service_id]) > max_history:
                self.metrics_history[service_id] = self.metrics_history[service_id][-max_history:]
            
            # Actualizar umbrales si hay suficientes puntos
            if len(self.metrics_history[service_id]) >= self.min_history_points:
                self.update_thresholds(service_id)
                
            return True
            
        except Exception as e:
            logger.error(f"Error al añadir punto de métrica: {str(e)}")
            return False
    
    def update_thresholds(self, service_id):
        """Actualiza umbrales basados en el historial"""
        try:
            if service_id not in self.metrics_history or len(self.metrics_history[service_id]) < self.min_history_points:
                return
            
            # Inicializar diccionario de umbrales si no existe
            if service_id not in self.thresholds:
                # Copiar umbrales por defecto
                self.thresholds[service_id] = self.thresholds.get('default', {}).copy()
            
            # Extraer valores numéricos de cada métrica
            metrics_values = {}
            for point in self.metrics_history[service_id]:
                for key, value in point.items():
                    if key not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                        if key not in metrics_values:
                            metrics_values[key] = []
                        metrics_values[key].append(value)
            
            # Calcular umbrales para cada métrica
            for metric, values in metrics_values.items():
                if len(values) >= self.min_history_points:
                    if metric == 'hit_rate':
                        # Para hit_rate, valores más bajos son problemáticos
                        threshold = np.mean(values) - 2 * np.std(values)
                        # Limitar a mínimo 30%
                        threshold = max(30, threshold)
                    else:
                        # Para otras métricas, valores más altos son problemáticos
                        threshold = np.mean(values) + 2 * np.std(values)
                    
                    # Limitar a cambio máximo del 50% para evitar umbrales extremos
                    current = self.thresholds[service_id].get(metric, 0)
                    if current > 0:
                        max_change = current * 0.5
                        threshold = max(current - max_change, min(current + max_change, threshold))
                    
                    # Actualizar umbral
                    self.thresholds[service_id][metric] = threshold
            
            # Guardar umbrales actualizados
            self.save_thresholds()
            
        except Exception as e:
            logger.error(f"Error al actualizar umbrales: {str(e)}")
    
    def detect_anomalies(self, data_point):
        """
        Detecta anomalías en un punto de datos
        
        Args:
            data_point: Diccionario con métricas y metadatos
            
        Returns:
            Tuple (is_anomaly, anomaly_score, details)
        """
        try:
            # Extraer información básica
            service_id = data_point.get('service_id', 'unknown')
            
            # Añadir punto al historial
            self.add_metric_point(service_id, data_point)
            
            # Obtener umbrales para este servicio (o usar default)
            service_thresholds = self.thresholds.get(service_id, self.thresholds.get('default', {}))
            
            # Verificar patrones de anomalía
            detected_patterns = []
            anomaly_score = 0.0
            
            for pattern_name, pattern in self.anomaly_patterns.items():
                # Verificar si tenemos las métricas necesarias
                has_metrics = all(metric in data_point for metric in pattern["metrics"])
                
                if has_metrics:
                    # Verificar condiciones
                    conditions_met = all(
                        condition(data_point.get(metric, 0), service_thresholds) 
                        for metric, condition in pattern["conditions"].items()
                    )
                    
                    if conditions_met:
                        # Calcular severidad
                        severity = pattern["severity"](data_point, service_thresholds)
                        
                        detected_patterns.append({
                            "pattern": pattern_name,
                            "score": severity,
                            "metrics": {m: data_point.get(m) for m in pattern["metrics"] if m in data_point}
                        })
                        
                        # Actualizar score máximo
                        anomaly_score = max(anomaly_score, severity)
            
            # Determinar si hay anomalía
            is_anomaly = anomaly_score >= self.anomaly_threshold
            
            # Generar detalles
            details = {
                "anomaly_type": detected_patterns[0]["pattern"] if detected_patterns else "unknown",
                "detected_patterns": detected_patterns,
                "thresholds": service_thresholds,
                "metrics_analysis": self.analyze_metrics(data_point, service_thresholds)
            }
            
            return is_anomaly, anomaly_score, details
            
        except Exception as e:
            logger.error(f"Error al detectar anomalías: {str(e)}")
            return False, 0.0, {"error": str(e)}
    
    def analyze_metrics(self, data_point, thresholds):
        """Analiza métricas para proporcionar detalles"""
        analysis = {}
        
        for metric, value in data_point.items():
            if metric not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                threshold = thresholds.get(metric)
                
                if threshold:
                    # Determinar estado según tipo de métrica
                    if metric == 'hit_rate':
                        if value < threshold * 0.9:
                            status = 'critical'
                        elif value < threshold:
                            status = 'warning'
                        else:
                            status = 'normal'
                    else:
                        if value > threshold * 1.2:
                            status = 'critical'
                        elif value > threshold:
                            status = 'warning'
                        else:
                            status = 'normal'
                    
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
    
    def get_history(self, service_id, limit=20):
        """Obtiene historial de métricas para un servicio"""
        if service_id in self.metrics_history:
            return self.metrics_history[service_id][-limit:]
        return []
    
    def get_threshold(self, service_id, metric):
        """Obtiene umbral específico"""
        service_thresholds = self.thresholds.get(service_id, self.thresholds.get('default', {}))
        return service_thresholds.get(metric)
    
    def set_threshold(self, service_id, metric, value):
        """Establece umbral manualmente"""
        if service_id not in self.thresholds:
            self.thresholds[service_id] = self.thresholds.get('default', {}).copy()
        
        self.thresholds[service_id][metric] = value
        self.save_thresholds()
        
        return True

# Script principal
if __name__ == "__main__":
    detector = SimpleAnomalyDetector()
    
    # Ejemplo de detección
    test_point = {
        "service_id": "test-service",
        "memory_usage": 85,
        "cpu_usage": 90,
        "gc_collection_time": 500
    }
    
    is_anomaly, score, details = detector.detect_anomalies(test_point)
    print(f"Anomalía: {is_anomaly}, Score: {score}")
    print(f"Detalles: {json.dumps(details, indent=2)}")