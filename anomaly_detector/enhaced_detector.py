# anomaly_detector/enhanced_detector.py

import numpy as np
import pandas as pd
import logging
import json
import time
from datetime import datetime, timedelta
from collections import defaultdict
from scipy.stats import zscore
import joblib
import os

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('anomaly_detector')

class EnhancedAnomalyDetector:
    """Detector de anomalías mejorado con clasificación específica y umbrales adaptativos"""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Directorio para modelos y configuración
        self.models_dir = self.config.get('models_dir', './models/anomaly')
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Cargar configuración de umbrales o usar predeterminados
        self.thresholds_file = os.path.join(self.models_dir, 'adaptive_thresholds.json')
        self.load_thresholds()
        
        # Historial para cálculo de umbrales adaptativos
        self.metric_history = defaultdict(list)
        self.max_history_points = self.config.get('max_history_points', 1000)
        
        # Configuración de ventanas temporales para detección contextual
        self.time_windows = {
            'high_traffic': [(8, 12), (14, 18)],  # Horas pico (8-12h, 14-18h)
            'low_traffic': [(0, 7), (19, 23)]     # Horas valle (0-7h, 19-23h)
        }
        
        # Tipos específicos de anomalías con sus patrones asociados
        self.anomaly_patterns = {
            # Patrones para bases de datos
            "db_connection_overflow": {
                "metrics": ["active_connections", "connection_wait_time"],
                "conditions": {
                    "active_connections": lambda x: x > self.get_threshold("active_connections"),
                    "connection_wait_time": lambda x: x > self.get_threshold("connection_wait_time")
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, (
                    (metrics.get("active_connections", 0) / self.get_threshold("active_connections") - 1) * 0.6 +
                    (metrics.get("connection_wait_time", 0) / self.get_threshold("connection_wait_time") - 1) * 0.4
                )))
            },
            "db_slow_queries": {
                "metrics": ["query_execution_time_avg", "cpu_usage"],
                "conditions": {
                    "query_execution_time_avg": lambda x: x > self.get_threshold("query_execution_time_avg"),
                    "cpu_usage": lambda x: x > self.get_threshold("cpu_usage") * 0.8
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, 
                    metrics.get("query_execution_time_avg", 0) / self.get_threshold("query_execution_time_avg") - 1
                ))
            },
            "db_disk_saturation": {
                "metrics": ["disk_usage_percent", "io_wait"],
                "conditions": {
                    "disk_usage_percent": lambda x: x > self.get_threshold("disk_usage_percent"),
                    "io_wait": lambda x: x > self.get_threshold("io_wait")
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, 
                    metrics.get("disk_usage_percent", 0) / self.get_threshold("disk_usage_percent") - 1
                ))
            },
            
            # Patrones para servicios web/aplicaciones
            "memory_leak": {
                "metrics": ["memory_usage", "gc_collection_time"],
                "conditions": {
                    "memory_usage": lambda x: x > self.get_threshold("memory_usage"),
                    "gc_collection_time": lambda x: x > self.get_threshold("gc_collection_time")
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, (
                    (metrics.get("memory_usage", 0) / self.get_threshold("memory_usage") - 1) * 0.7 +
                    (metrics.get("gc_collection_time", 0) / self.get_threshold("gc_collection_time") - 1) * 0.3
                )))
            },
            "high_latency": {
                "metrics": ["response_time_ms", "request_rate", "error_rate"],
                "conditions": {
                    "response_time_ms": lambda x: x > self.get_threshold("response_time_ms"),
                    "error_rate": lambda x: x > self.get_threshold("error_rate")
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, (
                    (metrics.get("response_time_ms", 0) / self.get_threshold("response_time_ms") - 1) * 0.8 +
                    (metrics.get("error_rate", 0) / max(0.01, self.get_threshold("error_rate")) - 1) * 0.2
                )))
            },
            "service_degradation": {
                "metrics": ["error_rate", "request_rate", "cpu_usage"],
                "conditions": {
                    "error_rate": lambda x: x > self.get_threshold("error_rate") * 0.7,
                    "cpu_usage": lambda x: x > self.get_threshold("cpu_usage") * 0.9
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, 
                    metrics.get("error_rate", 0) / max(0.01, self.get_threshold("error_rate")) - 1
                ))
            },
            
            # Patrones para caché/Redis
            "cache_fragmentation": {
                "metrics": ["memory_fragmentation_ratio", "hit_rate"],
                "conditions": {
                    "memory_fragmentation_ratio": lambda x: x > self.get_threshold("memory_fragmentation_ratio"),
                    "hit_rate": lambda x: x < self.get_threshold("hit_rate")
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, (
                    (metrics.get("memory_fragmentation_ratio", 1) / self.get_threshold("memory_fragmentation_ratio") - 1) * 0.7 +
                    (1 - (metrics.get("hit_rate", 100) / self.get_threshold("hit_rate"))) * 0.3
                )))
            },
            "cache_evictions": {
                "metrics": ["eviction_rate", "memory_usage"],
                "conditions": {
                    "eviction_rate": lambda x: x > self.get_threshold("eviction_rate"),
                    "memory_usage": lambda x: x > self.get_threshold("memory_usage") * 0.85
                },
                "severity_func": lambda metrics: 0.3 + (0.7 * min(1.0, 
                    metrics.get("eviction_rate", 0) / self.get_threshold("eviction_rate") - 1
                ))
            }
        }
        
        # Historial de anomalías para análisis
        self.anomaly_history = defaultdict(list)
        
        logger.info(f"Detector de anomalías mejorado inicializado con {len(self.anomaly_patterns)} patrones")
    
    def load_thresholds(self):
        """Carga umbrales adaptativos desde archivo o usa predeterminados"""
        default_thresholds = {
            # Umbrales para bases de datos
            "active_connections": 75,
            "connection_wait_time": 150,
            "query_execution_time_avg": 500,
            "io_wait": 25,
            
            # Umbrales para servicios web/aplicaciones
            "memory_usage": 70,
            "gc_collection_time": 450,
            "response_time_ms": 300,
            "error_rate": 0.05,
            "cpu_usage": 80,
            
            # Umbrales para caché/Redis
            "memory_fragmentation_ratio": 2.0,
            "hit_rate": 85,
            "eviction_rate": 100,
            
            # Umbrales generales
            "disk_usage_percent": 85
        }
        
        # Modificadores contextuales para diferentes ventanas temporales
        self.threshold_modifiers = {
            'high_traffic': {
                "active_connections": 1.3,      # 30% más alto en horas pico
                "connection_wait_time": 1.2,    # 20% más alto en horas pico
                "response_time_ms": 1.25,       # 25% más alto en horas pico
                "cpu_usage": 1.15               # 15% más alto en horas pico
            },
            'low_traffic': {
                "active_connections": 0.7,      # 30% más bajo en horas valle
                "connection_wait_time": 0.8,    # 20% más bajo en horas valle
                "response_time_ms": 0.8,        # 20% más bajo en horas valle
                "cpu_usage": 0.85               # 15% más bajo en horas valle
            }
        }
        
        try:
            if os.path.exists(self.thresholds_file):
                with open(self.thresholds_file, 'r') as f:
                    self.thresholds = json.load(f)
                logger.info(f"Umbrales adaptativos cargados desde {self.thresholds_file}")
            else:
                self.thresholds = default_thresholds
                logger.info("Usando umbrales predeterminados")
        except Exception as e:
            logger.error(f"Error al cargar umbrales: {str(e)}")
            self.thresholds = default_thresholds
    
    def save_thresholds(self):
        """Guarda umbrales adaptativos en archivo"""
        try:
            with open(self.thresholds_file, 'w') as f:
                json.dump(self.thresholds, f, indent=2)
            logger.info(f"Umbrales adaptativos guardados en {self.thresholds_file}")
        except Exception as e:
            logger.error(f"Error al guardar umbrales: {str(e)}")
    
    def get_threshold(self, metric_name):
        """Obtiene el umbral para una métrica específica con ajuste contextual por hora"""
        base_threshold = self.thresholds.get(metric_name, 0)
        
        # Obtener hora actual para contexto temporal
        current_hour = datetime.now().hour
        
        # Aplicar modificador según ventana temporal
        modifier = 1.0  # valor predeterminado (sin modificación)
        
        for window_name, time_ranges in self.time_windows.items():
            for start_hour, end_hour in time_ranges:
                if start_hour <= current_hour <= end_hour:
                    # Aplicar modificador si existe para esta métrica
                    window_modifiers = self.threshold_modifiers.get(window_name, {})
                    modifier = window_modifiers.get(metric_name, 1.0)
                    break
        
        return base_threshold * modifier
    
    def update_metric_history(self, metric_name, value):
        """Actualiza el historial de una métrica y recalcula umbrales adaptativos"""
        if not isinstance(value, (int, float)):
            return
        
        # Añadir al historial
        self.metric_history[metric_name].append(value)
        
        # Limitar tamaño del historial
        if len(self.metric_history[metric_name]) > self.max_history_points:
            self.metric_history[metric_name] = self.metric_history[metric_name][-self.max_history_points:]
        
        # Solo recalcular umbral si tenemos suficientes puntos
        if len(self.metric_history[metric_name]) >= 100:
            self.recalculate_threshold(metric_name)
    
    def recalculate_threshold(self, metric_name):
        """Recalcula umbral adaptativo basado en historial de la métrica"""
        values = np.array(self.metric_history[metric_name])
        
        if len(values) < 30:
            return  # necesitamos suficientes datos
        
        # Diferentes estrategias según la métrica
        if metric_name in ["error_rate", "memory_fragmentation_ratio"]:
            # Para métricas donde valores altos son anomalías: media + 2.5*std
            threshold = np.mean(values) + 2.5 * np.std(values)
        elif metric_name in ["hit_rate"]:
            # Para métricas donde valores bajos son anomalías: media - 2*std
            threshold = np.mean(values) - 2 * np.std(values)
        else:
            # Para métricas estándar: percentil 95
            threshold = np.percentile(values, 95)
        
        # Evitar umbrales extremos
        if metric_name in self.thresholds:
            original = self.thresholds[metric_name]
            # Límite de cambio: no más del 40% arriba o 30% abajo del valor original
            threshold = max(min(threshold, original * 1.4), original * 0.7)
        
        # Actualizar umbral
        self.thresholds[metric_name] = threshold
        
        # Guardar umbrales cada cierto número de actualizaciones
        if np.random.random() < 0.1:  # 10% de probabilidad de guardar
            self.save_thresholds()
    
    def detect_anomalies(self, data):
        """Detecta anomalías en los datos con identificación de patrones"""
        if not isinstance(data, dict):
            return False, 0, {"error": "Datos no válidos"}
        
        service_id = data.get('service_id', 'unknown')
        timestamp = data.get('timestamp', datetime.now().isoformat())
        
        # Actualizar historial de métricas
        for key, value in data.items():
            if isinstance(value, (int, float)) and key not in ['timestamp']:
                self.update_metric_history(key, value)
        
        # Verificar cada patrón de anomalía
        detected_patterns = []
        max_score = 0
        
        for pattern_name, pattern in self.anomaly_patterns.items():
            # Verificar si tenemos suficientes métricas para este patrón
            if not all(metric in data for metric in pattern["metrics"]):
                continue
            
            # Verificar condiciones
            conditions_met = all(
                condition(data[metric]) 
                for metric, condition in pattern["conditions"].items() 
                if metric in data
            )
            
            if conditions_met:
                # Calcular score de anomalía
                anomaly_score = pattern["severity_func"](data)
                
                detected_patterns.append({
                    "pattern": pattern_name,
                    "score": anomaly_score,
                    "metrics": {m: data.get(m) for m in pattern["metrics"] if m in data}
                })
                
                max_score = max(max_score, anomaly_score)
        
        # Determinar resultado general
        is_anomaly = max_score >= 0.3  # umbral general
        
        # Si no se detectó ningún patrón específico pero hay métricas anómalas
        if not detected_patterns and any(
            self.is_metric_anomalous(key, value) 
            for key, value in data.items() 
            if isinstance(value, (int, float)) and key not in ['timestamp']
        ):
            # Usar detección genérica
            generic_score = self.calculate_generic_score(data)
            is_anomaly = generic_score >= 0.3
            max_score = generic_score
            
            detected_patterns.append({
                "pattern": "generic_anomaly",
                "score": generic_score,
                "metrics": {k: v for k, v in data.items() if isinstance(v, (int, float)) and k not in ['timestamp']}
            })
        
        # Determinar tipo principal de anomalía
        if detected_patterns:
            detected_patterns.sort(key=lambda x: x["score"], reverse=True)
            primary_anomaly_type = detected_patterns[0]["pattern"]
        else:
            primary_anomaly_type = "none"
        
        # Registrar en historial de anomalías
        if is_anomaly:
            self.anomaly_history[service_id].append({
                "timestamp": timestamp,
                "anomaly_type": primary_anomaly_type,
                "score": max_score,
                "patterns": detected_patterns
            })
            
            # Limitar tamaño del historial
            if len(self.anomaly_history[service_id]) > 100:
                self.anomaly_history[service_id] = self.anomaly_history[service_id][-100:]
            
            logger.info(f"Anomalía detectada en {service_id}: {primary_anomaly_type} con score {max_score:.3f}")
        
        # Preparar resultado detallado
        details = {
            "anomaly_type": primary_anomaly_type,
            "detected_patterns": detected_patterns,
            "threshold": 0.3,
            "metrics_analysis": self.analyze_metrics(data)
        }
        
        return is_anomaly, max_score, details
    
    def is_metric_anomalous(self, metric_name, value):
        """Determina si una métrica individual es anómala"""
        if metric_name not in self.thresholds:
            return False
        
        # Verificar si tenemos suficiente historial
        if len(self.metric_history.get(metric_name, [])) >= 30:
            # Calcular z-score para esta métrica
            values = np.array(self.metric_history[metric_name])
            z = (value - np.mean(values)) / max(np.std(values), 0.001)
            
            # Métricas donde valores altos son anomalías
            if metric_name not in ["hit_rate"]:
                return z > 2.5
            else:
                # Métricas donde valores bajos son anomalías
                return z < -2.5
        else:
            # Comparar con umbral fijo si no hay suficiente historial
            threshold = self.get_threshold(metric_name)
            
            # Métricas donde valores altos son anomalías
            if metric_name not in ["hit_rate"]:
                return value > threshold
            else:
                # Métricas donde valores bajos son anomalías
                return value < threshold
    
    def calculate_generic_score(self, data):
        """Calcula un score de anomalía genérico para métricas que no coinciden con patrones"""
        anomaly_scores = []
        
        for key, value in data.items():
            if not isinstance(value, (int, float)) or key in ['timestamp', 'service_id']:
                continue
                
            if key in self.thresholds:
                threshold = self.get_threshold(key)
                
                # Métricas donde valores bajos son anomalías
                if key in ["hit_rate"]:
                    if value < threshold:
                        # Normalizar: más bajo = más anómalo
                        score = (threshold - value) / threshold
                        anomaly_scores.append(score)
                else:
                    # Métricas donde valores altos son anomalías
                    if value > threshold:
                        # Normalizar: más alto = más anómalo
                        score = (value - threshold) / threshold
                        anomaly_scores.append(score)
        
        # Si no hay métricas anómalas
        if not anomaly_scores:
            return 0
        
        # Calcular score combinado
        return min(0.9, 0.3 + np.mean(anomaly_scores) * 0.7)
    
    def analyze_metrics(self, data):
        """Analiza las métricas para proporcionar contexto detallado"""
        analysis = {}
        
        for key, value in data.items():
            if not isinstance(value, (int, float)) or key in ['timestamp', 'service_id']:
                continue
            
            status = 'normal'
            threshold = self.get_threshold(key) if key in self.thresholds else None
            
            if threshold is not None:
                # Determinar estado para métricas donde valores bajos son anomalías
                if key in ["hit_rate"]:
                    if value < threshold * 0.9:
                        status = 'critical'
                    elif value < threshold:
                        status = 'warning'
                # Determinar estado para métricas donde valores altos son anomalías
                else:
                    if value > threshold * 1.2:
                        status = 'critical'
                    elif value > threshold:
                        status = 'warning'
                
                analysis[key] = {
                    'value': value,
                    'threshold': threshold,
                    'status': status
                }
                
                # Añadir contexto histórico si está disponible
                if key in self.metric_history and len(self.metric_history[key]) >= 5:
                    recent_values = self.metric_history[key][-5:]
                    analysis[key]['trend'] = 'increasing' if value > recent_values[0] else 'decreasing'
                    analysis[key]['recent_avg'] = sum(recent_values) / len(recent_values)
            else:
                analysis[key] = {
                    'value': value,
                    'status': 'unknown'
                }
        
        return analysis
    
    def get_anomaly_history(self, service_id, limit=10):
        """Obtiene historial de anomalías para un servicio"""
        return self.anomaly_history.get(service_id, [])[-limit:]
    
    def get_service_health(self, service_id):
        """Calcula métricas de salud general para un servicio"""
        anomalies = self.anomaly_history.get(service_id, [])
        
        if not anomalies:
            return {"status": "unknown", "anomaly_count": 0}
        
        # Contar anomalías recientes (últimas 24h)
        recent_cutoff = (datetime.now() - timedelta(hours=24)).isoformat()
        recent_anomalies = [a for a in anomalies if a["timestamp"] > recent_cutoff]
        
        # Calcular distribución de tipos
        type_distribution = defaultdict(int)
        for anomaly in recent_anomalies:
            type_distribution[anomaly["anomaly_type"]] += 1
        
        return {
            "status": "healthy" if len(recent_anomalies) == 0 else "degraded" if len(recent_anomalies) < 3 else "critical",
            "anomaly_count": len(recent_anomalies),
            "type_distribution": dict(type_distribution),
            "latest_anomaly": anomalies[-1] if anomalies else None
        }