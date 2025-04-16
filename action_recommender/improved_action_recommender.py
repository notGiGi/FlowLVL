import numpy as np
import pandas as pd
import logging
import json
import os
import re
from datetime import datetime
import traceback

from utils.retry import retry_with_backoff
from utils.metrics import MetricsCollector
from utils.distributed_cache import DistributedCache, cached
from monitoring.service_profiler import ServiceProfiler
from action_recommender.action_orchestrator import ActionOrchestrator

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('action_recommender')

class ImprovedActionRecommender:
    """
    Recomendador de acciones mejorado que utiliza un enfoque basado en aprendizaje
    para determinar las mejores acciones correctivas para cada servicio y situación.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.config_dir = self.config.get('config_dir', './config')
        
        # Componentes complementarios
        self.service_profiler = ServiceProfiler(config=self.config)
        self.orchestrator = ActionOrchestrator(config=self.config)
        self.metrics = MetricsCollector(config=self.config)
        
        # Caché distribuida para resultados
        self.cache = DistributedCache(
            redis_host=self.config.get('redis_host', 'localhost'),
            redis_port=self.config.get('redis_port', 6379)
        )
        
        # Cargar políticas de acción
        self.action_policies = {}
        self.load_action_policies()
        
        # Histórico de efectividad de acciones
        self.action_effectiveness = {}
        self.load_action_effectiveness()
        
        # Mapa de situaciones a tipos de problema
        self.situation_type_map = {
            # Patrones de anomalías -> tipo de problema
            "memory_leak": "memory_issue",
            "gc_pressure": "memory_issue",
            "memory_fragmentation": "memory_issue",
            "high_cpu": "performance_issue",
            "high_latency": "performance_issue",
            "db_overload": "database_issue",
            "connection_pool_exhaustion": "database_issue",
            "disk_space_low": "storage_issue",
            "io_bottleneck": "storage_issue",
            "network_saturation": "network_issue",
            "connection_errors": "network_issue"
        }
        
        logger.info("Recomendador de acciones mejorado inicializado")
    
    def load_action_policies(self):
        """Carga políticas de acción desde archivo JSON o directorio YAML"""
        try:
            policy_file = os.path.join(self.config_dir, 'action_policies.json')
            
            if os.path.exists(policy_file):
                with open(policy_file, 'r') as f:
                    self.action_policies = json.load(f)
                logger.info(f"Políticas de acción cargadas: {len(self.action_policies)} servicios")
            else:
                logger.warning("Archivo de políticas no encontrado, usando valores por defecto")
                self.load_default_policies()
                
            # Validar políticas
            self._validate_policies()
                
        except Exception as e:
            logger.error(f"Error al cargar políticas: {str(e)}")
            logger.error(traceback.format_exc())
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
                                "memory_usage": "> 65",
                                "gc_collection_time": "> 400"
                            },
                            "anomaly_score": "> 0.5"
                        },
                        "priority": "high"
                    }
                }
            },
            "postgres-main": {
                "description": "Acciones para servicios PostgreSQL",
                "actions": {
                    "connection_pool_increase": {
                        "description": "Aumenta el pool de conexiones",
                        "command": "kubectl exec ${service_id}-0 -- psql -c \"ALTER SYSTEM SET max_connections = ${max_connections}; SELECT pg_reload_conf();\"",
                        "conditions": {
                            "metrics": {
                                "active_connections": "> 70",
                                "connection_wait_time": "> 100"
                            },
                            "anomaly_score": "> 0.3"
                        },
                        "parameters": {
                            "max_connections": "200"
                        },
                        "priority": "high"
                    }
                }
            },
            "redis-cache-01": {
                "description": "Acciones para servicios Redis",
                "actions": {
                    "redis_memory_purge": {
                        "description": "Purga de memoria de Redis",
                        "command": "kubectl exec ${service_id}-0 -- redis-cli MEMORY PURGE",
                        "conditions": {
                            "metrics": {
                                "memory_fragmentation_ratio": "> 1.8"
                            },
                            "anomaly_score": "> 0.3"
                        },
                        "priority": "high"
                    }
                }
            },
            # Añadir políticas genéricas para diferentes tipos de servicio
            "default_web_service": {
                "description": "Acciones genéricas para servicios web",
                "actions": {
                    "scale_up": {
                        "description": "Escala horizontalmente el servicio",
                        "command": "kubectl scale deployment ${service_id} --replicas=$(kubectl get deployment ${service_id} -o=jsonpath='{.spec.replicas}'+1)",
                        "conditions": {
                            "metrics": {
                                "cpu_usage": "> 80",
                                "response_time_ms": "> 500"
                            },
                            "anomaly_score": "> 0.6"
                        },
                        "priority": "medium"
                    },
                    "memory_restart": {
                        "description": "Reinicia el servicio por problemas de memoria",
                        "command": "kubectl rollout restart deployment ${service_id}",
                        "conditions": {
                            "metrics": {
                                "memory_usage": "> 80"
                            },
                            "anomaly_score": "> 0.7"
                        },
                        "priority": "high"
                    }
                }
            },
            "default_database": {
                "description": "Acciones genéricas para bases de datos",
                "actions": {
                    "vacuum_analyze": {
                        "description": "Ejecuta vacuum analyze",
                        "command": "kubectl exec ${service_id}-0 -- psql -c 'VACUUM ANALYZE;'",
                        "conditions": {
                            "metrics": {
                                "query_time_avg": "> 500",
                                "index_bloat": "> 30"
                            },
                            "anomaly_score": "> 0.5"
                        },
                        "priority": "low"
                    }
                }
            }
        }
    
    def _validate_policies(self):
        """Valida y estandariza las políticas cargadas"""
        for service_id, service_policy in self.action_policies.items():
            if not isinstance(service_policy, dict):
                logger.warning(f"Política inválida para {service_id}, no es un diccionario")
                continue
                
            # Asegurar que existe la sección de acciones
            if 'actions' not in service_policy:
                service_policy['actions'] = {}
                
            # Validar cada acción
            for action_id, action in service_policy.get('actions', {}).items():
                # Verificar campos requeridos
                if 'command' not in action and 'remediation' not in action:
                    logger.warning(f"Acción {action_id} en {service_id} no tiene comando o remediación")
                    
                # Mover comando a formato estándar si es necesario
                if 'command' in action and 'remediation' not in action:
                    action['remediation'] = {
                        'type': 'command',
                        'command': action['command']
                    }
                
                # Asegurar que existe sección de condiciones
                if 'conditions' not in action:
                    action['conditions'] = {}
                    
                # Estandarizar prioridad
                if 'priority' not in action:
                    action['priority'] = 'medium'
    
    def load_action_effectiveness(self):
        """Carga historial de efectividad de acciones desde archivo"""
        effectiveness_file = os.path.join(self.config_dir, 'action_effectiveness.json')
        
        if os.path.exists(effectiveness_file):
            try:
                with open(effectiveness_file, 'r') as f:
                    self.action_effectiveness = json.load(f)
                logger.info(f"Efectividad de acciones cargada: {len(self.action_effectiveness)} registros")
            except Exception as e:
                logger.error(f"Error al cargar efectividad: {str(e)}")
                self.action_effectiveness = {}
    
    def save_action_effectiveness(self):
        """Guarda historial de efectividad de acciones en archivo"""
        effectiveness_file = os.path.join(self.config_dir, 'action_effectiveness.json')
        
        try:
            with open(effectiveness_file, 'w') as f:
                json.dump(self.action_effectiveness, f, indent=2)
            logger.info("Efectividad de acciones guardada")
        except Exception as e:
            logger.error(f"Error al guardar efectividad: {str(e)}")
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
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
            
            # Evaluar condición con margen de tolerancia (10%)
            if operator == '>':
                tolerance = threshold * 0.1 if isinstance(threshold, (int, float)) else 0
                return metric_value > (threshold - tolerance)
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
        
        # Verificar issue_type si está presente
        if 'issue_type' in conditions and 'issue_type' in metrics:
            # Puede ser exact match o lista de tipos
            if isinstance(conditions['issue_type'], list):
                if metrics['issue_type'] not in conditions['issue_type']:
                    return False
            else:
                if metrics['issue_type'] != conditions['issue_type']:
                    return False
        
        # Todas las condiciones cumplidas
        return True
    
    def find_matching_actions(self, service_id, metrics, issue_type=None):
        """
        Encuentra acciones que coinciden con las métricas actuales y tipo de problema
        
        Args:
            service_id: ID del servicio
            metrics: Métricas actuales
            issue_type: Tipo de problema (opcional)
            
        Returns:
            Lista de acciones coincidentes
        """
        matching_actions = []
        
        # Si se proporciona issue_type, añadirlo a las métricas
        if issue_type:
            metrics_copy = metrics.copy()
            metrics_copy['issue_type'] = issue_type
        else:
            metrics_copy = metrics
            
            # Intentar determinar tipo de problema desde anomaly_type si está disponible
            if 'anomaly_type' in metrics:
                issue_type = self.situation_type_map.get(metrics['anomaly_type'])
                if issue_type:
                    metrics_copy['issue_type'] = issue_type
        
        # Verificar políticas específicas para este servicio
        if service_id in self.action_policies:
            service_actions = self.action_policies[service_id].get('actions', {})
            
            # Verificar cada acción
            for action_id, action_def in service_actions.items():
                if 'conditions' in action_def:
                    if self.check_conditions(action_def['conditions'], metrics_copy):
                        # Crear copia de la acción y añadir datos adicionales
                        action = action_def.copy()
                        action['action_id'] = action_id
                        action['service_id'] = service_id
                        
                        # Añadir score de efectividad
                        effectiveness_key = f"{service_id}:{action_id}"
                        effectiveness = self.action_effectiveness.get(effectiveness_key, {})
                        action['effectiveness_score'] = effectiveness.get('success_rate', 0.5)
                        
                        # Añadir a lista de coincidentes
                        matching_actions.append(action)
        
        # Si no hay acciones específicas, buscar en políticas genéricas
        if not matching_actions:
            # Determinar tipo de servicio para buscar políticas genéricas
            service_type = self._infer_service_type(service_id, metrics_copy)
            default_policy_id = f"default_{service_type}"
            
            if default_policy_id in self.action_policies:
                default_actions = self.action_policies[default_policy_id].get('actions', {})
                
                # Verificar cada acción genérica
                for action_id, action_def in default_actions.items():
                    if 'conditions' in action_def:
                        if self.check_conditions(action_def['conditions'], metrics_copy):
                            # Crear copia de la acción y adaptarla al servicio actual
                            action = action_def.copy()
                            action['action_id'] = action_id
                            action['service_id'] = service_id
                            action['is_generic'] = True
                            
                            # Usar efectividad genérica
                            effectiveness_key = f"generic:{action_id}"
                            effectiveness = self.action_effectiveness.get(effectiveness_key, {})
                            action['effectiveness_score'] = effectiveness.get('success_rate', 0.4)  # Menor confianza en genéricas
                            
                            matching_actions.append(action)
        
        # Ordenar por efectividad y prioridad
        priority_map = {
            'critical': 0,
            'high': 1,
            'medium': 2,
            'low': 3
        }
        
        # Ordenar primero por prioridad, luego por efectividad
        matching_actions.sort(
            key=lambda x: (
                priority_map.get(x.get('priority', 'medium'), 2),
                -x.get('effectiveness_score', 0)  # Negativo para ordenar descendente
            )
        )
        
        return matching_actions
    
    def _infer_service_type(self, service_id, metrics):
        """
        Infiere el tipo de servicio basado en el nombre y métricas disponibles
        
        Returns:
            str: Tipo de servicio inferido
        """
        service_id_lower = service_id.lower()
        
        # Inferir por nombre
        if any(db_term in service_id_lower for db_term in ['postgres', 'mysql', 'db', 'database', 'sql']):
            return 'database'
        elif any(cache_term in service_id_lower for cache_term in ['redis', 'cache', 'memcached']):
            return 'cache'
        elif any(queue_term in service_id_lower for queue_term in ['kafka', 'rabbit', 'mq', 'queue']):
            return 'queue'
        
        # Inferir por métricas disponibles
        if any(metric in metrics for metric in ['active_connections', 'query_time', 'index_bloat']):
            return 'database'
        elif any(metric in metrics for metric in ['memory_fragmentation_ratio', 'hit_rate', 'eviction_rate']):
            return 'cache'
        elif any(metric in metrics for metric in ['consumer_lag', 'message_rate', 'queue_size']):
            return 'queue'
        
        # Por defecto es web service
        return 'web_service'
    
    @cached(ttl=60)  # Cachear resultados por 60 segundos
    def process_and_recommend(self, anomaly_data=None, prediction_data=None):
        """
        Procesa datos de anomalías o predicciones y recomienda acciones
        
        Args:
            anomaly_data: Datos de anomalía
            prediction_data: Datos de predicción
            
        Returns:
            Dict con recomendación
        """
        try:
            with self.metrics.time_recommendation(service_id="unknown"):
                # Determinar tipo de entrada
                if anomaly_data:
                    # Procesar anomalía
                    service_id = anomaly_data.get('service_id', 'unknown_service')
                    metrics = anomaly_data.get('details', {}).get('metrics', {})
                    metrics['anomaly_score'] = anomaly_data.get('anomaly_score', 0)
                    
                    # Determinar tipo de problema
                    anomaly_type = anomaly_data.get('details', {}).get('anomaly_type', 'unknown')
                    issue_type = self.situation_type_map.get(anomaly_type)
                    
                    # Recomendar acción
                    recommended_action = self.recommend_action(service_id, metrics, 'anomaly', issue_type)
                    
                    if recommended_action:
                        # Registrar métrica
                        self.metrics.record_action_recommendation(
                            service_id, recommended_action.get('action_id', 'unknown')
                        )
                        
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
                    
                    # Determinar tipo de problema
                    prediction_type = prediction_data.get('prediction_type', 'unknown')
                    issue_type = self.situation_type_map.get(prediction_type)
                    
                    # Recomendar acción
                    recommended_action = self.recommend_action(service_id, metrics, 'prediction', issue_type)
                    
                    if recommended_action:
                        # Registrar métrica
                        self.metrics.record_action_recommendation(
                            service_id, recommended_action.get('action_id', 'unknown')
                        )
                        
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
            logger.error(traceback.format_exc())
            return {
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
    
    def recommend_action(self, service_id, metrics, issue_type=None, problem_category=None):
        """
        Recomienda la mejor acción para un problema detectado
        
        Args:
            service_id: ID del servicio
            metrics: Métricas actuales
            issue_type: Tipo de problema (anomalía o predicción)
            problem_category: Categoría de problema
            
        Returns:
            Dict con acción recomendada
        """
        try:
            logger.info(f"Buscando acción para {service_id} con issue_type={issue_type}, problema={problem_category}")
            
            # Encontrar acciones que coinciden con las métricas
            matching_actions = self.find_matching_actions(service_id, metrics, problem_category)
            
            if not matching_actions:
                logger.warning(f"No hay acciones disponibles para {service_id}")
                return None
            
            # La primera acción es la de mayor prioridad y efectividad
            return matching_actions[0]
                
        except Exception as e:
            logger.error(f"Error al recomendar acción: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def execute_action(self, action, metrics, auth_token=None):
        """
        Ejecuta una acción correctiva
        
        Args:
            action: Acción a ejecutar
            metrics: Métricas actuales
            auth_token: Token de autorización opcional
        
        Returns:
            bool: True si la acción se ejecutó exitosamente
        """
        if not action:
            logger.warning("No se proporcionó acción para ejecutar")
            return False
        
        # Extraer información
        action_id = action.get('action_id', 'unknown_action')
        service_id = action.get('service_id', 'unknown_service')
        
        # Contexto de ejecución
        context = {
            'metrics': metrics,
            'auth_token': auth_token,
            'timestamp': datetime.now().isoformat()
        }
        
        # Encolar acción para ejecución
        execution_id = self.orchestrator.enqueue_action(action, context)
        
        if execution_id:
            logger.info(f"Acción {action_id} encolada para ejecución: {execution_id}")
            return True
        else:
            logger.error(f"Error al encolar acción {action_id}")
            return False
    
    def update_action_effectiveness(self, service_id, action_id, success, metrics_before, metrics_after=None):
        """
        Actualiza la efectividad histórica de una acción
        
        Args:
            service_id: ID del servicio
            action_id: ID de la acción
            success: Si la acción tuvo éxito
            metrics_before: Métricas antes de la acción
            metrics_after: Métricas después de la acción
        """
        effectiveness_key = f"{service_id}:{action_id}"
        
        # Inicializar registro si no existe
        if effectiveness_key not in self.action_effectiveness:
            self.action_effectiveness[effectiveness_key] = {
                'count': 0,
                'success_count': 0,
                'success_rate': 0.0,
                'last_update': datetime.now().isoformat()
            }
        
        # Actualizar estadísticas
        record = self.action_effectiveness[effectiveness_key]
        record['count'] += 1
        if success:
            record['success_count'] += 1
        
        # Recalcular tasa de éxito
        record['success_rate'] = record['success_count'] / record['count']
        record['last_update'] = datetime.now().isoformat()
        
        # Si hay métricas antes y después, calcular mejora
        if metrics_after:
            # Implementación simplificada - en producción necesitaría más lógica
            # para determinar cuáles métricas son "buenas" cuando bajan o suben
            pass
        
        # Guardar cambios
        self.save_action_effectiveness()
    
    def get_action_effectiveness(self, service_id=None, action_id=None):
        """
        Obtiene estadísticas de efectividad de acciones
        
        Args:
            service_id: Filtrar por servicio (opcional)
            action_id: Filtrar por acción (opcional)
            
        Returns:
            Dict con estadísticas de efectividad
        """
        if service_id and action_id:
            # Acción específica
            key = f"{service_id}:{action_id}"
            return self.action_effectiveness.get(key)
        elif service_id:
            # Todas las acciones para un servicio
            results = {}
            prefix = f"{service_id}:"
            for key, value in self.action_effectiveness.items():
                if key.startswith(prefix):
                    action_id = key.split(':', 1)[1]
                    results[action_id] = value
            return results
        else:
            # Todas las acciones
            return self.action_effectiveness