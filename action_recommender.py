# simplified_action_recommender.py
import numpy as np
import pandas as pd
import random
import json
import logging
import os
import re
from datetime import datetime

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('action_recommender')

class ActionRecommender:
    """Recomendador de acciones simplificado para pruebas"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.config_dir = self.config.get('config_dir', './config')
        
        # Cargar políticas de acción
        self.action_policies = {}
        self.load_action_policies()
        
        logger.info("Recomendador de acciones (simplificado) inicializado")
    
    def load_action_policies(self):
        """Carga políticas de acción desde archivo JSON"""
        try:
            policy_file = os.path.join(self.config_dir, 'action_policies.json')
            
            if os.path.exists(policy_file):
                with open(policy_file, 'r') as f:
                    self.action_policies = json.load(f)
                logger.info(f"Políticas de acción cargadas: {len(self.action_policies)} servicios")
            else:
                logger.warning("Archivo de políticas no encontrado, usando valores por defecto")
                self.load_default_policies()
        except Exception as e:
            logger.error(f"Error al cargar políticas: {str(e)}")
            self.load_default_policies()
    
    def load_default_policies(self):
        """Carga políticas por defecto si no hay archivo"""
        self.action_policies = {
            "order-processing-service": {
                "description": "Acciones para el servicio de procesamiento de órdenes",
                "actions": {
                    "memory_leak_restart": {
                        "description": "Reinicia el servicio para resolver fuga de memoria",
                        "command": "kubectl rollout restart deployment ${service_id}",
                        "conditions": {
                            "metrics": {
                                "memory_usage": "> 70",
                                "gc_collection_time": "> 500"
                            },
                            "anomaly_score": "> 0.7"
                        },
                        "priority": "high"
                    }
                }
            }
        }
    
    def check_condition(self, condition, metrics):
        """Verifica si una condición se cumple con las métricas dadas"""
        try:
            # Extrae el nombre de la métrica y el valor umbral
            matches = re.match(r'([a-zA-Z_]+)\s*([<>=!]+)\s*(.+)', condition)
            if not matches:
                return False
            
            metric_name, operator, threshold = matches.groups()
            
            # Obtener valor de la métrica
            if metric_name not in metrics:
                return False
            
            metric_value = metrics[metric_name]
            
            # Convertir threshold a número si es posible
            try:
                threshold = float(threshold)
            except ValueError:
                pass
            
            # Evaluar condición
            if operator == '==':
                return metric_value == threshold
            elif operator == '!=':
                return metric_value != threshold
            elif operator == '>':
                return metric_value > threshold
            elif operator == '>=':
                return metric_value >= threshold
            elif operator == '<':
                return metric_value < threshold
            elif operator == '<=':
                return metric_value <= threshold
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error al verificar condición {condition}: {str(e)}")
            return False
    
    def check_conditions(self, conditions, metrics):
        """Verifica si todas las condiciones se cumplen"""
        # Verificar métricas
        if 'metrics' in conditions:
            for metric, condition in conditions['metrics'].items():
                full_condition = f"{metric} {condition}"
                if not self.check_condition(full_condition, metrics):
                    return False
        
        # Verificar anomaly_score si está presente
        if 'anomaly_score' in conditions and 'anomaly_score' in metrics:
            if not self.check_condition(
                f"anomaly_score {conditions['anomaly_score']}", metrics
            ):
                return False
        
        # Verificar failure_probability si está presente
        if 'failure_probability' in conditions and 'failure_probability' in metrics:
            if not self.check_condition(
                f"failure_probability {conditions['failure_probability']}", metrics
            ):
                return False
        
        # Todas las condiciones cumplidas
        return True
    
    def find_matching_actions(self, service_id, metrics):
        """Encuentra acciones que coinciden con las métricas actuales"""
        matching_actions = []
        
        # Verificar si tenemos políticas para este servicio
        if service_id not in self.action_policies:
            logger.warning(f"No hay políticas definidas para {service_id}")
            return []
        
        # Obtener acciones para este servicio
        service_actions = self.action_policies[service_id].get('actions', {})
        
        # Verificar cada acción
        for action_id, action_def in service_actions.items():
            # Verificar condiciones
            if 'conditions' in action_def:
                if self.check_conditions(action_def['conditions'], metrics):
                    # Crear copia de la acción
                    action = action_def.copy()
                    action['action_id'] = action_id
                    action['service_id'] = service_id
                    
                    # Añadir a lista de coincidentes
                    matching_actions.append(action)
        
        # Ordenar por prioridad
        priority_map = {
            'critical': 0,
            'high': 1,
            'medium': 2,
            'low': 3
        }
        
        matching_actions.sort(
            key=lambda x: priority_map.get(x.get('priority', 'medium'), 2)
        )
        
        return matching_actions
    
    def process_and_recommend(self, anomaly_data=None, prediction_data=None):
        """Procesa datos de anomalías o predicciones y recomienda acciones"""
        try:
            # Determinar tipo de entrada
            if anomaly_data:
                # Procesar anomalía
                service_id = anomaly_data.get('service_id', 'unknown_service')
                metrics = anomaly_data.get('details', {}).get('metrics', {})
                metrics['anomaly_score'] = anomaly_data.get('anomaly_score', 0)
                
                # Recomendar acción
                recommended_action = self.recommend_action(service_id, metrics, 'anomaly')
                
                if recommended_action:
                    return {
                        'service_id': service_id,
                        'timestamp': datetime.now().isoformat(),
                        'recommendation_type': 'anomaly',
                        'anomaly_score': anomaly_data.get('anomaly_score', 0),
                        'recommended_action': recommended_action,
                        'metrics': metrics
                    }
            
            elif prediction_data:
                # Procesar predicción
                service_id = prediction_data.get('service_id', 'unknown_service')
                metrics = prediction_data.get('influential_metrics', {})
                metrics['failure_probability'] = prediction_data.get('probability', 0)
                
                # Recomendar acción
                recommended_action = self.recommend_action(service_id, metrics, 'prediction')
                
                if recommended_action:
                    return {
                        'service_id': service_id,
                        'timestamp': datetime.now().isoformat(),
                        'recommendation_type': 'prediction',
                        'failure_probability': prediction_data.get('probability', 0),
                        'prediction_horizon': prediction_data.get('prediction_horizon', 24),
                        'recommended_action': recommended_action,
                        'metrics': metrics
                    }
            
            return {
                'error': 'No se proporcionaron datos de anomalía o predicción',
                'timestamp': datetime.now().isoformat()
            }
                
        except Exception as e:
            logger.error(f"Error en process_and_recommend: {str(e)}")
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def recommend_action(self, service_id, metrics, issue_type):
        """Recomienda la mejor acción para un problema detectado"""
        try:
            logger.info(f"Buscando acción para {service_id} con issue_type={issue_type}")
            
            # Encontrar acciones que coinciden con las métricas
            matching_actions = self.find_matching_actions(service_id, metrics)
            
            if not matching_actions:
                logger.warning(f"No hay acciones disponibles para {service_id}")
                return None
            
            # Devolver la primera acción coincidente (la de mayor prioridad según el ordenamiento)
            return matching_actions[0]
                
        except Exception as e:
            logger.error(f"Error al recomendar acción: {str(e)}")
            return None
    
    def execute_action(self, action, metrics):
        """Simula la ejecución de una acción correctiva"""
        if not action:
            logger.warning("No se proporcionó acción para ejecutar")
            return False
        
        # Extraer información
        action_id = action.get('action_id', 'unknown_action')
        service_id = action.get('service_id', 'unknown_service')
        command = action.get('command', '')
        
        logger.info(f"Ejecutando acción {action_id} para {service_id}: {command}")
        
        # Simular éxito
        success = True
        
        if success:
            logger.info(f"Acción {action_id} ejecutada exitosamente")
        else:
            logger.error(f"Error al ejecutar acción {action_id}")
        
        return success
