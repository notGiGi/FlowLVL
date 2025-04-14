# simplified_predictive_engine.py
import numpy as np
import pandas as pd
import random
import json
import logging
from datetime import datetime, timedelta

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('predictive_engine')

class PredictiveEngine:
    """Motor predictivo simplificado para pruebas"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.prediction_threshold = self.config.get('prediction_threshold', 0.7)
        logger.info("Motor predictivo (simplificado) inicializado")
    
    def predict_failures(self, service_id, data, horizon_hours=None):
        """Simula predicción de fallos basada en métricas clave"""
        try:
            # Para demo, hacemos que prediga fallos basado en tendencias simples
            if isinstance(data, list) and len(data) >= 3:
                # Analizar tendencia de memory_usage
                memory_values = []
                for item in data:
                    if isinstance(item, dict) and 'memory_usage' in item:
                        memory_values.append(item['memory_usage'])
                
                # Si tenemos suficientes valores, calcular tendencia
                if len(memory_values) >= 3:
                    # Calcular pendiente simplificada
                    trend = (memory_values[-1] - memory_values[0]) / len(memory_values)
                    
                    # Hacer predicción basada en tendencia
                    predicted_value = memory_values[-1] + (trend * 3)  # Proyección a 3 unidades de tiempo
                    
                    # Calcular probabilidad (más alta si proyección > 85%)
                    probability = min(1.0, max(0.0, (predicted_value - 70) / 30))
                    
                    # Determinar horizonte de predicción
                    if probability > 0.8:
                        prediction_horizon = 2  # Horizonte corto si alta probabilidad
                    else:
                        prediction_horizon = 6  # Horizonte largo si baja probabilidad
                    
                    # Determinar si hay predicción de fallo
                    prediction = probability >= self.prediction_threshold
                    
                    result = {
                        'service_id': service_id,
                        'timestamp': datetime.now().isoformat(),
                        'prediction': prediction,
                        'probability': float(probability),
                        'prediction_horizon': prediction_horizon,
                        'predicted_failure_time': (datetime.now() + timedelta(hours=prediction_horizon)).isoformat() if prediction else None,
                        'confidence': 'high' if probability > 0.85 else 'medium' if probability > 0.7 else 'low',
                        'influential_metrics': {
                            'memory_usage': float(memory_values[-1]),
                            'memory_trend': float(trend)
                        }
                    }
                    
                    return result
            
            # Valor por defecto si no hay suficientes datos
            return {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction': False,
                'probability': 0.0,
                'error': 'Datos insuficientes para predicción'
            }
                
        except Exception as e:
            logger.error(f"Error al predecir fallos: {str(e)}")
            return {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction': False,
                'probability': 0.0,
                'error': str(e)
            }
