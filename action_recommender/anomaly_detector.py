# anomaly_detector.py
import numpy as np
import pandas as pd
import logging
from datetime import datetime
import traceback

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector')

class AdaptiveEnsembleDetector:
    """Detector de anomalías con soporte para múltiples patrones,
       con fórmulas ajustadas para diferentes escenarios.
    """
    
    def __init__(self, models_config=None):
        # Pesos para diferentes detectores (pueden ajustarse según relevancia)
        self.model_weights = {"memory_leak": 0.7, "db_overload": 0.7, "memory_fragmentation": 0.7}
        
        # Umbrales y valores base para cada tipo de métrica (ajustados para ser generales)
        self.thresholds = {
            # Para memory leak: se espera que el uso de memoria incremente de manera significativa
            "memory_usage": 55.0,    # Inicio del rango (valor base)
            "gc_collection_time": 300.0,  # Valor base en ms
            
            # Para base de datos: se consideran problemáticas conexiones desde 90 hasta 120 y tiempos de espera desde 200 a 400ms.
            "active_connections": {"base": 90.0, "max": 120.0},
            "connection_wait_time": {"base": 200.0, "max": 400.0},
            
            # Para Redis: se consideran anómalos ratios de fragmentación superiores a 2.0 hasta 4.0, y hit rate inferiores a 80%.
            "memory_fragmentation_ratio": {"base": 2.0, "max": 4.0},
            "hit_rate": {"base": 80.0, "min": 50.0}  # Se espera que el hit rate normal sea alto.
        }
        
        logger.info("AdaptiveEnsembleDetector inicializado con parámetros: %s", self.thresholds)
    
    def predict(self, data, threshold=0.65, update_weights=True):
        """Predice anomalías adaptando el enfoque al tipo de datos disponibles"""
        try:
            if not isinstance(data, dict):
                logger.warning("Datos no son un diccionario: %s", type(data))
                return False, 0.0, {}
            
            anomaly_type = self._identify_anomaly_type(data)
            
            if anomaly_type == "memory_leak":
                score = self._detect_memory_leak(data)
                logger.debug("Detectando memory_leak, score: %.3f", score)
            elif anomaly_type == "db_overload":
                score = self._detect_db_overload(data)
                logger.debug("Detectando db_overload, score: %.3f", score)
            elif anomaly_type == "memory_fragmentation":
                score = self._detect_memory_fragmentation(data)
                logger.debug("Detectando memory_fragmentation, score: %.3f", score)
            else:
                score = self._generic_detection(data)
                logger.debug("Detectando general, score: %.3f", score)
            
            is_anomaly = score >= threshold
            
            details = {
                "anomaly_type": anomaly_type,
                "anomaly_score": score,
                "threshold": threshold,
                "metrics_analysis": self._analyze_metrics(data, anomaly_type)
            }
            
            logger.debug("Resultado detección: is_anomaly=%s, score=%.3f, tipo=%s", 
                        is_anomaly, score, anomaly_type)
            return is_anomaly, score, details
            
        except Exception as e:
            logger.error("Error en predict: %s", str(e))
            logger.error(traceback.format_exc())
            return False, 0.0, {"error": str(e)}
    
    def _identify_anomaly_type(self, data):
        """Identifica qué tipo de anomalía podría estar presente según las métricas"""
        if 'memory_usage' in data and 'gc_collection_time' in data:
            return "memory_leak"
        if 'active_connections' in data and 'connection_wait_time' in data:
            return "db_overload"
        if 'memory_fragmentation_ratio' in data and 'hit_rate' in data:
            return "memory_fragmentation"
        return "general"
    
    def _detect_memory_leak(self, data):
        """Detecta fuga de memoria basado en uso de memoria y tiempo de GC.
           Se utilizan valores base y rangos ajustados.
        """
        memory = float(data.get('memory_usage', 0))
        gc_time = float(data.get('gc_collection_time', 0))
        
        logger.debug("_detect_memory_leak - memory: %.2f, gc_time: %.2f", memory, gc_time)
        
        # Se usa la fórmula original (puede ajustarse según se disponga de datos históricos)
        memory_factor = max(0, min(1, (memory - self.thresholds["memory_usage"]) / 30))
        gc_factor = max(0, min(1, (gc_time - self.thresholds["gc_collection_time"]) / 500))
        
        final_score = 0.6 * memory_factor + 0.4 * gc_factor
        logger.debug("Score final memory_leak: %.3f", final_score)
        return final_score
    
    def _detect_db_overload(self, data):
        """Detecta sobrecarga de base de datos usando un rango general.
           Se asume que las conexiones son problemáticas a partir de un valor base y
           que tiempos de espera altos son relevantes.
        """
        connections = float(data.get('active_connections', 0))
        wait_time = float(data.get('connection_wait_time', 0))
        logger.debug("_detect_db_overload - connections: %.2f, wait_time: %.2f", connections, wait_time)
        
        # Parámetros para conexiones y tiempos (valores configurables y generales)
        base_con = self.thresholds["active_connections"]["base"]
        max_con = self.thresholds["active_connections"]["max"]
        base_wait = self.thresholds["connection_wait_time"]["base"]
        max_wait = self.thresholds["connection_wait_time"]["max"]
        
        conn_factor = max(0, min(1, (connections - base_con) / (max_con - base_con)))
        wait_factor = max(0, min(1, (wait_time - base_wait) / (max_wait - base_wait)))
        
        # Factor combinado si las métricas son muy críticas
        combined_factor = 0
        if connections > (base_con + (max_con - base_con) * 0.5) and wait_time > (base_wait + (max_wait - base_wait) * 0.5):
            combined_factor = 0.3
        
        final_score = 0.5 * conn_factor + 0.3 * wait_factor + combined_factor
        logger.debug("Score final db_overload: %.3f", final_score)
        return final_score
    
    def _detect_memory_fragmentation(self, data):
        """Detecta fragmentación de memoria en Redis usando rangos generales.
           Se considera anómalo un ratio que supere el valor base y un hit rate bajo.
        """
        frag_ratio = float(data.get('memory_fragmentation_ratio', 0))
        hit_rate = float(data.get('hit_rate', 100))
        logger.debug("_detect_memory_fragmentation - frag_ratio: %.2f, hit_rate: %.2f", frag_ratio, hit_rate)
        
        base_frag = self.thresholds["memory_fragmentation_ratio"]["base"]
        max_frag = self.thresholds["memory_fragmentation_ratio"]["max"]
        base_hit = self.thresholds["hit_rate"]["base"]
        
        frag_factor = max(0, min(1, (frag_ratio - base_frag) / (max_frag - base_frag)))
        # Un hit rate inferior al valor base es preocupante; se asume que valores menores generan un factor mayor
        hit_factor = max(0, min(1, (base_hit - hit_rate) / (base_hit - self.thresholds["hit_rate"]["min"])))
        
        final_score = 0.7 * frag_factor + 0.3 * hit_factor
        logger.debug("Score final memory_fragmentation: %.3f", final_score)
        return final_score
    
    def _generic_detection(self, data):
        """Detección genérica basada en umbrales aproximados para métricas desconocidas"""
        total_score = 0.0
        metrics_count = 0
        for metric, value in data.items():
            if not isinstance(value, (int, float)) or metric in ['timestamp', 'service_id']:
                continue
            metrics_count += 1
            if metric in self.thresholds:
                threshold = self.thresholds[metric]
                # Se asume que valores significativamente mayores (o menores, en caso inverso) generan scores
                if isinstance(threshold, dict):
                    score = max(0, min(1, (value - threshold.get("base", 0)) / 50))
                else:
                    score = max(0, min(1, (value - threshold * 0.8) / (threshold * 0.4)))
                logger.debug("Métrica %s: valor=%.2f, score=%.3f", metric, value, score)
                total_score += score
            else:
                if value > 80:
                    score = (value - 80) / 20
                    total_score += score
        final_score = total_score / max(1, metrics_count)
        logger.debug("Score genérico final: %.3f (basado en %d métricas)", final_score, metrics_count)
        return final_score
    
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
                if metric in self.thresholds:
                    if isinstance(self.thresholds[metric], dict):
                        if metric == 'active_connections':
                            if value > self.thresholds[metric]["base"] * 1.2:
                                status = 'critical'
                            elif value > self.thresholds[metric]["base"]:
                                status = 'warning'
                        elif metric == 'connection_wait_time':
                            if value > self.thresholds[metric]["base"] * 1.2:
                                status = 'critical'
                            elif value > self.thresholds[metric]["base"]:
                                status = 'warning'
                        elif metric == 'memory_fragmentation_ratio':
                            if value > self.thresholds[metric]["base"] * 1.2:
                                status = 'critical'
                            elif value > self.thresholds[metric]["base"]:
                                status = 'warning'
                        elif metric == 'hit_rate':
                            if value < self.thresholds[metric]["base"] * 0.9:
                                status = 'critical'
                            elif value < self.thresholds[metric]["base"]:
                                status = 'warning'
                    else:
                        if value > self.thresholds[metric] * 1.2:
                            status = 'critical'
                        elif value > self.thresholds[metric]:
                            status = 'warning'
                    analysis[metric] = {'value': value, 'threshold': self.thresholds[metric], 'status': status}
                else:
                    analysis[metric] = {'value': value, 'status': 'unknown'}
        return analysis

class AnomalyDetector:
    """Detector de anomalías principal que utiliza el AdaptiveEnsembleDetector"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.5)
        self.ensemble_detector = AdaptiveEnsembleDetector()
        logger.info("Detector de anomalías inicializado con umbral %.2f", self.anomaly_threshold)
    
    def detect_anomalies(self, data):
        """Detecta anomalías en los datos proporcionados"""
        try:
            metrics = data.copy() if isinstance(data, dict) else {}
            logger.debug("Detectando anomalías para métricas: %s", metrics)
            is_anomaly, anomaly_score, details = self.ensemble_detector.predict(
                metrics, threshold=self.anomaly_threshold
            )
            if is_anomaly:
                logger.info(f"Anomalía detectada con score {anomaly_score:.3f}")
            return is_anomaly, anomaly_score, details
            
        except Exception as e:
            logger.error("Error al detectar anomalías: %s", str(e))
            logger.error(traceback.format_exc())
            return False, 0, {"error": str(e)}
