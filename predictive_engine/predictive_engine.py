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
        self.prediction_threshold = self.config.get('prediction_threshold', 0.6)  # Umbral reducido
        logger.info("Motor predictivo (simplificado) inicializado")
    
    def predict_failures(self, service_id, data, horizon_hours=None):
        """Simula predicción de fallos basada en métricas clave y tendencias"""
        try:
            # Para demo, hacemos que prediga fallos basado en tendencias
            if isinstance(data, list) and len(data) >= 3:
                # Analizar tendencia de memory_usage y GC time
                memory_values = []
                gc_values = []
                for item in data:
                    if isinstance(item, dict):
                        if 'memory_usage' in item:
                            memory_values.append(item['memory_usage'])
                        if 'gc_collection_time' in item:
                            gc_values.append(item['gc_collection_time'])
                
                # Si tenemos suficientes valores, calcular tendencia
                if len(memory_values) >= 3 and len(gc_values) >= 3:
                    # Calcular pendiente para memoria
                    memory_trend = (memory_values[-1] - memory_values[0]) / len(memory_values)
                    gc_trend = (gc_values[-1] - gc_values[0]) / len(gc_values)
                    
                    # Hacer predicción basada en ambas tendencias
                    memory_projected = memory_values[-1] + (memory_trend * 3)
                    gc_projected = gc_values[-1] + (gc_trend * 3)
                    
                    # Combinar probabilidades (mayor peso a memoria)
                    memory_prob = min(1.0, max(0.0, (memory_projected - 65) / 35))
                    gc_prob = min(1.0, max(0.0, (gc_projected - 300) / 700))
                    
                    probability = 0.7*memory_prob + 0.3*gc_prob
                    
                    # Determinar horizonte de predicción
                    if probability > 0.8:
                        prediction_horizon = 1  # Horizonte corto si alta probabilidad
                    else:
                        prediction_horizon = 4  # Horizonte medio
                    
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
                            'memory_trend': float(memory_trend),
                            'gc_collection_time': float(gc_values[-1]),
                            'gc_trend': float(gc_trend)
                        }
                    }
                    
                    return result
            
            # Valor por defecto si no hay suficientes datos
            return {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction': False,
                'probability': 0.0,
                'reason': 'Datos insuficientes para predicción'
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