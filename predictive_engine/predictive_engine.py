import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model
from tensorflow.keras.layers import Dense, LSTM, Dropout, BatchNormalization
from tensorflow.keras.optimizers import Adam
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import GradientBoostingRegressor, RandomForestClassifier
import joblib
import os
import json
import logging
from datetime import datetime, timedelta
import traceback
import random
from concurrent.futures import ThreadPoolExecutor
import hashlib

from utils.retry import retry_with_backoff
from utils.metrics import MetricsCollector
from utils.distributed_cache import DistributedCache, cached

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('predictive_engine')

class PredictiveEngine:
    """
    Motor predictivo avanzado que utiliza múltiples modelos para predecir
    fallos antes de que ocurran en diferentes tipos de servicios.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.models_dir = self.config.get('models_dir', './models/predictive')
        self.data_dir = self.config.get('data_dir', './data/timeseries')
        self.prediction_threshold = self.config.get('prediction_threshold', 0.6)
        self.sequence_length = self.config.get('sequence_length', 10)
        self.prediction_horizons = self.config.get('prediction_horizons', [1, 6, 24, 72])  # Horas
        
        # Componentes auxiliares
        self.metrics = MetricsCollector(config=self.config)
        self.cache = DistributedCache(
            redis_host=self.config.get('redis_host', 'localhost'),
            redis_port=self.config.get('redis_port', 6379),
            prefix='predictive_engine'
        )
        
        # Crear directorios si no existen
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Histórico de predicciones (para validar precisión)
        self.prediction_history = {}
        
        # Mapa de modelos por servicio y tipo de predicción
        # key: f"{service_id}:{prediction_type}:{horizon}"
        self.models = {}
        self.scalers = {}
        
        # Ejecutor para tareas asíncronas
        self.executor = ThreadPoolExecutor(max_workers=self.config.get('max_workers', 4))
        
        # Cargar modelos existentes
        self._load_models()
        
        logger.info("Motor predictivo inicializado")
    
    def _load_models(self):
        """Carga modelos de predicción preentrenados"""
        try:
            # Buscar modelos en el directorio
            if not os.path.exists(self.models_dir):
                logger.warning(f"Directorio de modelos {self.models_dir} no existe")
                return
            
            # Recorrer servicios
            for service_id in os.listdir(self.models_dir):
                service_dir = os.path.join(self.models_dir, service_id)
                if not os.path.isdir(service_dir):
                    continue
                
                # Recorrer tipos de predicción
                for prediction_type in os.listdir(service_dir):
                    type_dir = os.path.join(service_dir, prediction_type)
                    if not os.path.isdir(type_dir):
                        continue
                    
                    # Cargar modelos por horizonte
                    for model_file in os.listdir(type_dir):
                        if model_file.endswith('.h5') or model_file.endswith('.joblib'):
                            # Extraer horizonte del nombre del archivo
                            if '_horizon_' in model_file:
                                horizon = int(model_file.split('_horizon_')[1].split('.')[0])
                            else:
                                # Valor por defecto si no se especifica
                                horizon = 24
                            
                            model_path = os.path.join(type_dir, model_file)
                            scaler_path = os.path.join(type_dir, f"scaler_horizon_{horizon}.joblib")
                            metadata_path = os.path.join(type_dir, f"metadata_horizon_{horizon}.json")
                            
                            # Cargar modelo
                            try:
                                if model_file.endswith('.h5'):
                                    model = load_model(model_path)
                                else:
                                    model = joblib.load(model_path)
                                
                                # Cargar scaler si existe
                                scaler = None
                                if os.path.exists(scaler_path):
                                    scaler = joblib.load(scaler_path)
                                
                                # Cargar metadata si existe
                                metadata = {}
                                if os.path.exists(metadata_path):
                                    with open(metadata_path, 'r') as f:
                                        metadata = json.load(f)
                                
                                # Guardar modelo y scaler
                                key = f"{service_id}:{prediction_type}:{horizon}"
                                self.models[key] = model
                                self.scalers[key] = scaler
                                
                                logger.info(f"Modelo cargado: {key}")
                                
                            except Exception as e:
                                logger.error(f"Error al cargar modelo {model_path}: {str(e)}")
            
            logger.info(f"Se cargaron {len(self.models)} modelos de predicción")
            
        except Exception as e:
            logger.error(f"Error al cargar modelos: {str(e)}")
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def predict_failures(self, service_id, data_points, prediction_type=None):
        """
        Predice fallos basados en secuencias de datos históricas
        
        Args:
            service_id: ID del servicio
            data_points: Lista de puntos de datos históricos
            prediction_type: Tipo de predicción (opcional)
            
        Returns:
            Dict con predicción y detalles
        """
        try:
            # Verificar datos mínimos
            if len(data_points) < 3:
                return {
                    "service_id": service_id,
                    "prediction": False,
                    "message": "Datos insuficientes para predicción",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Determinar tipo de predicción si no se proporciona
            if not prediction_type:
                prediction_type = self._identify_prediction_type(data_points)
            
            # Realizar predicciones para diferentes horizontes
            predictions = []
            for horizon in self.prediction_horizons:
                result = self._predict_for_horizon(service_id, data_points, prediction_type, horizon)
                if result:
                    predictions.append(result)
            
            # Si no hay predicciones para ningún horizonte
            if not predictions:
                return {
                    "service_id": service_id,
                    "prediction": False,
                    "probability": 0.0,
                    "message": "No hay modelos disponibles para este servicio",
                    "timestamp": datetime.now().isoformat()
                }
            
            # Ordenar por probabilidad descendente
            predictions.sort(key=lambda x: x.get("probability", 0), reverse=True)
            
            # Obtener la predicción más probable
            best_prediction = predictions[0]
            is_failure_predicted = best_prediction.get("probability", 0) >= self.prediction_threshold
            
            # Construir respuesta
            result = {
                "service_id": service_id,
                "prediction": is_failure_predicted,
                "probability": best_prediction.get("probability", 0),
                "prediction_horizon": best_prediction.get("prediction_horizon", 24),
                "prediction_type": prediction_type,
                "details": {
                    "alternative_predictions": predictions[1:3] if len(predictions) > 1 else [],
                    "model_type": best_prediction.get("model_type", "unknown"),
                    "prediction_timestamp": datetime.now().isoformat()
                },
                "timestamp": datetime.now().isoformat()
            }
            
            # Obtener métricas influyentes
            result["influential_metrics"] = self._extract_influential_metrics(data_points, prediction_type)
            
            # Registrar predicción en histórico
            self._register_prediction(service_id, result)
            
            # Registrar métrica
            self.metrics.prediction_made.labels(
                service_id=service_id,
                prediction_type=prediction_type
            ).inc()
            
            return result
            
        except Exception as e:
            logger.error(f"Error en predict_failures: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "service_id": service_id,
                "prediction": False,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def predict_failures_async(self, service_id, data_points, prediction_type=None, callback=None):
        """
        Versión asíncrona de predict_failures
        
        Args:
            service_id: ID del servicio
            data_points: Lista de puntos de datos
            prediction_type: Tipo de predicción
            callback: Función de callback opcional
            
        Returns:
            Future object
        """
        def _callback_wrapper(future):
            try:
                result = future.result()
                if callback:
                    callback(result)
            except Exception as e:
                logger.error(f"Error en callback de predicción asíncrona: {str(e)}")
        
        future = self.executor.submit(self.predict_failures, service_id, data_points, prediction_type)
        
        if callback:
            future.add_done_callback(_callback_wrapper)
            
        return future
    
    def _identify_prediction_type(self, data_points):
        """
        Identifica el tipo de predicción basado en los datos disponibles
        
        Returns:
            str: Tipo de predicción
        """
        if not data_points:
            return "unknown"
            
        # Obtener métricas del primer punto
        sample_point = data_points[0]
        metrics = list(sample_point.keys())
        
        # Patrones de métricas para diferentes tipos de predicción
        patterns = {
            "memory_failure": ["memory_usage", "gc_collection_time"],
            "cpu_failure": ["cpu_usage", "cpu_throttling", "load_average"],
            "disk_failure": ["disk_usage", "iops", "io_wait"],
            "db_failure": ["active_connections", "connection_wait_time", "query_time"],
            "network_failure": ["network_errors", "packet_loss", "latency"]
        }
        
        # Buscar coincidencias
        best_match = None
        max_match_count = 0
        
        for pred_type, required_metrics in patterns.items():
            match_count = sum(1 for metric in required_metrics if metric in metrics)
            
            # Si hay coincidencia total, devolver inmediatamente
            if match_count == len(required_metrics):
                return pred_type
            
            # Si hay coincidencia parcial mejor que la actual
            if match_count > max_match_count and match_count >= 1:
                max_match_count = match_count
                best_match = pred_type
        
        return best_match or "general_failure"
    
    def _predict_for_horizon(self, service_id, data_points, prediction_type, horizon):
        """
        Realiza predicción para un horizonte específico
        
        Args:
            service_id: ID del servicio
            data_points: Lista de puntos de datos
            prediction_type: Tipo de predicción
            horizon: Horizonte de predicción en horas
            
        Returns:
            Dict con resultado o None si no hay modelo
        """
        model_key = f"{service_id}:{prediction_type}:{horizon}"
        
        # Intentar usar modelo específico para el servicio
        model = self.models.get(model_key)
        scaler = self.scalers.get(model_key)
        
        # Si no hay modelo específico, usar modelo genérico
        if not model:
            generic_key = f"generic:{prediction_type}:{horizon}"
            model = self.models.get(generic_key)
            scaler = self.scalers.get(generic_key)
            
            # Si tampoco hay modelo genérico, no podemos predecir
            if not model:
                # Si no tenemos datos suficientes, entrenar nuevo modelo
                if len(data_points) >= max(30, self.sequence_length * 3):
                    # Entrenar en segundo plano para no bloquear
                    self.executor.submit(
                        self._train_new_model,
                        service_id,
                        data_points,
                        prediction_type,
                        horizon
                    )
                
                # Sin modelo, no podemos predecir
                return None
        
        try:
            # Preparar datos para predicción
            X = self._prepare_data_for_prediction(data_points, scaler)
            
            # Realizar predicción según tipo de modelo
            if isinstance(model, tf.keras.Model):
                # Modelo TensorFlow/Keras (LSTM, etc.)
                prediction = model.predict(X)
                
                # Extraer probabilidad
                if prediction.shape[-1] > 1:
                    # Modelo clasificador (one-hot)
                    probability = float(prediction[0][1])  # Probabilidad de clase positiva
                else:
                    # Modelo regresión (0-1)
                    probability = float(prediction[0][0])
                
                model_type = "deep_learning"
                
            elif hasattr(model, "predict_proba"):
                # Modelo scikit-learn con probabilidades
                prediction_proba = model.predict_proba(X)
                probability = float(prediction_proba[0][1])  # Clase positiva
                model_type = "machine_learning"
                
            elif hasattr(model, "predict"):
                # Modelo scikit-learn sin probabilidades
                prediction = model.predict(X)
                
                # Convertir a probabilidad aproximada
                if prediction[0] > 0.5:
                    probability = min(1.0, prediction[0])
                else:
                    probability = max(0.0, prediction[0])
                
                model_type = "machine_learning"
                
            else:
                # Tipo de modelo desconocido
                logger.warning(f"Tipo de modelo desconocido para {model_key}")
                return None
            
            # Construir resultado
            return {
                "probability": probability,
                "prediction_horizon": horizon,
                "model_key": model_key,
                "model_type": model_type
            }
            
        except Exception as e:
            logger.error(f"Error al predecir con modelo {model_key}: {str(e)}")
            return None
    
    def _prepare_data_for_prediction(self, data_points, scaler=None):
        """
        Prepara datos para hacer predicción
        
        Args:
            data_points: Lista de puntos de datos
            scaler: Scaler para normalización (opcional)
            
        Returns:
            Array NumPy con datos preparados
        """
        # Extraer solo métricas numéricas
        numeric_data = []
        for point in data_points[-self.sequence_length:]:
            # Extraer valores numéricos
            values = []
            for k, v in point.items():
                if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float)):
                    values.append(v)
            
            numeric_data.append(values)
        
        # Convertir a array NumPy
        X = np.array(numeric_data)
        
        # Normalizar si hay scaler
        if scaler:
            X = scaler.transform(X)
        
        # Reshape para modelo LSTM si es necesario
        if len(X.shape) == 2:
            # Para modelos LSTM: shape (samples, time_steps, features)
            X = X.reshape(1, X.shape[0], X.shape[1])
        else:
            # Para modelos no secuenciales: shape (samples, features)
            X = X.reshape(1, -1)
        
        return X
    
    def _extract_influential_metrics(self, data_points, prediction_type):
        """
        Extrae métricas influyentes basadas en patrones conocidos
        
        Args:
            data_points: Lista de puntos de datos
            prediction_type: Tipo de predicción
            
        Returns:
            Dict con métricas influyentes
        """
        # Métricas relevantes según tipo de predicción
        relevant_metrics = {
            "memory_failure": ["memory_usage", "gc_collection_time"],
            "cpu_failure": ["cpu_usage", "cpu_throttling", "load_average"],
            "disk_failure": ["disk_usage", "iops", "io_wait"],
            "db_failure": ["active_connections", "connection_wait_time", "query_time"],
            "network_failure": ["network_errors", "packet_loss", "latency"],
            "general_failure": ["cpu_usage", "memory_usage", "response_time_ms"]
        }
        
        metrics_to_extract = relevant_metrics.get(prediction_type, ["cpu_usage", "memory_usage"])
        
        # Extraer último punto de datos
        if not data_points:
            return {}
            
        last_point = data_points[-1]
        
        # Extraer métricas relevantes
        result = {}
        for metric in metrics_to_extract:
            if metric in last_point and isinstance(last_point[metric], (int, float)):
                result[metric] = last_point[metric]
        
        return result
    
    def _register_prediction(self, service_id, prediction_result):
        """
        Registra una predicción en el histórico para validación futura
        
        Args:
            service_id: ID del servicio
            prediction_result: Resultado de la predicción
        """
        # Crear clave única para la predicción
        prediction_id = f"{service_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        horizon = prediction_result.get("prediction_horizon", 24)
        
        # Almacenar predicción
        self.prediction_history[prediction_id] = {
            "service_id": service_id,
            "prediction": prediction_result.get("prediction", False),
            "probability": prediction_result.get("probability", 0),
            "prediction_horizon": horizon,
            "prediction_type": prediction_result.get("prediction_type", "unknown"),
            "prediction_time": datetime.now().isoformat(),
            "validation_time": (datetime.now() + timedelta(hours=horizon)).isoformat(),
            "validated": False,
            "was_correct": None
        }
        
        # Limitar tamaño del histórico
        if len(self.prediction_history) > 1000:
            # Eliminar entradas más antiguas
            keys_to_remove = sorted(self.prediction_history.keys())[:100]
            for key in keys_to_remove:
                del self.prediction_history[key]
    
    def validate_predictions(self, service_id, had_failure):
        """
        Valida predicciones anteriores cuando ocurre un fallo
        
        Args:
            service_id: ID del servicio
            had_failure: Si ocurrió un fallo
            
        Returns:
            Dict con estadísticas de validación
        """
        current_time = datetime.now()
        validated_count = 0
        correct_count = 0
        
        for pred_id, pred_data in self.prediction_history.items():
            # Solo validar predicciones para este servicio que no estén validadas
            if pred_data["service_id"] != service_id or pred_data["validated"]:
                continue
            
            # Convertir tiempos a datetime
            prediction_time = datetime.fromisoformat(pred_data["prediction_time"].replace('Z', '+00:00'))
            validation_time = datetime.fromisoformat(pred_data["validation_time"].replace('Z', '+00:00'))
            
            # Si es tiempo de validar (pasó el horizonte de predicción)
            if current_time >= validation_time:
                # Marcar como validada
                pred_data["validated"] = True
                
                # Determinar si la predicción fue correcta
                if had_failure:
                    # Hubo fallo - la predicción es correcta si predijo fallo
                    was_correct = pred_data["prediction"] == True
                else:
                    # No hubo fallo - la predicción es correcta si no predijo fallo
                    was_correct = pred_data["prediction"] == False
                
                pred_data["was_correct"] = was_correct
                pred_data["actual_validation_time"] = current_time.isoformat()
                
                validated_count += 1
                if was_correct:
                    correct_count += 1
        
        # Calcular precisión
        accuracy = correct_count / validated_count if validated_count > 0 else 0
        
        # Actualizar métrica de precisión
        self.metrics.prediction_accuracy.labels(
            service_id=service_id,
            prediction_type="all"
        ).set(accuracy)
        
        return {
            "service_id": service_id,
            "validated_count": validated_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
            "timestamp": current_time.isoformat()
        }
    
    def _train_new_model(self, service_id, data_points, prediction_type, horizon):
        """
        Entrena un nuevo modelo para un servicio y tipo de predicción
        
        Args:
            service_id: ID del servicio
            data_points: Lista de puntos de datos históricos
            prediction_type: Tipo de predicción
            horizon: Horizonte de predicción en horas
        """
        try:
            logger.info(f"Entrenando nuevo modelo para {service_id} - {prediction_type} - {horizon}h")
            
            # En una implementación real, aquí habría código para:
            # 1. Preparar datos de entrenamiento
            # 2. Entrenar un modelo LSTM o similar
            # 3. Guardar modelo y scaler
            # 4. Actualizar diccionarios de modelos y scalers
            
            # Para esta demo, simulamos entrenamiento
            logger.info(f"Entrenamiento simulado completado para {service_id}")
            
            # En implementación real se reemplazaría por un entrenamiento real
            
        except Exception as e:
            logger.error(f"Error al entrenar modelo: {str(e)}")
    
    def get_prediction_accuracy(self, service_id=None):
        """
        Obtiene estadísticas de precisión de predicciones
        
        Args:
            service_id: ID del servicio (opcional)
            
        Returns:
            Dict con estadísticas de precisión
        """
        # Filtrar predicciones validadas
        validated_predictions = [
            p for p in self.prediction_history.values()
            if p["validated"] and (service_id is None or p["service_id"] == service_id)
        ]
        
        if not validated_predictions:
            return {
                "service_id": service_id,
                "accuracy": 0,
                "count": 0,
                "message": "No hay predicciones validadas"
            }
        
        # Calcular estadísticas
        total = len(validated_predictions)
        correct = sum(1 for p in validated_predictions if p["was_correct"])
        accuracy = correct / total if total > 0 else 0
        
        # Desglosar por tipo de predicción
        by_type = {}
        for p in validated_predictions:
            pred_type = p["prediction_type"]
            if pred_type not in by_type:
                by_type[pred_type] = {"total": 0, "correct": 0}
            by_type[pred_type]["total"] += 1
            if p["was_correct"]:
                by_type[pred_type]["correct"] += 1
        
        # Calcular precisión por tipo
        for pred_type, stats in by_type.items():
            stats["accuracy"] = stats["correct"] / stats["total"] if stats["total"] > 0 else 0
        
        return {
            "service_id": service_id,
            "accuracy": accuracy,
            "count": total,
            "correct": correct,
            "by_type": by_type,
            "timestamp": datetime.now().isoformat()
        }