# anomaly_detector/ensemble_models.py

import numpy as np
import logging
import joblib
from sklearn.ensemble import IsolationForest
from tensorflow.keras.models import Model, load_model
from sklearn.metrics import roc_auc_score
from scipy.stats import hmean

logger = logging.getLogger('anomaly_detector.ensemble')

class AdaptiveEnsembleDetector:
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
        """
        Inicializa los modelos basados en la configuración proporcionada
        """
        for config in models_config:
            model_type = config.get('type')
            model_id = config.get('id')
            model_path = config.get('path')
            
            try:
                if model_type == 'isolation_forest':
                    self.models[model_id] = joblib.load(model_path)
                elif model_type == 'autoencoder':
                    self.models[model_id] = load_model(model_path)
                # Añadir soporte para otros tipos de modelos aquí
                
                # Inicializar peso igual para todos los modelos
                self.model_weights[model_id] = config.get('initial_weight', self.default_weight)
                self.performance_history[model_id] = []
                
                logger.info(f"Modelo {model_id} ({model_type}) cargado correctamente")
            except Exception as e:
                logger.error(f"Error al cargar modelo {model_id}: {str(e)}")
    
    def add_model(self, model_id, model, model_type, initial_weight=1.0):
        """
        Añade un modelo al ensamble
        """
        self.models[model_id] = model
        self.model_weights[model_id] = initial_weight
        self.performance_history[model_id] = []
        logger.info(f"Modelo {model_id} añadido al ensamble con peso {initial_weight}")
    
    def remove_model(self, model_id):
        """
        Elimina un modelo del ensamble
        """
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
                if isinstance(model, IsolationForest):
                    # Para Isolation Forest
                    raw_score = model.decision_function([data])[0]
                    # Convertir a score de anomalía (más alto = más anómalo)
                    score = 1.0 - ((raw_score + 1.0) / 2.0)
                    confidence = min(max(0.5 + abs(raw_score) / 2, 0.5), 1.0)
                elif "autoencoder" in model_id.lower():
                    # Para Autoencoder
                    prediction = model.predict(np.array([data]))
                    mse = np.mean(np.square(np.array([data]) - prediction))
                    # Normalizar score (asumiendo que MSE > 0.1 es anómalo)
                    score = min(mse / 0.1, 1.0)
                    confidence = min(max(0.5 + (score - 0.5) * 2, 0.5), 1.0) if score > 0.5 else max(0.5 - (0.5 - score) * 2, 0.1)
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