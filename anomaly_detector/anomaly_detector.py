#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Anomaly Detector - Sistema predictivo de mantenimiento para sistemas distribuidos
--------------------------------------------------------------------------------
Módulo para detección adaptativa de anomalías mediante ensamblado de modelos.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
import time
from datetime import datetime, timedelta
from collections import deque
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow.keras.models import Model, load_model
from sklearn.metrics import roc_auc_score
from scipy import stats
from scipy.spatial.distance import mahalanobis
import warnings

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('anomaly_detector')

# Suprimir advertencias
warnings.filterwarnings("ignore")

class AdaptiveEnsembleDetector:
    """
    Detector de anomalías con ensamblado adaptativo de múltiples modelos.
    """
    def __init__(self, models_config=None):
        """
        Inicializa el detector de anomalías con ensamblado adaptativo
        
        Args:
            models_config: Lista de configuraciones de modelos a utilizar
        """
        self.models = {}
        self.model_weights = {}
        self.performance_history = {}
        self.default_weight = 1.0
        
        # Cargar modelos si se proporciona configuración
        if models_config:
            self.initialize_models(models_config)
    
    def initialize_models(self, models_config):
        """Inicializa los modelos basados en la configuración proporcionada"""
        for config in models_config:
            model_type = config.get('type')
            model_id = config.get('id')
            model_path = config.get('path')
            
            try:
                if model_type == 'isolation_forest':
                    self.models[model_id] = joblib.load(model_path)
                elif model_type == 'autoencoder':
                    self.models[model_id] = load_model(model_path)
                elif model_type == 'robust_covariance':
                    self.models[model_id] = joblib.load(model_path)
                # Añadir soporte para otros tipos de modelos aquí
                
                # Inicializar peso igual para todos los modelos
                self.model_weights[model_id] = config.get('initial_weight', self.default_weight)
                self.performance_history[model_id] = []
                
                logger.info(f"Modelo {model_id} ({model_type}) cargado correctamente")
            except Exception as e:
                logger.error(f"Error al cargar modelo {model_id}: {str(e)}")
    
    def add_model(self, model_id, model, model_type, initial_weight=1.0):
        """Añade un modelo al ensamble"""
        self.models[model_id] = model
        self.model_weights[model_id] = initial_weight
        self.performance_history[model_id] = []
        logger.info(f"Modelo {model_id} añadido al ensamble con peso {initial_weight}")
    
    def remove_model(self, model_id):
        """Elimina un modelo del ensamble"""
        if model_id in self.models:
            del self.models[model_id]
            del self.model_weights[model_id]
            del self.performance_history[model_id]
            logger.info(f"Modelo {model_id} eliminado del ensamble")
    
    def update_weights(self, feedback_data=None):
        """
        Actualiza los pesos de los modelos basados en su rendimiento reciente
        
        Args:
            feedback_data: Datos de retroalimentación sobre aciertos/fallos
        """
        if not feedback_data or len(self.models) <= 1:
            return
        
        # Actualizar historial de rendimiento
        for model_id, model in self.models.items():
            if model_id in feedback_data:
                self.performance_history[model_id].append(feedback_data[model_id])
                # Mantener solo el historial reciente (últimas 100 muestras)
                if len(self.performance_history[model_id]) > 100:
                    self.performance_history[model_id] = self.performance_history[model_id][-100:]
        
        # Calcular rendimiento reciente para cada modelo
        recent_performance = {}
        for model_id, history in self.performance_history.items():
            if history:
                # Calcular tasa de acierto reciente
                recent_performance[model_id] = sum(history) / len(history)
            else:
                recent_performance[model_id] = 0.5  # Valor neutro si no hay historial
        
        # Normalizar pesos basados en rendimiento
        total_performance = sum(recent_performance.values())
        if total_performance > 0:
            for model_id in self.models:
                # El peso es proporcional al rendimiento relativo
                performance_ratio = recent_performance[model_id] / total_performance
                # Suavizar cambios en los pesos (70% peso anterior, 30% nuevo)
                self.model_weights[model_id] = (0.7 * self.model_weights[model_id]) + (0.3 * performance_ratio * len(self.models))
        
        logger.debug(f"Pesos actualizados: {self.model_weights}")
    
    def predict(self, data, threshold=0.75, update_weights=True):
        """
        Realiza una predicción de anomalía utilizando el ensamble de modelos
        
        Args:
            data: Datos a evaluar
            threshold: Umbral para considerar anomalía
            update_weights: Si True, actualiza los pesos tras la predicción
            
        Returns:
            Tuple(is_anomaly, anomaly_score, details)
        """
        if not self.models:
            logger.warning("No hay modelos en el ensamble para realizar predicciones")
            return False, 0.0, {}
        
        # Recolectar predicciones de cada modelo
        model_scores = {}
        model_details = {}
        
        for model_id, model in self.models.items():
            try:
                # La lógica específica de predicción depende del tipo de modelo
                if "isolation_forest" in model_id.lower():
                    # Para Isolation Forest
                    raw_score = model.decision_function([data])[0]
                    # Convertir a score de anomalía (más alto = más anómalo)
                    score = 1.0 - ((raw_score + 1.0) / 2.0)
                    confidence = min(max(0.5 + abs(raw_score) / 2, 0.5), 1.0)
                elif "autoencoder" in model_id.lower():
                    # Para Autoencoder
                    prediction = model.predict(np.array([data]), verbose=0)
                    mse = np.mean(np.square(np.array([data]) - prediction))
                    # Normalizar score (asumiendo que MSE > 0.1 es anómalo)
                    score = min(mse / 0.1, 1.0)
                    confidence = min(max(0.5 + (score - 0.5) * 2, 0.5), 1.0) if score > 0.5 else max(0.5 - (0.5 - score) * 2, 0.1)
                elif "robust_covariance" in model_id.lower():
                    # Para modelos basados en covarianza
                    mahalanobis_dist = model.mahalanobis(np.array([data]))[0]
                    # Normalizar a un score entre 0 y 1
                    score = min(1.0, mahalanobis_dist / 20.0)  # Asumir que dist > 20 es 1.0
                    confidence = min(max(0.4 + mahalanobis_dist / 25.0, 0.5), 1.0)
                # Añadir casos para otros tipos de modelos
                else:
                    # Caso genérico
                    score = 0.5
                    confidence = 0.5
                    logger.warning(f"Modelo {model_id} de tipo desconocido")
                
                # Almacenar resultados
                model_scores[model_id] = {
                    'score': score,
                    'confidence': confidence,
                    'weight': self.model_weights[model_id]
                }
                
                # Recopilar detalles
                model_details[model_id] = {
                    'raw_score': score,
                    'confidence': confidence,
                    'contribution': score * self.model_weights[model_id]
                }
                
            except Exception as e:
                logger.error(f"Error al obtener predicción del modelo {model_id}: {str(e)}")
                model_scores[model_id] = {'score': 0.5, 'confidence': 0.1, 'weight': 0.1}
        
        # Calcular score de anomalía agregado con pesos
        weighted_scores = []
        confidences = []
        weights = []
        
        for model_id, score_info in model_scores.items():
            weighted_scores.append(score_info['score'] * score_info['weight'] * score_info['confidence'])
            confidences.append(score_info['confidence'])
            weights.append(score_info['weight'])
        
        # Normalizar para que sumen 1
        weights_sum = sum(weights)
        norm_weights = [w/weights_sum for w in weights] if weights_sum > 0 else [1.0/len(weights)] * len(weights)
        
        # Método de combinación más robusto: media ponderada por peso*confianza
        total_confidence_weight = sum([confidences[i] * norm_weights[i] for i in range(len(norm_weights))])
        anomaly_score = sum(weighted_scores) / total_confidence_weight if total_confidence_weight > 0 else 0.5
        
        # Determinar si es anomalía basado en umbral
        is_anomaly = anomaly_score >= threshold
        
        # Prepara detalles para retornar
        details = {
            'model_contributions': model_details,
            'threshold': threshold,
            'ensemble_method': 'weighted_confidence',
            'model_weights': {k: round(v, 3) for k, v in self.model_weights.items()}
        }
        
        # Si hay feedback disponible, actualizar pesos
        if update_weights and is_anomaly:
            # Este es un placeholder - en un sistema real, 
            # el feedback verdadero vendría después de verificar si la anomalía era real
            self.update_weights({model_id: 1.0 for model_id in self.models})
        
        return is_anomaly, anomaly_score, details


class AnomalyDetector:
    """
    Detector de anomalías para sistemas distribuidos utilizando
    múltiples métodos y adaptación automática.
    """
    
    def __init__(self, config=None, engine=None, kafka_producer=None):
        """
        Inicializa el detector de anomalías.
        
        Args:
            config: Configuración del detector
            engine: Conexión a la base de datos
            kafka_producer: Productor Kafka para publicar anomalías
        """
        self.config = config or {}
        self.engine = engine
        self.kafka_producer = kafka_producer
        
        # Parámetros de configuración
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.75)
        self.lookback_window = self.config.get('lookback_window', 10)
        self.min_data_points = self.config.get('min_data_points', 5)
        self.models_dir = self.config.get('models_dir', '/app/models/anomaly')
        
        # Inicializar scaler y modelos
        self.scaler = None
        self.models = {}
        self.service_buffers = {}  # Buffer de datos recientes por servicio
        self.service_baselines = {}  # Líneas base por servicio
        
        # Estadísticas de anomalías
        self.anomaly_stats = {
            'total_analyzed': 0,
            'anomalies_detected': 0,
            'last_anomalies': deque(maxlen=100)
        }
        
        # Carga de modelos
        self.load_models()
        
        # Inicializar detector de ensamble
        self.ensemble_detector = None
        self.initialize_ensemble_detector()
        
        logger.info("Detector de anomalías inicializado")
    
    def load_models(self):
        """Carga los modelos de detección de anomalías desde disco"""
        try:
            # Cargar scaler
            scaler_path = os.path.join(self.models_dir, 'standard_scaler.joblib')
            if os.path.exists(scaler_path):
                self.scaler = joblib.load(scaler_path)
                logger.info("Scaler cargado correctamente")
            else:
                self.scaler = StandardScaler()
                logger.warning("No se encontró scaler, se inicializará uno nuevo")
            
            # Cargar modelos de Isolation Forest
            if_path = os.path.join(self.models_dir, 'isolation_forest.joblib')
            if os.path.exists(if_path):
                self.models['isolation_forest'] = joblib.load(if_path)
                logger.info("Modelo Isolation Forest cargado correctamente")
            
            # Cargar autoencoder
            ae_path = os.path.join(self.models_dir, 'autoencoder.h5')
            if os.path.exists(ae_path):
                self.models['autoencoder'] = load_model(ae_path)
                logger.info("Modelo Autoencoder cargado correctamente")
            
            # Cargar información de líneas base
            baseline_path = os.path.join(self.models_dir, 'service_baselines.json')
            if os.path.exists(baseline_path):
                with open(baseline_path, 'r') as f:
                    self.service_baselines = json.load(f)
                logger.info(f"Líneas base cargadas para {len(self.service_baselines)} servicios")
        
        except Exception as e:
            logger.error(f"Error al cargar modelos: {str(e)}")
    
    def initialize_ensemble_detector(self):
        """Inicializa el detector de ensamble con los modelos cargados"""
        try:
            # Configurar modelos para el ensamble
            models_config = []
            
            # Añadir Isolation Forest si existe
            if 'isolation_forest' in self.models:
                models_config.append({
                    'type': 'isolation_forest',
                    'id': 'isolation_forest',
                    'path': os.path.join(self.models_dir, 'isolation_forest.joblib'),
                    'initial_weight': 1.0
                })
            
            # Añadir Autoencoder si existe
            if 'autoencoder' in self.models:
                models_config.append({
                    'type': 'autoencoder',
                    'id': 'autoencoder',
                    'path': os.path.join(self.models_dir, 'autoencoder.h5'),
                    'initial_weight': 1.2  # Damos un poco más de peso inicial al autoencoder
                })
            
            # Inicializar detector de ensamble
            self.ensemble_detector = AdaptiveEnsembleDetector(models_config)
            logger.info(f"Detector de ensamble inicializado con {len(models_config)} modelos")
            
        except Exception as e:
            logger.error(f"Error al inicializar detector de ensamble: {str(e)}")
            # Crear un detector vacío como fallback
            self.ensemble_detector = AdaptiveEnsembleDetector()
    
    def preprocess_data(self, data):
        """
        Preprocesa los datos antes de la detección de anomalías.
        
        Args:
            data: DataFrame con los datos a preprocesar
            
        Returns:
            Tuple: (scaled_data, original_df)
        """
        try:
            # Convertir a DataFrame si es un diccionario
            if isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                df = pd.DataFrame(data)
            
            # Seleccionar solo columnas numéricas
            numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
            if not numeric_cols:
                logger.warning("No hay columnas numéricas en los datos")
                return None, df
            
            # Guardar copia del DataFrame original
            original_df = df.copy()
            
            # Seleccionar solo datos numéricos para escalar
            numeric_df = df[numeric_cols].copy()
            
            # Manejar valores faltantes
            numeric_df = numeric_df.fillna(numeric_df.mean())
            
            # Escalar datos
            if self.scaler is None:
                self.scaler = StandardScaler().fit(numeric_df)
                # Guardar scaler
                joblib.dump(self.scaler, os.path.join(self.models_dir, 'standard_scaler.joblib'))
            
            scaled_data = self.scaler.transform(numeric_df)
            
            return scaled_data, original_df
            
        except Exception as e:
            logger.error(f"Error al preprocesar datos: {str(e)}")
            return None, None
    
    def detect_anomalies(self, data):
        """
        Detecta anomalías en los datos utilizando múltiples modelos.
        
        Args:
            data: Datos a analizar para anomalías (dict o DataFrame)
            
        Returns:
            Tuple: (is_anomaly, anomaly_score, details)
        """
        try:
            # Incrementar contador de análisis
            self.anomaly_stats['total_analyzed'] += 1
            
            # Preprocesar datos
            scaled_data, original_df = self.preprocess_data(data)
            if scaled_data is None:
                return False, 0, {}
            
            # Extraer service_id para seguimiento
            service_id = data.get('service_id', original_df.get('service_id', 'unknown_service')[0])
            
            # Actualizar buffer de datos para este servicio
            if service_id not in self.service_buffers:
                self.service_buffers[service_id] = deque(maxlen=self.lookback_window)
            self.service_buffers[service_id].append(data)
            
            # Verificar si tenemos suficientes datos para análisis contextual
            has_context = len(self.service_buffers[service_id]) >= self.min_data_points
            
            # Calcular características de tendencia si hay suficiente contexto
            if has_context:
                trend_features = self._calculate_trend_features(service_id)
                # Añadir características de tendencia a los datos originales
                for feature, value in trend_features.items():
                    if isinstance(data, dict):
                        data[feature] = value
                    else:
                        original_df[feature] = value
                
                # Actualizar scaled_data con nuevas características
                scaled_data, original_df = self.preprocess_data(data)
            
            # Usar el detector de ensamble
            is_anomaly, anomaly_score, details = self.ensemble_detector.predict(
                scaled_data[0],  # Primer elemento ya que es un batch de 1
                threshold=self.anomaly_threshold
            )
            
            # Enriquecer detalles con información de las métricas
            if is_anomaly:
                # Incrementar contador de anomalías
                self.anomaly_stats['anomalies_detected'] += 1
                
                # Registrar anomalía para estadísticas
                anomaly_info = {
                    'service_id': service_id,
                    'timestamp': datetime.now().isoformat(),
                    'anomaly_score': anomaly_score,
                    'details': details
                }
                self.anomaly_stats['last_anomalies'].append(anomaly_info)
                
                # Identificar métricas que contribuyeron a la anomalía
                feature_details = {}
                
                if 'autoencoder' in self.models:
                    # Obtener la reconstrucción del autoencoder
                    reconstruction = self.models['autoencoder'].predict(scaled_data, verbose=0)
                    # Calcular error por característica
                    feature_errors = np.power(scaled_data - reconstruction, 2)[0]
                    
                    # Mapear errores a nombres de características
                    numeric_cols = original_df.select_dtypes(include=['number']).columns.tolist()
                    feature_contributions = dict(zip(numeric_cols, feature_errors))
                    
                    # Obtener las métricas con mayor error (top 3)
                    sorted_contributions = sorted(
                        feature_contributions.items(), 
                        key=lambda x: x[1], 
                        reverse=True
                    )[:3]
                    
                    for feature, error in sorted_contributions:
                        feature_details[feature] = {
                            'error': float(error),
                            'value': float(original_df[feature].iloc[0]) if feature in original_df.columns else None,
                            'z_score': self._calculate_zscore(
                                original_df[feature].iloc[0] if feature in original_df.columns else 0,
                                feature,
                                original_df
                            )
                        }
                
                # Si hay línea base para este servicio, añadir comparación
                if service_id in self.service_baselines:
                    baseline = self.service_baselines[service_id]
                    baseline_comparison = {}
                    
                    for feature in feature_details:
                        if feature in baseline:
                            current_value = original_df[feature].iloc[0] if feature in original_df.columns else None
                            if current_value is not None:
                                deviation = ((current_value - baseline[feature]) / baseline[feature]) * 100 if baseline[feature] != 0 else float('inf')
                                baseline_comparison[feature] = {
                                    'baseline': baseline[feature],
                                    'current': current_value,
                                    'deviation_percent': float(deviation)
                                }
                    
                    details['baseline_comparison'] = baseline_comparison
                
                # Añadir detalles de tendencia si existen
                if has_context and trend_features:
                    trends_info = {}
                    for feature, value in trend_features.items():
                        base_feature = feature.replace('_trend', '').replace('_growth_rate', '')
                        if base_feature in original_df.columns:
                            trends_info[base_feature] = {
                                'trend_value': value,
                                'recent_values': [float(x.get(base_feature, 0)) if isinstance(x, dict) else float(getattr(x, base_feature, 0)) 
                                                for x in list(self.service_buffers[service_id])[-5:]]
                            }
                    
                    details['trends'] = trends_info
                
                # Añadir detalles de métricas a los resultados
                details['metrics_contribution'] = feature_details
            
            return is_anomaly, anomaly_score, details
        
        except Exception as e:
            logger.error(f"Error al detectar anomalías: {str(e)}")
            return False, 0, {'error': str(e)}
    
    def _calculate_trend_features(self, service_id):
        """
        Calcula características de tendencia basadas en el buffer de datos.
        
        Args:
            service_id: ID del servicio para obtener su buffer
            
        Returns:
            dict: Características de tendencia calculadas
        """
        buffer = list(self.service_buffers[service_id])
        if len(buffer) < 3:  # Necesitamos al menos 3 puntos para tendencia
            return {}
        
        trend_features = {}
        
        # Extraer métricas comunes
        common_metrics = self._extract_common_metrics(buffer)
        
        # Para cada métrica, calcular tendencia
        for metric in common_metrics:
            values = []
            for item in buffer:
                if isinstance(item, dict):
                    val = item.get(metric)
                else:
                    val = getattr(item, metric, None)
                values.append(val if val is not None else np.nan)
            
            # Reemplazar NaN con interpolación
            values = pd.Series(values).interpolate().values
            
            # Si hay al menos 3 valores válidos, calcular tendencia
            if len(values) >= 3 and not np.isnan(values).any():
                # Calcular pendiente con regresión lineal
                x = np.arange(len(values))
                slope, _, r_value, _, _ = stats.linregress(x, values)
                
                # Guardar tendencia solo si hay correlación significativa
                if abs(r_value) >= 0.6:
                    trend_features[f"{metric}_trend"] = float(slope)
                
                # Calcular tasa de crecimiento
                if values[-1] != 0 and values[0] != 0:
                    growth_rate = ((values[-1] - values[0]) / values[0]) * 100
                    trend_features[f"{metric}_growth_rate"] = float(growth_rate)
        
        return trend_features
    
    def _extract_common_metrics(self, buffer):
        """
        Extrae métricas comunes presentes en todos los elementos del buffer.
        
        Args:
            buffer: Lista de diccionarios o objetos con datos
            
        Returns:
            list: Lista de métricas comunes
        """
        if not buffer:
            return []
        
        # Obtener todas las claves del primer elemento
        if isinstance(buffer[0], dict):
            all_keys = set(buffer[0].keys())
            
            # Filtrar a solo claves numéricas
            numeric_keys = set()
            for k, v in buffer[0].items():
                if isinstance(v, (int, float)) and not k.startswith('_') and k != 'timestamp':
                    numeric_keys.add(k)
            
            # Verificar presencia en todos los elementos
            for item in buffer[1:]:
                if not isinstance(item, dict):
                    return []
                numeric_keys = numeric_keys.intersection(k for k, v in item.items() 
                                                       if isinstance(v, (int, float)))
            
            return list(numeric_keys)
        else:
            # Para objetos, extraer atributos comunes
            # Esta implementación dependerá del tipo de objetos en el buffer
            return []
    
    def _calculate_zscore(self, value, feature, df):
        """
        Calcula el Z-score para un valor dado.
        
        Args:
            value: Valor a analizar
            feature: Nombre de la característica
            df: DataFrame con los datos
            
        Returns:
            float: Z-score calculado
        """
        try:
            if feature not in df.columns:
                return 0.0
                
            feature_idx = list(df.columns).index(feature)
            if hasattr(self.scaler, 'mean_') and feature_idx < len(self.scaler.mean_):
                mean = self.scaler.mean_[feature_idx]
                std = self.scaler.scale_[feature_idx]
                if std != 0:
                    z_score = abs((value - mean) / std)
                    return float(z_score)
            
            # Fallback: calcular z-score con datos actuales
            mean = df[feature].mean()
            std = df[feature].std()
            if std != 0:
                z_score = abs((value - mean) / std)
                return float(z_score)
            
            return 0.0
        except Exception as e:
            logger.error(f"Error al calcular Z-score: {str(e)}")
            return 0.0
    
    def save_state(self):
        """Guarda el estado actual del detector de anomalías"""
        try:
            # Guardar scaler
            if self.scaler is not None:
                joblib.dump(self.scaler, os.path.join(self.models_dir, 'standard_scaler.joblib'))
            
            # Guardar líneas base de servicios
            baseline_path = os.path.join(self.models_dir, 'service_baselines.json')
            with open(baseline_path, 'w') as f:
                json.dump(self.service_baselines, f)
            
            # Guardar estadísticas
            stats_path = os.path.join(self.models_dir, 'anomaly_stats.json')
            stats_data = {
                'total_analyzed': self.anomaly_stats['total_analyzed'],
                'anomalies_detected': self.anomaly_stats['anomalies_detected'],
                'last_update': datetime.now().isoformat()
            }
            with open(stats_path, 'w') as f:
                json.dump(stats_data, f)
            
            logger.info("Estado del detector de anomalías guardado correctamente")
            return True
        except Exception as e:
            logger.error(f"Error al guardar estado: {str(e)}")
            return False
    
    def update_service_baseline(self, service_id, metrics):
        """
        Actualiza la línea base para un servicio.
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario con métricas a usar como línea base
        """
        try:
            # Si es la primera vez, inicializar
            if service_id not in self.service_baselines:
                self.service_baselines[service_id] = {}
            
            # Actualizar solo métricas numéricas
            for key, value in metrics.items():
                if isinstance(value, (int, float)):
                    # Si ya existe, hacer promedio ponderado (75% histórico, 25% nuevo)
                    if key in self.service_baselines[service_id]:
                        self.service_baselines[service_id][key] = (
                            self.service_baselines[service_id][key] * 0.75 + value * 0.25
                        )
                    else:
                        self.service_baselines[service_id][key] = value
            
            logger.info(f"Línea base actualizada para servicio {service_id}")
            return True
        except Exception as e:
            logger.error(f"Error al actualizar línea base: {str(e)}")
            return False
    
    def get_detection_stats(self):
        """
        Obtiene estadísticas de detección de anomalías.
        
        Returns:
            dict: Estadísticas de detección
        """
        return {
            'total_analyzed': self.anomaly_stats['total_analyzed'],
            'anomalies_detected': self.anomaly_stats['anomalies_detected'],
            'detection_rate': (self.anomaly_stats['anomalies_detected'] / self.anomaly_stats['total_analyzed']) 
                              if self.anomaly_stats['total_analyzed'] > 0 else 0,
            'services_monitored': len(self.service_buffers),
            'models_available': list(self.models.keys()),
            'ensemble_weights': self.ensemble_detector.model_weights if self.ensemble_detector else {}
        }
    
    def process_and_detect(self, data):
        """
        Procesa datos, detecta anomalías y publica resultados.
        
        Args:
            data: Datos a procesar y analizar
            
        Returns:
            dict: Resultado del procesamiento
        """
        try:
            start_time = time.time()
            
            # Extraer service_id
            service_id = data.get('service_id', 'unknown_service')
            
            # Detectar anomalías
            is_anomaly, anomaly_score, details = self.detect_anomalies(data)
            
            # Calcular tiempo de procesamiento
            processing_time = time.time() - start_time
            
            # Preparar resultado
            result = {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'is_anomaly': is_anomaly,
                'anomaly_score': anomaly_score,
                'processing_time_ms': processing_time * 1000,
                'details': details
            }
            
            # Si hay anomalía, publicar en Kafka
            if is_anomaly and self.kafka_producer:
                try:
                    self.kafka_producer.send('anomalies', result)
                    logger.info(f"Anomalía publicada para servicio {service_id} con score {anomaly_score:.3f}")
                except Exception as e:
                    logger.error(f"Error al publicar anomalía en Kafka: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error en process_and_detect: {str(e)}")
            return {
                'error': str(e),
                'service_id': data.get('service_id', 'unknown_service'),
                'timestamp': datetime.now().isoformat(),
                'is_anomaly': False
            }

# Funciones de utilidad

def load_test_data(file_path):
    """Carga datos de prueba desde un archivo CSV"""
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        logger.error(f"Error al cargar datos de prueba: {str(e)}")
        return None

def train_isolation_forest(data, contamination=0.05):
    """Entrena un modelo de Isolation Forest"""
    model = IsolationForest(contamination=contamination, random_state=42)
    model.fit(data)
    return model

def train_autoencoder(data, encoding_dim=8, epochs=50):
    """Entrena un modelo de Autoencoder"""
    from tensorflow.keras.layers import Input, Dense, Dropout
    from tensorflow.keras.models import Model
    
    # Parámetros
    input_dim = data.shape[1]
    
    # Definir arquitectura
    input_layer = Input(shape=(input_dim,))
    
    # Encoder
    encoded = Dense(32, activation='relu')(input_layer)
    encoded = Dropout(0.2)(encoded)
    encoded = Dense(16, activation='relu')(encoded)
    encoded = Dense(encoding_dim, activation='relu')(encoded)
    
    # Decoder
    decoded = Dense(16, activation='relu')(encoded)
    decoded = Dropout(0.2)(decoded)
    decoded = Dense(32, activation='relu')(decoded)
    decoded = Dense(input_dim, activation='sigmoid')(decoded)
    
    # Autoencoder completo
    autoencoder = Model(input_layer, decoded)
    
    # Compilar modelo
    autoencoder.compile(optimizer='adam', loss='mean_squared_error')
    
    # Entrenar modelo
    autoencoder.fit(
        data, data,
        epochs=epochs,
        batch_size=32,
        shuffle=True,
        validation_split=0.2,
        verbose=1
    )
    
    return autoencoder

# Función principal de ejemplo
def main():
    """Función principal para pruebas locales"""
    # Configuración de ejemplo
    config = {
        'anomaly_threshold': 0.75,
        'lookback_window': 10,
        'min_data_points': 5,
        'models_dir': './models/anomaly'
    }
    
    # Crear detector
    detector = AnomalyDetector(config=config)
    
    # Datos de ejemplo
    example_data = {
        'service_id': 'web_service',
        'cpu_usage': 85.2,
        'memory_usage': 78.4,
        'disk_usage_percent': 65.3,
        'response_time_ms': 250,
        'error_rate': 2.5,
        'active_connections': 128,
        'requests_per_second': 42
    }
    
    # Detectar anomalías
    is_anomaly, score, details = detector.detect_anomalies(example_data)
    
    # Mostrar resultados
    print(f"Anomalía detectada: {is_anomaly}")
    print(f"Score de anomalía: {score:.3f}")
    print("Detalles:")
    for key, value in details.items():
        print(f"  {key}: {value}")

if __name__ == "__main__":
    main()