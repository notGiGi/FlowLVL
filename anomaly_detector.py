# simplified_anomaly_detector.py
import numpy as np
import pandas as pd
import random
import json
import logging

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector')

class AdaptiveEnsembleDetector:
    """Versión simplificada del detector de anomalías"""
    
    def __init__(self, models_config=None):
        self.model_weights = {"isolation_forest": 0.6, "autoencoder": 0.4}
    
    def predict(self, data, threshold=0.75, update_weights=True):
        # Simulamos detección de anomalías
        # Para demo, hacemos que detecte anomalías cuando memory_usage > 70 o gc_collection_time > 600
        memory_usage = data.get('memory_usage', 0) if isinstance(data, dict) else 0
        gc_time = data.get('gc_collection_time', 0) if isinstance(data, dict) else 0
        
        # Calcular score basado en estas métricas
        memory_factor = max(0, min(1, (memory_usage - 60) / 30))  # 60-90% rango
        gc_factor = max(0, min(1, (gc_time - 300) / 500))  # 300-800ms rango
        
        # Combinar factores con peso
        anomaly_score = 0.7 * memory_factor + 0.3 * gc_factor
        is_anomaly = anomaly_score >= threshold
        
        details = {
            "model_contributions": {
                "memory_usage": memory_factor,
                "gc_collection_time": gc_factor
            },
            "threshold": threshold
        }
        
        return is_anomaly, anomaly_score, details

class AnomalyDetector:
    """Detector de anomalías simplificado para pruebas"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.75)
        self.ensemble_detector = AdaptiveEnsembleDetector()
        logger.info("Detector de anomalías (simplificado) inicializado")
    
    def detect_anomalies(self, data):
        """Detecta anomalías en los datos proporcionados"""
        try:
            # Extraer algunas métricas clave para análisis
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
