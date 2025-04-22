# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import json
import logging
import os
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.preprocessing import StandardScaler, PolynomialFeatures
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("advanced_predictor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('advanced_predictor')

class AdvancedPredictor:
    """Predictor avanzado mejorado con detección proactiva de anomalías futuras"""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Parámetros de configuración
        self.prediction_threshold = self.config.get('prediction_threshold', 0.6)
        self.min_history_points = self.config.get('min_history_points', 8)
        self.max_prediction_hours = self.config.get('max_prediction_hours', 24)  # Máximo horizonte de predicción
        self.time_intervals = [1, 2, 4, 8, 12, 24]  # Horas a predecir (1h, 2h, 4h, 8h, 12h, 24h)
        
        # Directorio para almacenar datos
        self.data_dir = self.config.get('data_dir', './data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Historial de predicciones por servicio
        self.prediction_history = {}
        
        # Modelos entrenados por servicio
        self.models = {}
        
        # Cargar umbrales para evaluación
        self.thresholds = self.load_thresholds()
        
        # Límites de crecimiento por hora para evitar predicciones extremas
        self.growth_limits = {
            'cpu_usage': 3.0,        # máximo 3% por hora
            'memory_usage': 2.5,     # máximo 2.5% por hora
            'response_time_ms': 20,  # máximo 20ms por hora
            'error_rate': 0.5,       # máximo 0.5 errores por hora
            'active_connections': 5, # máximo 5 conexiones por hora
            'query_time_avg': 10     # máximo 10ms por hora
        }
        
        # Valores límite absolutos para las predicciones
        self.absolute_limits = {
            'cpu_usage': 95,        # máximo 95%
            'memory_usage': 95,     # máximo 95%
            'response_time_ms': 500, # máximo 500ms
            'error_rate': 10,       # máximo 10 errores
            'active_connections': 150, # máximo 150 conexiones
            'query_time_avg': 200   # máximo 200ms
        }
        
        logger.info("Predictor avanzado mejorado inicializado - Detección proactiva activada")
    
    def load_thresholds(self):
        """Carga umbrales desde archivo para evaluación de anomalías"""
        threshold_file = os.path.join(self.data_dir, 'thresholds.json')
        
        try:
            if os.path.exists(threshold_file):
                with open(threshold_file, 'r', encoding='utf-8-sig') as f:
                    thresholds = json.load(f)
                logger.info(f"Umbrales cargados: {len(thresholds)} servicios")
                return thresholds
            else:
                logger.warning("Archivo de umbrales no encontrado, creando valores por defecto")
                default_thresholds = {
                    "default": {
                        "memory_usage": 75,
                        "cpu_usage": 75,
                        "response_time_ms": 300,
                        "error_rate": 5,
                        "active_connections": 90,
                        "query_time_avg": 80,
                        "gc_collection_time": 400
                    }
                }
                # Guardar umbrales por defecto
                with open(threshold_file, 'w', encoding='utf-8') as f:
                    json.dump(default_thresholds, f, indent=2)
                return default_thresholds
        except Exception as e:
            logger.error(f"Error al cargar umbrales: {str(e)}")
            return {"default": {}}
    
    def load_prediction_models(self):
        """Carga modelos previamente entrenados si existen"""
        models_file = os.path.join(self.data_dir, 'advanced_prediction_models.json')
        
        if os.path.exists(models_file):
            try:
                with open(models_file, 'r', encoding='utf-8-sig') as f:
                    info = json.load(f)
                    
                logger.info(f"Información de modelos cargada: {len(info)} servicios")
                # No podemos serializar modelos completos, pero sabemos qué métricas tienen modelos
                self.model_info = info
                return True
            except Exception as e:
                logger.error(f"Error al cargar información de modelos: {str(e)}")
        return False
    
    def save_model_info(self):
        """Guarda información sobre modelos entrenados"""
        models_file = os.path.join(self.data_dir, 'advanced_prediction_models.json')
        
        try:
            # No podemos serializar los modelos directamente, pero guardamos qué métricas tienen modelos
            model_info = {}
            for service_id, metrics in self.models.items():
                model_info[service_id] = {
                    "metrics": list(metrics.keys()),
                    "last_trained": datetime.now().isoformat()
                }
            
            with open(models_file, 'w', encoding='utf-8') as f:
                json.dump(model_info, f, indent=2)
            
            logger.info(f"Información de modelos guardada en {models_file}")
        except Exception as e:
            logger.error(f"Error al guardar información de modelos: {str(e)}")
    
    def parse_datetime(self, ts_string):
        """Parsea un string de timestamp a objeto datetime"""
        try:
            # Intentar parsear timestamp con zona horaria
            if 'Z' in ts_string:
                # Convertir 'Z' a '+00:00' para ISO format
                ts_string = ts_string.replace('Z', '+00:00')
                
            if '+' in ts_string or '-' in ts_string and 'T' in ts_string:
                # Ya tiene información de zona horaria
                dt = datetime.fromisoformat(ts_string)
                # Convertir a UTC naive para simplicidad
                return datetime(dt.year, dt.month, dt.day, dt.hour, dt.minute, dt.second)
            else:
                # No tiene zona horaria, asumir local
                return datetime.fromisoformat(ts_string)
        except Exception as e:
            logger.error(f"Error al parsear timestamp {ts_string}: {str(e)}")
            # Fallback a timestamp actual
            return datetime.now()
    
    def train_advanced_model(self, service_id, metric, data_points, timestamps):
        """Entrena un modelo avanzado para una métrica específica"""
        try:
            if len(data_points) < self.min_history_points:
                logger.warning(f"Datos insuficientes para entrenar modelo de {service_id}:{metric}")
                return None
            
            # Convertir timestamps a minutos desde el primero (característica numérica)
            datetime_objects = [self.parse_datetime(ts) for ts in timestamps]
            base_time = min(datetime_objects)
            
            # Crear dataset
            X = []  # Features: [minutes, hour_of_day, day_of_week]
            y = []  # Target: metric value
            
            for i, dt in enumerate(datetime_objects):
                # Características temporales
                minutes = (dt - base_time).total_seconds() / 60
                hour_of_day = dt.hour / 24.0  # Normalizar entre 0-1
                day_of_week = dt.weekday() / 7.0  # Normalizar entre 0-1
                
                # Añadir características
                X.append([minutes, hour_of_day, day_of_week])
                y.append(data_points[i])
            
            # Convertir a arrays de numpy
            X = np.array(X)
            y = np.array(y)
            
            # MEJORA: Detectar y manejar outliers usando límites de percentiles
            # Esto evita que valores extremos afecten al modelo
            if len(y) > 10:
                q1 = np.percentile(y, 10)
                q3 = np.percentile(y, 90)
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                # Filtrar puntos dentro del rango aceptable
                valid_indices = np.where((y >= lower_bound) & (y <= upper_bound))[0]
                
                if len(valid_indices) >= self.min_history_points:
                    X = X[valid_indices]
                    y = y[valid_indices]
                    logger.info(f"Filtrados {len(data_points) - len(valid_indices)} outliers para {service_id}:{metric}")
            
            # MEJORA: Usar modelos más estables según la cantidad de datos
            if len(X) < 10:
                # Crear pipeline con escalado y regresión lineal simple para pocos datos
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('regressor', Ridge(alpha=1.0))  # Alpha más alto para regularización más fuerte
                ])
            else:
                # Crear pipeline con escalado, características polinómicas limitadas y regresión regularizada
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('poly', PolynomialFeatures(degree=2, include_bias=False)),  # Include_bias=False para evitar multicolinealidad
                    ('regressor', Ridge(alpha=0.8))  # Buena regularización para evitar overfitting
                ])
            
            # Entrenar modelo
            model.fit(X, y)
            
            # Calcular métricas de ajuste
            y_pred = model.predict(X)
            mse = np.mean((y - y_pred) ** 2)
            
            # MEJORA: Validación cruzada simple si hay suficientes datos
            # Esto da una idea más real del rendimiento esperado
            if len(X) >= 15:
                try:
                    # Usar una pequeña validación para verificar estabilidad
                    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
                    model.fit(X_train, y_train)
                    test_mse = np.mean((y_test - model.predict(X_test)) ** 2)
                    
                    # Si el error en test es mucho mayor, el modelo es inestable, usamos uno más simple
                    if test_mse > 2 * mse:
                        logger.warning(f"Modelo inestable para {service_id}:{metric}, usando modelo más simple")
                        model = Pipeline([
                            ('scaler', StandardScaler()),
                            ('regressor', Ridge(alpha=1.5))  # Modelo muy simple y estable
                        ])
                        model.fit(X, y)  # Re-entrenar con todos los datos
                        y_pred = model.predict(X)
                        mse = np.mean((y - y_pred) ** 2)
                except Exception as e:
                    logger.error(f"Error en validación cruzada para {service_id}:{metric}: {str(e)}")
            
            # Guardar modelo y metadata
            if service_id not in self.models:
                self.models[service_id] = {}
            
            self.models[service_id][metric] = {
                'model': model,
                'base_time': base_time,
                'last_trained': datetime.now().isoformat(),
                'mse': mse,
                'data_points': len(y),
                'current_value': y[-1] if len(y) > 0 else None,  # MEJORA: Guardar valor actual
                'trend': self._calculate_trend(y)  # MEJORA: Calcular tendencia
            }
            
            logger.info(f"Modelo avanzado entrenado para {service_id}:{metric} (MSE: {mse:.3f}, puntos: {len(y)})")
            self.save_model_info()
            
            return model
            
        except Exception as e:
            logger.error(f"Error al entrenar modelo avanzado para {service_id}:{metric}: {str(e)}")
            return None
    
    def _calculate_trend(self, values):
        """Calcula la tendencia de los valores (positiva, negativa o estable)"""
        if len(values) < 5:
            return 0  # No hay suficientes datos para calcular tendencia
        
        # Usar los últimos 5 puntos para calcular tendencia
        recent = values[-5:]
        
        # Ajuste lineal simple
        X = np.array(range(len(recent))).reshape(-1, 1)
        y = np.array(recent)
        
        try:
            model = LinearRegression()
            model.fit(X, y)
            slope = model.coef_[0]
            
            # Normalizar pendiente respecto al valor promedio
            avg_value = np.mean(y)
            if avg_value != 0:
                normalized_slope = slope / avg_value
            else:
                normalized_slope = slope
            
            return normalized_slope
        except Exception:
            return 0
    
    def predict_point(self, service_id, metric, hours_ahead):
        """Predice un valor futuro específico para una métrica"""
        try:
            if service_id not in self.models or metric not in self.models[service_id]:
                return None
            
            model_data = self.models[service_id][metric]
            model = model_data['model']
            base_time = model_data['base_time']
            current_value = model_data.get('current_value')
            trend = model_data.get('trend', 0)
            
            # MEJORA: Preparar punto futuro para predicción
            future_time = datetime.now() + timedelta(hours=hours_ahead)
            
            # Crear características
            minutes = (future_time - base_time).total_seconds() / 60
            hour_of_day = future_time.hour / 24.0
            day_of_week = future_time.weekday() / 7.0
            
            # Hacer predicción
            X_future = np.array([[minutes, hour_of_day, day_of_week]])
            raw_prediction = float(model.predict(X_future)[0])
            
            # MEJORA: Aplicar restricciones para predicciones más realistas
            if current_value is not None:
                # Obtener límite de crecimiento para esta métrica
                max_growth_per_hour = self.growth_limits.get(metric, 1.0)
                
                # Calcular límites superior e inferior basados en el valor actual
                # Considerar la tendencia reciente para permitir más flexibilidad en esa dirección
                if trend > 0:
                    # Tendencia creciente
                    upper_limit = current_value + (max_growth_per_hour * hours_ahead * (1 + abs(trend)))
                    lower_limit = current_value - (max_growth_per_hour * hours_ahead * 0.5)  # Más restrictivo hacia abajo
                elif trend < 0:
                    # Tendencia decreciente 
                    upper_limit = current_value + (max_growth_per_hour * hours_ahead * 0.5)  # Más restrictivo hacia arriba
                    lower_limit = current_value - (max_growth_per_hour * hours_ahead * (1 + abs(trend)))
                else:
                    # Tendencia neutra
                    upper_limit = current_value + (max_growth_per_hour * hours_ahead)
                    lower_limit = current_value - (max_growth_per_hour * hours_ahead)
                
                # Limitar la predicción según estos límites
                bounded_prediction = max(lower_limit, min(upper_limit, raw_prediction))
                
                # Para horizontes largos, aplicar amortiguación adicional
                if hours_ahead > 4:
                    # Calcular factor de amortiguación que aumenta con el horizonte
                    damping_factor = 4 / hours_ahead
                    
                    # Aplicar amortiguación: mezclar predicción con tendencia lineal simple
                    simple_prediction = current_value + (current_value * trend * hours_ahead)
                    damped_prediction = (bounded_prediction * damping_factor) + (simple_prediction * (1 - damping_factor))
                    
                    # Aplicar límites de nuevo después de amortiguación
                    predicted_value = max(lower_limit, min(upper_limit, damped_prediction))
                else:
                    predicted_value = bounded_prediction
            else:
                # Sin valor actual, confiar en la predicción bruta pero limitar cambios extremos
                predicted_value = raw_prediction
            
            # MEJORA: Aplicar límites absolutos para asegurar valores realistas
            abs_limit = self.absolute_limits.get(metric, float('inf'))
            predicted_value = min(abs_limit, max(0, predicted_value))
            
            # Limitar a valores razonables (no negativos para la mayoría de métricas)
            if metric not in ['hit_rate', 'availability']:
                predicted_value = max(0, predicted_value)
            
            return predicted_value
            
        except Exception as e:
            logger.error(f"Error al predecir {service_id}:{metric} a {hours_ahead}h: {str(e)}")
            return None
    
    def predict_timeline(self, service_id, metrics_history):
        """
        Genera predicciones para múltiples intervalos de tiempo
        y determina cuándo se espera una anomalía
        
        Args:
            service_id: ID del servicio
            metrics_history: Historial de métricas del servicio
            
        Returns:
            Diccionario con predicciones de timeline, anomalías esperadas y detalles
        """
        result = {
            'service_id': service_id,
            'timestamp': datetime.now().isoformat(),
            'timeline': {},
            'first_anomaly_in': None,  # Horas hasta primera anomalía
            'predicted_anomalies': [],
            'confidence': 0.0
        }
        
        try:
            if not metrics_history or len(metrics_history) < self.min_history_points:
                logger.warning(f"Historial insuficiente para {service_id}")
                return result
            
            # Extraer métricas y timestamps
            metrics_data = {}
            timestamps = []
            
            for point in metrics_history:
                ts = point.get('timestamp')
                if not ts:
                    continue
                
                timestamps.append(ts)
                
                for key, value in point.items():
                    if key not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                        if key not in metrics_data:
                            metrics_data[key] = []
                        metrics_data[key].append(value)
            
            # No hay suficientes datos con timestamp
            if len(timestamps) < self.min_history_points:
                return result
            
            # MEJORA: Usar valores actuales de las métricas para mejores predicciones iniciales
            current_metrics = {}
            if metrics_history and len(metrics_history) > 0:
                latest = metrics_history[-1]
                for key, value in latest.items():
                    if key not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                        current_metrics[key] = value
            
            # Entrenar o actualizar modelos para cada métrica
            for metric, values in metrics_data.items():
                if len(values) >= self.min_history_points:
                    if (service_id not in self.models or
                        metric not in self.models[service_id]):
                        self.train_advanced_model(service_id, metric, values, timestamps)
                    elif metric in current_metrics:
                        # Actualizar valor actual en el modelo
                        if service_id in self.models and metric in self.models[service_id]:
                            self.models[service_id][metric]['current_value'] = current_metrics[metric]
            
            # Obtener umbrales para este servicio
            service_thresholds = self.thresholds.get(service_id, self.thresholds.get('default', {}))
            
            # Generar predicciones para cada intervalo de tiempo
            for hours in self.time_intervals:
                result['timeline'][str(hours)] = {
                    'metrics': {},
                    'anomalies': [],
                    'highest_severity': 0.0
                }
                
                # Para cada métrica, predecir valor futuro
                for metric in metrics_data.keys():
                    if service_id in self.models and metric in self.models[service_id]:
                        predicted_value = self.predict_point(service_id, metric, hours)
                        
                        if predicted_value is not None:
                            # Redondear para mejorar legibilidad
                            predicted_value = round(predicted_value, 2)
                            result['timeline'][str(hours)]['metrics'][metric] = predicted_value
                            
                            # Verificar si excede umbral
                            threshold = service_thresholds.get(metric)
                            if threshold:
                                # Para hit_rate, valores bajos son anómalos
                                if metric == 'hit_rate' and predicted_value < threshold:
                                    severity = min(0.95, max(0.1, (threshold - predicted_value) / threshold))
                                    anomaly = {
                                        'metric': metric,
                                        'predicted': predicted_value,
                                        'threshold': threshold,
                                        'severity': severity
                                    }
                                    result['timeline'][str(hours)]['anomalies'].append(anomaly)
                                    result['timeline'][str(hours)]['highest_severity'] = max(
                                        result['timeline'][str(hours)]['highest_severity'], severity)
                                
                                # Para otras métricas, valores altos son anómalos
                                elif metric != 'hit_rate' and predicted_value > threshold:
                                    severity = min(0.95, max(0.1, (predicted_value - threshold) / threshold))
                                    anomaly = {
                                        'metric': metric,
                                        'predicted': predicted_value,
                                        'threshold': threshold,
                                        'severity': severity
                                    }
                                    result['timeline'][str(hours)]['anomalies'].append(anomaly)
                                    result['timeline'][str(hours)]['highest_severity'] = max(
                                        result['timeline'][str(hours)]['highest_severity'], severity)
            
            # Determinar cuándo se espera la primera anomalía
            first_anomaly_hours = None
            predicted_anomalies = []
            
            for hours in sorted([int(h) for h in result['timeline'].keys()]):
                timeline_data = result['timeline'][str(hours)]
                if timeline_data['highest_severity'] >= self.prediction_threshold:
                    if first_anomaly_hours is None:
                        first_anomaly_hours = hours
                    
                    # Agregar a lista de anomalías previstas
                    for anomaly in timeline_data['anomalies']:
                        if anomaly['severity'] >= self.prediction_threshold:
                            predicted_anomaly = anomaly.copy()
                            predicted_anomaly['hours'] = hours
                            predicted_anomaly['timestamp'] = (datetime.now() + timedelta(hours=hours)).isoformat()
                            predicted_anomalies.append(predicted_anomaly)
            
            # Actualizar resultado
            result['first_anomaly_in'] = first_anomaly_hours
            result['predicted_anomalies'] = predicted_anomalies
            
            # MEJORA: Calcular confianza basada en cantidad de datos, MSE y consistencia
            confidence_factors = []
            for metric in metrics_data.keys():
                if service_id in self.models and metric in self.models[service_id]:
                    model_data = self.models[service_id][metric]
                    
                    # Factor de puntos de datos: más datos = mayor confianza
                    # Saturar en 30 puntos (0.3 a 1.0)
                    data_factor = min(1.0, 0.3 + 0.7 * min(1.0, model_data['data_points'] / 30.0))
                    
                    # Factor MSE: menor error = mayor confianza
                    # Normalizar MSE a un factor entre 0-1 (menor es mejor)
                    # Asumimos que un MSE de 100 o más es muy malo (confianza base 0.2)
                    mse_factor = 0.2 + 0.8 * max(0.0, 1.0 - (model_data['mse'] / 100.0))
                    
                    # Combinar factores
                    metric_confidence = 0.6 * data_factor + 0.4 * mse_factor
                    confidence_factors.append(metric_confidence)
            
            if confidence_factors:
                result['confidence'] = round(sum(confidence_factors) / len(confidence_factors), 2)
            else:
                result['confidence'] = 0.3  # Confianza base si no hay factores
            
            # MEJORA: Asegurar que la probabilidad nunca sea NaN
            if result['predicted_anomalies']:
                result['probability'] = round(max([a['severity'] for a in result['predicted_anomalies']]), 2)
            else:
                result['probability'] = 0.0
            
            # Guardar en historial
            if service_id not in self.prediction_history:
                self.prediction_history[service_id] = []
            
            self.prediction_history[service_id].append(result)
            
            # Limitar tamaño del historial
            max_history = self.config.get('max_prediction_history', 50)
            if len(self.prediction_history[service_id]) > max_history:
                self.prediction_history[service_id] = self.prediction_history[service_id][-max_history:]
            
            return result
            
        except Exception as e:
            logger.error(f"Error al generar timeline de predicciones para {service_id}: {str(e)}")
            return result
    
    def get_failure_prediction_timeline(self, service_id, metrics_history):
        """
        Predice cuándo se espera que un servicio experimente una anomalía
        y qué medidas preventivas tomar
        
        Args:
            service_id: ID del servicio
            metrics_history: Historial de métricas del servicio
            
        Returns:
            Diccionario con detalles de la predicción o None si no hay predicción
        """
        prediction = self.predict_timeline(service_id, metrics_history)
        
        if not prediction or not prediction.get('first_anomaly_in'):
            return None
        
        # Verificar si hay alguna predicción de anomalía con suficiente confianza
        if (prediction['first_anomaly_in'] is not None and 
            prediction['confidence'] >= 0.5 and
            len(prediction['predicted_anomalies']) > 0):
            
            # Determinar las métricas que serán problemáticas
            influential_metrics = {}
            for anomaly in prediction['predicted_anomalies']:
                metric = anomaly['metric']
                predicted = anomaly['predicted']
                influential_metrics[metric] = predicted
            
            # Añadir métricas influyentes para usar en recomendaciones
            prediction['influential_metrics'] = influential_metrics
            
            # Calcular probabilidad general de fallo basada en severidad y confianza
            max_severity = max([a['severity'] for a in prediction['predicted_anomalies']])
            prediction['probability'] = round(0.7 * max_severity + 0.3 * prediction['confidence'], 2)
            
            # Añadir hora prevista de la primera anomalía como prediction_horizon
            prediction['prediction_horizon'] = prediction['first_anomaly_in']
            
            return prediction
        
        return None
    
    def get_prediction_history(self, service_id=None, limit=10):
        """Obtiene historial de predicciones para un servicio"""
        if service_id:
            history = self.prediction_history.get(service_id, [])
        else:
            # Combinar historiales de todos los servicios
            history = []
            for predictions in self.prediction_history.values():
                history.extend(predictions)
        
        # Ordenar por timestamp (más recientes primero)
        sorted_history = sorted(history, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return sorted_history[:limit]
    
    def save_prediction(self, prediction):
        """Guarda una predicción en archivo"""
        if not prediction:
            return
        
        try:
            service_id = prediction.get('service_id', 'unknown')
            # Crear nombre de archivo
            filename = f"prediction_{service_id}_{datetime.now().strftime('%Y%m%d')}.json"
            filepath = os.path.join(self.data_dir, filename)
            
            # Leer archivo existente si existe
            data = []
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
            
            # Añadir nueva predicción
            data.append(prediction)
            
            # Guardar archivo
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
                
            logger.debug(f"Predicción guardada en {filepath}")
            
        except Exception as e:
            logger.error(f"Error al guardar predicción: {str(e)}")
