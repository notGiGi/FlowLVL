# -*- coding: utf-8 -*-
import json
import os
import logging
import re
from datetime import datetime
import subprocess
import requests

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("action_recommender.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('simple_recommender')

class SimpleActionRecommender:
    """Recomendador de acciones simplificado para prueba real"""
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Cargar políticas de acción
        self.config_dir = self.config.get('config_dir', './config')
        self.action_policies = self.load_action_policies()
        
        # Historial de acciones
        self.action_history = []
        self.max_history = self.config.get('max_history_items', 100)
        
        # Modo de ejecución (real o simulación)
        self.execution_mode = self.config.get('execution_mode', 'simulation')
        
        logger.info(f"Recomendador de acciones simple inicializado (modo: {self.execution_mode})")
    
    def load_action_policies(self):
        """Carga políticas de acción desde archivo JSON"""
        try:
            policy_file = os.path.join(self.config_dir, 'action_policies.json')
            
            if os.path.exists(policy_file):
                with open(policy_file, 'r') as f:
                    policies = json.load(f)
                logger.info(f"Políticas de acción cargadas: {len(policies)} servicios")
                return policies
            else:
                logger.warning("Archivo de políticas no encontrado, usando valores por defecto")
                return self.get_default_policies()
                
        except Exception as e:
            logger.error(f"Error al cargar políticas: {str(e)}")
            return self.get_default_policies()
    
    def get_default_policies(self):
        """Devuelve políticas por defecto"""
        return {
            "generic_web_service": {
                "description": "Acciones para servicios web genéricos",
                "actions": {
                    "memory_restart": {
                        "description": "Reinicia el servicio para resolver problemas de memoria",
                        "remediation": {
                            "type": "command",
                            "command": "kubectl rollout restart deployment ${service_id}"
                        },
                        "conditions": {
                            "metrics": {
                                "memory_usage": "> 80"
                            },
                            "anomaly_score": "> 0.6"
                        },
                        "priority": "high"
                    },
                    "cpu_scale_up": {
                        "description": "Escala el servicio horizontalmente",
                        "remediation": {
                            "type": "command",
                            "command": "kubectl scale deployment ${service_id} --replicas=$(kubectl get deployment ${service_id} -o=jsonpath='{.spec.replicas}'+1)"
                        },
                        "conditions": {
                            "metrics": {
                                "cpu_usage": "> 80"
                            },
                            "anomaly_score": "> 0.6"
                        },
                        "priority": "medium"
                    }
                }
            },
            "generic_database": {
                "description": "Acciones para bases de datos genéricas",
                "actions": {
                    "connection_pool_increase": {
                        "description": "Aumenta el pool de conexiones",
                        "remediation": {
                            "type": "command",
                            "command": "kubectl exec ${service_id}-0 -- psql -c \"ALTER SYSTEM SET max_connections = ${max_connections}; SELECT pg_reload_conf();\""
                        },
                        "conditions": {
                            "metrics": {
                                "active_connections": "> 70",
                                "connection_wait_time": "> 100"
                            },
                            "anomaly_score": "> 0.6"
                        },
                        "parameters": {
                            "max_connections": "200"
                        },
                        "priority": "high"
                    }
                }
            }
        }
    
    def check_condition(self, condition, metrics):
        """Verifica si una condición se cumple con las métricas dadas"""
        try:
            # Extraer el nombre de la métrica y el valor umbral
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
            if operator == '>':
                return metric_value > threshold
            elif operator == '>=':
                return metric_value >= threshold
            elif operator == '<':
                return metric_value < threshold
            elif operator == '<=':
                return metric_value <= threshold
            elif operator == '==':
                return metric_value == threshold
            elif operator == '!=':
                return metric_value != threshold
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error al verificar condición {condition}: {str(e)}")
            return False
    
    def check_conditions(self, conditions, metrics):
        """Verifica si todas las condiciones se cumplen"""
        # Verificar métricas
        if 'metrics' in conditions:
            metrics_conditions_met = 0
            total_metrics_conditions = len(conditions['metrics'])
            
            for metric, condition in conditions['metrics'].items():
                full_condition = f"{metric} {condition}"
                if self.check_condition(full_condition, metrics):
                    metrics_conditions_met += 1
            
            # Al menos 70% de condiciones métricas deben cumplirse
            if metrics_conditions_met / total_metrics_conditions < 0.7:
                return False
        
        # Verificar anomaly_score si está presente
        if 'anomaly_score' in conditions and 'anomaly_score' in metrics:
            if not self.check_condition(f"anomaly_score {conditions['anomaly_score']}", metrics):
                return False
        
        # Verificar failure_probability si está presente
        if 'failure_probability' in conditions and 'failure_probability' in metrics:
            if not self.check_condition(f"failure_probability {conditions['failure_probability']}", metrics):
                return False
        
        # Todas las condiciones cumplidas
        return True
    
    def find_matching_actions(self, service_id, metrics):
        """Encuentra acciones que coinciden con las métricas actuales"""
        matching_actions = []
        
        # Verificar si tenemos políticas para este servicio
        if service_id in self.action_policies:
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
        
        # Si no hay acciones específicas para este servicio, buscar genéricas
        if not matching_actions:
            # Determinar tipo de servicio por métricas
            service_type = self._get_service_type(metrics)
            generic_id = f"generic_{service_type}"
            
            if generic_id in self.action_policies:
                generic_actions = self.action_policies[generic_id].get('actions', {})
                
                # Verificar cada acción
                for action_id, action_def in generic_actions.items():
                    if 'conditions' in action_def:
                        if self.check_conditions(action_def['conditions'], metrics):
                            # Crear copia de la acción
                            action = action_def.copy()
                            action['action_id'] = action_id
                            action['service_id'] = service_id  # Usar el ID real
                            action['is_generic'] = True
                            
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
    
    def _get_service_type(self, metrics):
        """Determina tipo de servicio basado en métricas disponibles"""
        # Verificar si hay métricas específicas de bases de datos
        if any(m in metrics for m in ['active_connections', 'query_time_avg', 'connection_wait_time']):
            return 'database'
        
        # Verificar si hay métricas específicas de Redis/caché
        if any(m in metrics for m in ['memory_fragmentation_ratio', 'hit_rate', 'eviction_rate']):
            return 'cache'
        
        # Por defecto, asumir servicio web
        return 'web_service'
    
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
        """Ejecuta una acción correctiva"""
        if not action:
            logger.warning("No se proporcionó acción para ejecutar")
            return False
        
        # Extraer información
        action_id = action.get('action_id', 'unknown_action')
        service_id = action.get('service_id', 'unknown_service')
        
        # Obtener detalles de remediación
        remediation = action.get('remediation', {})
        remediation_type = remediation.get('type', 'command')
        
        # Verificar modo de ejecución
        logger.info(f"Ejecutando acción {action_id} para {service_id} (modo: {self.execution_mode})")
        
        # Guardar en historial
        history_item = {
            'action_id': action_id,
            'service_id': service_id,
            'timestamp': datetime.now().isoformat(),
            'execution_mode': self.execution_mode,
            'metrics_before': metrics,
            'success': False
        }
        
        try:
            if self.execution_mode == 'simulation':
                # En modo simulación, solo registrar la acción
                logger.info(f"[SIMULACIÓN] {remediation_type}: {remediation}")
                
                # Marcar como éxito en simulación
                history_item['success'] = True
                history_item['simulation'] = True
                
                self._add_to_history(history_item)
                return True
            
            elif self.execution_mode == 'real':
                # En modo real, ejecutar la acción
                if remediation_type == 'command':
                    # Ejecutar comando
                    command = remediation.get('command', '')
                    command = self._substitute_variables(command, action, metrics)
                    
                    logger.info(f"Ejecutando comando: {command}")
                    
                    # Ejecutar comando
                    process = subprocess.Popen(
                        command,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True
                    )
                    
                    # Esperar con timeout
                    stdout, stderr = process.communicate(timeout=30)
                    
                    success = process.returncode == 0
                    
                    history_item['success'] = success
                    history_item['stdout'] = stdout
                    history_item['stderr'] = stderr
                    
                    self._add_to_history(history_item)
                    
                    if success:
                        logger.info(f"Comando ejecutado exitosamente")
                        return True
                    else:
                        logger.error(f"Error al ejecutar comando: {stderr}")
                        return False
                
                elif remediation_type == 'api':
                    # Llamar a API
                    endpoint = remediation.get('endpoint', '')
                    endpoint = self._substitute_variables(endpoint, action, metrics)
                    
                    method = remediation.get('method', 'POST')
                    headers = remediation.get('headers', {})
                    payload = remediation.get('payload', {})
                    
                    # Sustituir variables en headers y payload
                    processed_headers = {}
                    for key, value in headers.items():
                        processed_headers[key] = self._substitute_variables(value, action, metrics)
                    
                    processed_payload = {}
                    for key, value in payload.items():
                        if isinstance(value, str):
                            processed_payload[key] = self._substitute_variables(value, action, metrics)
                        else:
                            processed_payload[key] = value
                    
                    logger.info(f"Llamando API: {method} {endpoint}")
                    
                    # Realizar solicitud
                    response = requests.request(
                        method,
                        endpoint,
                        headers=processed_headers,
                        json=processed_payload,
                        timeout=10
                    )
                    
                    success = 200 <= response.status_code < 300
                    
                    history_item['success'] = success
                    history_item['status_code'] = response.status_code
                    history_item['response'] = response.text[:500]
                    
                    self._add_to_history(history_item)
                    
                    if success:
                        logger.info(f"API respondió correctamente: {response.status_code}")
                        return True
                    else:
                        logger.error(f"Error en respuesta API: {response.status_code}")
                        return False
                
                else:
                    logger.error(f"Tipo de remediación desconocido: {remediation_type}")
                    return False
            
            else:
                logger.error(f"Modo de ejecución desconocido: {self.execution_mode}")
                return False
                
        except Exception as e:
            logger.error(f"Error al ejecutar acción: {str(e)}")
            
            # Actualizar entrada de historial
            history_item['success'] = False
            history_item['error'] = str(e)
            self._add_to_history(history_item)
            
            return False
    
    def _substitute_variables(self, template, action, context):
        """Sustituye variables en una plantilla"""
        if not template or not isinstance(template, str):
            return template
            
        result = template
        
        # Sustituir variables de acción
        replacements = {
            "${service_id}": action.get('service_id', ''),
            "${action_id}": action.get('action_id', '')
        }
        
        # Añadir parámetros de la acción
        params = action.get('parameters', {})
        for param_name, param_value in params.items():
            replacements[f"${{{param_name}}}"] = str(param_value)
        
        # Añadir variables de contexto
        for key, value in context.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[f"${{{key}}}"] = str(value)
        
        # Realizar sustituciones
        for var, value in replacements.items():
            result = result.replace(var, value)
        
        return result
    
    def _add_to_history(self, item):
        """Añade una acción al historial"""
        self.action_history.append(item)
        
        # Limitar tamaño del historial
        if len(self.action_history) > self.max_history:
            self.action_history = self.action_history[-self.max_history:]
    
    def get_action_history(self, service_id=None, limit=10):
        """Obtiene historial de acciones"""
        if service_id:
            # Filtrar por servicio
            filtered_history = [
                item for item in self.action_history
                if item['service_id'] == service_id
            ]
        else:
            filtered_history = self.action_history
        
        # Ordenar por más reciente primero
        sorted_history = sorted(
            filtered_history,
            key=lambda x: x.get('timestamp', ''),
            reverse=True
        )
        
        return sorted_history[:limit]
    
    def set_execution_mode(self, mode):
        """Establece el modo de ejecución (simulation o real)"""
        if mode in ['simulation', 'real']:
            self.execution_mode = mode
            logger.info(f"Modo de ejecución cambiado a: {mode}")
            return True
        else:
            logger.error(f"Modo de ejecución inválido: {mode}")
            return False

# Script principal
if __name__ == "__main__":
    recommender = SimpleActionRecommender()
    
    # Ejemplo de recomendación
    test_anomaly = {
        "service_id": "test-service",
        "anomaly_score": 0.8,
        "details": {
            "metrics": {
                "memory_usage": 85,
                "gc_collection_time": 500
            }
        }
    }
    
    recommendation = recommender.process_and_recommend(anomaly_data=test_anomaly)
    print(json.dumps(recommendation, indent=2))