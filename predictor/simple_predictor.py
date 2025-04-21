# -*- coding: utf-8 -*-
import numpy as np
import pandas as pd
import json
import logging
import os
from datetime import datetime, timedelta
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("predictor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('simple_predictor')

class SimplePredictor:
    """Predictor de tendencias y anomalías futuras"""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Parámetros de configuración
        self.prediction_threshold = self.config.get('prediction_threshold', 0.6)
        self.min_history_points = self.config.get('min_history_points', 10)
        self.prediction_horizon = self.config.get('prediction_horizon', 24)  # horas
        
        # Directorio para almacenar datos
        self.data_dir = self.config.get('data_dir', './data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Histórico de predicciones por servicio
        self.prediction_history = {}
        
        # Modelos entrenados por servicio
        self.models = {}
        
        logger.info("Predictor de tendencias inicializado")
    
    def load_prediction_models(self):
        """Carga modelos previamente entrenados si existen"""
        models_file = os.path.join(self.data_dir, 'prediction_models.json')
        
        if os.path.exists(models_file):
            try:
                with open(models_file, 'r', encoding='utf-8-sig') as f:
                    model_params = json.load(f)
                
                # Reconstruir modelos
                for service_id, metrics in model_params.items():
                    self.models[service_id] = {}
                    for metric, params in metrics.items():
                        model = LinearRegression()
                        model.coef_ = np.array(params.get('coef', [0]))
                        model.intercept_ = params.get('intercept', 0)
                        self.models[service_id][metric] = {
                            'model': model,
                            'scaler': StandardScaler(),
                            'last_trained': params.get('last_trained')
                        }
                
                logger.info(f"Modelos de predicción cargados: {len(self.models)} servicios")
            except Exception as e:
                logger.error(f"Error al cargar modelos de predicción: {str(e)}")
    
    def save_prediction_models(self):
        """Guarda modelos entrenados para uso futuro"""
        models_file = os.path.join(self.data_dir, 'prediction_models.json')
        
        try:
            # Convertir modelos a formato serializable
            model_params = {}
            for service_id, metrics in self.models.items():
                model_params[service_id] = {}
                for metric, model_data in metrics.items():
                    model = model_data['model']
                    model_params[service_id][metric] = {
                        'coef': model.coef_.tolist() if hasattr(model, 'coef_') else [],
                        'intercept': float(model.intercept_) if hasattr(model, 'intercept_') else 0,
                        'last_trained': model_data.get('last_trained')
                    }
            
            with open(models_file, 'w', encoding='utf-8') as f:
                json.dump(model_params, f, indent=2)
            
            logger.info(f"Modelos de predicción guardados en {models_file}")
        except Exception as e:
            logger.error(f"Error al guardar modelos de predicción: {str(e)}")
    
    def parse_datetime(self, ts_string):
        """Parsea un string de timestamp a objeto datetime con manejo de zonas horarias"""
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
    
    def train_model(self, service_id, metric, data_points, timestamps):
        """Entrena un modelo de predicción para una métrica específica"""
        try:
            if len(data_points) < self.min_history_points:
                return None
            
            # Convertir timestamps a minutos desde el primero (característica numérica)
            try:
                # Parsear timestamps con manejo adecuado de zonas horarias
                datetime_objects = [self.parse_datetime(ts) for ts in timestamps]
                base_time = datetime_objects[0]
                time_features = []
                
                for dt in datetime_objects:
                    # Calcular minutos desde el tiempo base
                    minutes = (dt - base_time).total_seconds() / 60
                    time_features.append([minutes])
                
                # Normalizar características
                scaler = StandardScaler()
                X = scaler.fit_transform(np.array(time_features))
                y = np.array(data_points)
                
                # Entrenar modelo
                model = LinearRegression()
                model.fit(X, y)
                
                # Guardar modelo y scaler
                if service_id not in self.models:
                    self.models[service_id] = {}
                
                self.models[service_id][metric] = {
                    'model': model,
                    'scaler': scaler,
                    'base_time': base_time,
                    'last_trained': datetime.now().isoformat()
                }
                
                # Calcular métricas de ajuste
                y_pred = model.predict(X)
                mse = np.mean((y - y_pred) ** 2)
                r2 = model.score(X, y)
                
                logger.info(f"Modelo entrenado para {service_id}:{metric} (MSE: {mse:.3f}, R²: {r2:.3f})")
                
                # Guardar modelos actualizados
                self.save_prediction_models()
                
                return model
            except Exception as e:
                logger.error(f"Error en procesamiento de timestamps para {service_id}:{metric}: {str(e)}")
                return None
        
        except Exception as e:
            logger.error(f"Error al entrenar modelo para {service_id}:{metric}: {str(e)}")
            return None
    
    def predict_metrics(self, service_id, metrics_history, hours_ahead=None):
        """
        Predice valores futuros de métricas para un servicio
        
        Args:
            service_id: ID del servicio
            metrics_history: Historial de métricas del servicio
            hours_ahead: Horas a futuro para predecir (default: usa prediction_horizon)
            
        Returns:
            Diccionario con predicciones y detalles
        """
        if hours_ahead is None:
            hours_ahead = self.prediction_horizon
        
        try:
            if not metrics_history or len(metrics_history) < self.min_history_points:
                logger.warning(f"Historial insuficiente para {service_id} (puntos: {len(metrics_history) if metrics_history else 0})")
                return None
            
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
                return None
            
            # Entrenar o actualizar modelos para cada métrica
            prediction_results = {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction_horizon': hours_ahead,
                'predicted_metrics': {},
                'influential_metrics': {},
                'probability': 0.0,
                'confidence': 0.0
            }
            
            # Para cada métrica, predecir valor futuro
            anomaly_probabilities = []
            
            for metric, values in metrics_data.items():
                if len(values) < self.min_history_points:
                    continue
                
                # Siempre entrenar un modelo nuevo para evitar problemas con modelos antiguos
                model = self.train_model(service_id, metric, values, timestamps)
                
                if model is None:
                    continue
                
                # Verificar que tenemos los datos necesarios para predicción
                if (service_id not in self.models or
                    metric not in self.models[service_id] or
                    'model' not in self.models[service_id][metric] or
                    'scaler' not in self.models[service_id][metric] or
                    'base_time' not in self.models[service_id][metric]):
                    continue
                
                model_data = self.models[service_id][metric]
                model = model_data['model']
                scaler = model_data['scaler']
                base_time = model_data['base_time']
                
                # Preparar punto futuro para predicción
                future_time = datetime.now() + timedelta(hours=hours_ahead)
                minutes = (future_time - base_time).total_seconds() / 60
                
                # Transformar características
                X_future = scaler.transform([[minutes]])
                
                # Predecir valor
                try:
                    predicted_value = float(model.predict(X_future)[0])
                    
                    # Guardar predicción
                    prediction_results['predicted_metrics'][metric] = predicted_value
                    
                    # Calcular probabilidad de anomalía
                    # Obtenemos el umbral actual para esta métrica
                    threshold_file = os.path.join(self.data_dir, 'thresholds.json')
                    thresholds = {}
                    try:
                        if os.path.exists(threshold_file):
                            with open(threshold_file, 'r', encoding='utf-8-sig') as f:
                                thresholds = json.load(f)
                    except Exception as e:
                        logger.error(f"Error al leer umbrales: {str(e)}")
                    
                    service_thresholds = thresholds.get(service_id, thresholds.get('default', {}))
                    threshold = service_thresholds.get(metric)
                    
                    if threshold:
                        # Calcular probabilidad de anomalía según tipo de métrica
                        if metric == 'hit_rate':  # Valores bajos son problemáticos
                            if predicted_value < threshold:
                                anomaly_prob = 0.5 + 0.5 * min(1.0, (threshold - predicted_value) / threshold)
                                anomaly_probabilities.append(anomaly_prob)
                                
                                # Guardar métricas influyentes
                                if anomaly_prob > 0.5:
                                    prediction_results['influential_metrics'][metric] = predicted_value
                        else:  # Valores altos son problemáticos
                            if predicted_value > threshold:
                                anomaly_prob = 0.5 + 0.5 * min(1.0, (predicted_value - threshold) / threshold)
                                anomaly_probabilities.append(anomaly_prob)
                                
                                # Guardar métricas influyentes
                                if anomaly_prob > 0.5:
                                    prediction_results['influential_metrics'][metric] = predicted_value
                except Exception as e:
                    logger.error(f"Error al predecir valor para {service_id}:{metric}: {str(e)}")
            
            # Calcular probabilidad general de anomalía
            if anomaly_probabilities:
                # Usar el máximo como indicador principal, pero considerar también el promedio
                max_prob = max(anomaly_probabilities)
                avg_prob = sum(anomaly_probabilities) / len(anomaly_probabilities)
                
                # Probabilidad ponderada (70% máximo, 30% promedio)
                prediction_results['probability'] = 0.7 * max_prob + 0.3 * avg_prob
                
                # Asignar confianza basada en cantidad de métricas
                prediction_results['confidence'] = min(1.0, len(prediction_results['influential_metrics']) / 3.0)
            
            # Guardar en historial
            if service_id not in self.prediction_history:
                self.prediction_history[service_id] = []
            
            self.prediction_history[service_id].append(prediction_results)
            
            # Limitar tamaño del historial
            max_history = self.config.get('max_prediction_history', 50)
            if len(self.prediction_history[service_id]) > max_history:
                self.prediction_history[service_id] = self.prediction_history[service_id][-max_history:]
            
            return prediction_results
            
        except Exception as e:
            logger.error(f"Error al predecir métricas para {service_id}: {str(e)}")
            return None
    
    def get_failure_prediction(self, service_id, metrics_history, hours_ahead=None):
        """
        Predice si un servicio experimentará una anomalía en el futuro
        
        Args:
            service_id: ID del servicio
            metrics_history: Historial de métricas del servicio
            hours_ahead: Horas a futuro para predecir (default: usa prediction_horizon)
            
        Returns:
            Diccionario con detalles de la predicción o None si no hay predicción
        """
        prediction = self.predict_metrics(service_id, metrics_history, hours_ahead)
        
        if not prediction:
            return None
        
        # Verificar si la probabilidad supera el umbral
        if prediction['probability'] >= self.prediction_threshold:
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