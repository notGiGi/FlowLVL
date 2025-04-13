import os
import json
import logging
import numpy as np
import pandas as pd
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import time
import joblib
from threading import Thread
import requests
import yaml
import subprocess
from sklearn.ensemble import RandomForestClassifier
import pickle
import json
import random

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('action_recommender')

class ActionRecommender:
    def __init__(self):
        # Configuración de conexiones
        self.db_host = os.environ.get('DB_HOST', 'timescaledb')
        self.db_port = os.environ.get('DB_PORT', '5432')
        self.db_user = os.environ.get('DB_USER', 'predictor')
        self.db_password = os.environ.get('DB_PASSWORD', 'predictor_password')
        self.db_name = os.environ.get('DB_NAME', 'metrics_db')
        self.kafka_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        
        # Conectar a la base de datos
        self.db_url = f"postgresql://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"
        self.engine = create_engine(self.db_url)
        
        # Configurar consumidores Kafka
        self.anomaly_consumer = KafkaConsumer(
            'anomalies',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='action_recommender_anomalies'
        )
        
        self.prediction_consumer = KafkaConsumer(
            'failure_predictions',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='action_recommender_predictions'
        )
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Cargar políticas de acción
        self.action_policies = self.load_action_policies()
        
        # Cargar o crear modelos de recomendación
        self.recommendation_models = self.load_recommendation_models()
        
        # Histórico de acciones para aprendizaje por refuerzo
        self.action_history = []
        
        # Configuración del recomendador
        self.max_history_size = 1000
        self.auto_remediation = True  # Si es True, ejecuta acciones automáticamente
        
        logger.info("Recomendador de acciones inicializado correctamente")

    def load_action_policies(self):
        """Carga las políticas de acción desde archivos YAML"""
        policies = {}
        policy_dir = "/app/policies"
        
        # Crear directorio si no existe
        if not os.path.exists(policy_dir):
            os.makedirs(policy_dir)
            # Crear política de ejemplo si no hay ninguna
            self.create_example_policies(policy_dir)
        
        try:
            # Cargar todos los archivos YAML del directorio
            for filename in os.listdir(policy_dir):
                if filename.endswith('.yaml') or filename.endswith('.yml'):
                    filepath = os.path.join(policy_dir, filename)
                    with open(filepath, 'r') as file:
                        policy = yaml.safe_load(file)
                        
                        # Validar estructura básica
                        if not isinstance(policy, dict) or 'service_id' not in policy:
                            logger.warning(f"Política inválida en {filename}, se omite")
                            continue
                        
                        service_id = policy['service_id']
                        policies[service_id] = policy
                        logger.info(f"Política cargada para servicio: {service_id}")
            
            if not policies:
                # Si no se cargaron políticas, crear ejemplos
                self.create_example_policies(policy_dir)
                # Volver a cargar
                return self.load_action_policies()
                
        except Exception as e:
            logger.error(f"Error al cargar políticas: {str(e)}")
            # Crear políticas de ejemplo en caso de error
            self.create_example_policies(policy_dir)
        
        return policies

    def create_example_policies(self, policy_dir):
        """Crea políticas de ejemplo si no hay ninguna configurada"""
        try:
            # Política para un servicio web genérico
            web_service_policy = {
                'service_id': 'web_service',
                'description': 'Política para servicios web',
                'actions': {
                    'high_cpu': {
                        'description': 'Acción para alto uso de CPU',
                        'conditions': {
                            'metrics': {
                                'cpu_usage': '> 90'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl scale deployment {service_name} --replicas={current_replicas + 1}',
                            'rollback': 'kubectl scale deployment {service_name} --replicas={original_replicas}'
                        },
                        'priority': 'high'
                    },
                    'memory_leak': {
                        'description': 'Acción para posible fuga de memoria',
                        'conditions': {
                            'metrics': {
                                'memory_usage': '> 85',
                                'memory_growth_rate': '> 10'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl rollout restart deployment {service_name}',
                        },
                        'priority': 'critical'
                    },
                    'high_latency': {
                        'description': 'Acción para alta latencia',
                        'conditions': {
                            'metrics': {
                                'response_time_ms': '> 500'
                            }
                        },
                        'remediation': {
                            'type': 'api',
                            'endpoint': 'http://{service_host}:{service_port}/admin/cache/clear',
                            'method': 'POST',
                            'headers': {
                                'Authorization': 'Bearer {service_token}'
                            },
                            'payload': {
                                'scope': 'all'
                            }
                        },
                        'priority': 'medium'
                    }
                }
            }
            
            # Política para servicio de base de datos
            db_service_policy = {
                'service_id': 'database_service',
                'description': 'Política para servicios de base de datos',
                'actions': {
                    'connection_pool_exhaustion': {
                        'description': 'Acción para agotamiento del pool de conexiones',
                        'conditions': {
                            'metrics': {
                                'active_connections': '> 90',
                                'connection_wait_time': '> 200'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl exec {pod_name} -- sh -c "echo \'ALTER SYSTEM SET max_connections = {current_connections * 1.5};\' | psql -U postgres && echo \'SELECT pg_reload_conf();\' | psql -U postgres"'
                        },
                        'priority': 'high'
                    },
                    'disk_space_low': {
                        'description': 'Acción para poco espacio en disco',
                        'conditions': {
                            'metrics': {
                                'disk_usage_percent': '> 85'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl exec {pod_name} -- sh -c "echo \'VACUUM FULL;\' | psql -U postgres"'
                        },
                        'priority': 'critical'
                    }
                }
            }
            
            # Política para un servicio de caché
            cache_service_policy = {
                'service_id': 'cache_service',
                'description': 'Política para servicios de caché',
                'actions': {
                    'eviction_rate_high': {
                        'description': 'Acción para alta tasa de expulsión',
                        'conditions': {
                            'metrics': {
                                'eviction_rate': '> 100'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl scale statefulset {service_name} --replicas={current_replicas + 1}'
                        },
                        'priority': 'medium'
                    },
                    'memory_fragmentation_high': {
                        'description': 'Acción para alta fragmentación de memoria',
                        'conditions': {
                            'metrics': {
                                'memory_fragmentation_ratio': '> 3'
                            }
                        },
                        'remediation': {
                            'type': 'command',
                            'command': 'kubectl exec {pod_name} -- redis-cli MEMORY PURGE'
                        },
                        'priority': 'low'
                    }
                }
            }
            
            # Guardar políticas de ejemplo
            with open(os.path.join(policy_dir, 'web_service_policy.yaml'), 'w') as f:
                yaml.dump(web_service_policy, f)
                
            with open(os.path.join(policy_dir, 'database_service_policy.yaml'), 'w') as f:
                yaml.dump(db_service_policy, f)
                
            with open(os.path.join(policy_dir, 'cache_service_policy.yaml'), 'w') as f:
                yaml.dump(cache_service_policy, f)
                
            logger.info("Políticas de ejemplo creadas")
            
        except Exception as e:
            logger.error(f"Error al crear políticas de ejemplo: {str(e)}")

    def load_recommendation_models(self):
        """Carga o crea modelos de recomendación para cada servicio"""
        models = {}
        models_dir = "/app/models/recommender"
        os.makedirs(models_dir, exist_ok=True)
        
        try:
            # Verificar si existen modelos previamente entrenados
            for service_id in self.action_policies.keys():
                model_path = os.path.join(models_dir, f"{service_id}_recommender.joblib")
                
                if os.path.exists(model_path):
                    # Cargar modelo existente
                    models[service_id] = joblib.load(model_path)
                    logger.info(f"Modelo de recomendación cargado para servicio: {service_id}")
                else:
                    # Crear un modelo básico
                    model = RandomForestClassifier(n_estimators=100, random_state=42)
                    models[service_id] = model
                    # No entrenamos aún, esperamos datos
                    logger.info(f"Modelo de recomendación creado para servicio: {service_id}")
        except Exception as e:
            logger.error(f"Error al cargar modelos de recomendación: {str(e)}")
            
        return models

    def evaluate_condition(self, condition, metrics):
        """Evalúa una condición contra las métricas actuales"""
        try:
            if 'metrics' not in condition:
                return False
            
            for metric_name, condition_str in condition['metrics'].items():
                # Extraer operador y valor
                parts = condition_str.strip().split(' ')
                if len(parts) != 2:
                    logger.warning(f"Condición inválida: {condition_str}")
                    return False
                
                operator, threshold_str = parts
                threshold = float(threshold_str)
                
                # Verificar si la métrica existe
                if metric_name not in metrics:
                    logger.debug(f"Métrica {metric_name} no encontrada en los datos")
                    return False
                
                # Obtener valor de la métrica
                metric_value = float(metrics[metric_name])
                
                # Evaluar condición
                if operator == '>':
                    if not (metric_value > threshold):
                        return False
                elif operator == '>=':
                    if not (metric_value >= threshold):
                        return False
                elif operator == '<':
                    if not (metric_value < threshold):
                        return False
                elif operator == '<=':
                    if not (metric_value <= threshold):
                        return False
                elif operator == '==':
                    if not (metric_value == threshold):
                        return False
                else:
                    logger.warning(f"Operador desconocido en condición: {operator}")
                    return False
            
            # Si todas las condiciones se cumplen
            return True
                
        except Exception as e:
            logger.error(f"Error al evaluar condición: {str(e)}")
            return False

    def find_matching_actions(self, service_id, metrics):
        """Encuentra acciones que coinciden con las métricas actuales"""
        matching_actions = []
        
        # Buscar política para este servicio
        if service_id not in self.action_policies:
            logger.warning(f"No hay política definida para servicio: {service_id}")
            # Buscar política genérica si existe
            if 'default' in self.action_policies:
                service_id = 'default'
            else:
                return []
        
        policy = self.action_policies[service_id]
        
        # Evaluar cada acción en la política
        for action_id, action_def in policy['actions'].items():
            if 'conditions' in action_def and self.evaluate_condition(action_def['conditions'], metrics):
                # Añadir metadatos de la acción
                action = {
                    'action_id': action_id,
                    'service_id': service_id,
                    'description': action_def.get('description', ''),
                    'remediation': action_def.get('remediation', {}),
                    'priority': action_def.get('priority', 'medium')
                }
                matching_actions.append(action)
        
        # Ordenar por prioridad
        priority_map = {
            'critical': 0,
            'high': 1,
            'medium': 2,
            'low': 3
        }
        
        matching_actions.sort(key=lambda x: priority_map.get(x['priority'], 99))
        
        return matching_actions

    def recommend_action(self, service_id, metrics, issue_type):
        """Recomienda la mejor acción para un problema detectado"""
        try:
            # Encontrar acciones que coinciden con las métricas
            matching_actions = self.find_matching_actions(service_id, metrics)
            
            if not matching_actions:
                logger.warning(f"No hay acciones disponibles para {service_id} con las métricas actuales")
                return None
            
            # Si tenemos un modelo entrenado, usarlo para seleccionar la mejor acción
            if service_id in self.recommendation_models and len(self.action_history) > 10:
                # Preparar características para el modelo
                features = []
                for key, value in metrics.items():
                    if isinstance(value, (int, float)):
                        features.append(value)
                
                # Si no hay suficientes características, usar selección básica
                if len(features) < 3:
                    return matching_actions[0]
                
                # Normalizar tamaño de características (padding o truncar)
                target_size = 10  # Tamaño fijo de características
                if len(features) < target_size:
                    features.extend([0] * (target_size - len(features)))
                else:
                    features = features[:target_size]
                
                # Predecir mejor acción
                X = np.array([features])
                
                # Verificar si el modelo está entrenado
                try:
                    # Predecir índice de acción
                    action_idx = self.recommendation_models[service_id].predict(X)[0]
                    action_idx = min(action_idx, len(matching_actions) - 1)
                    return matching_actions[action_idx]
                except:
                    # Si el modelo no está entrenado o falla, usar la primera acción
                    return matching_actions[0]
            else:
                # Sin modelo entrenado, tomar la acción de mayor prioridad
                return matching_actions[0]
                
        except Exception as e:
            logger.error(f"Error al recomendar acción: {str(e)}")
            if matching_actions:
                return matching_actions[0]  # Retornar la primera en caso de error
            return None

    def execute_action(self, action, metrics, variables=None):
        """Ejecuta una acción de remediación"""
        try:
            if not action or 'remediation' not in action:
                logger.warning("No hay acción de remediación definida")
                return False
            
            remediation = action['remediation']
            action_type = remediation.get('type', 'unknown')
            
            # Preparar variables para la acción
            action_vars = {
                'service_id': action['service_id'],
                'service_name': action['service_id'],
                'timestamp': datetime.now().isoformat()
            }
            
            # Añadir métricas como variables
            for key, value in metrics.items():
                if isinstance(value, (int, float, str)):
                    action_vars[key] = value
            
            # Añadir variables adicionales
            if variables:
                action_vars.update(variables)
            
            # Ejecutar según tipo de acción
            if action_type == 'command':
                command = remediation.get('command', '')
                if not command:
                    logger.warning("Comando vacío en acción")
                    return False
                
                # Reemplazar variables en el comando
                for var_name, var_value in action_vars.items():
                    command = command.replace(f"{{{var_name}}}", str(var_value))
                
                # Ejecutar comando
                logger.info(f"Ejecutando comando: {command}")
                
                # Simulación - en producción usaríamos subprocess.run
                # result = subprocess.run(command, shell=True, capture_output=True, text=True)
                # success = result.returncode == 0
                
                # Para el ejemplo, simulamos éxito
                success = True
                logger.info(f"Comando ejecutado exitosamente (simulado)")
                
                return success
                
            elif action_type == 'api':
                endpoint = remediation.get('endpoint', '')
                method = remediation.get('method', 'GET')
                headers = remediation.get('headers', {})
                payload = remediation.get('payload', {})
                
                if not endpoint:
                    logger.warning("Endpoint vacío en acción API")
                    return False
                
                # Reemplazar variables en el endpoint
                for var_name, var_value in action_vars.items():
                    endpoint = endpoint.replace(f"{{{var_name}}}", str(var_value))
                    
                    # También reemplazar en headers y payload
                    for header_key, header_value in headers.items():
                        if isinstance(header_value, str):
                            headers[header_key] = header_value.replace(f"{{{var_name}}}", str(var_value))
                    
                    # Reemplazar en payload (recursivamente)
                    if payload:
                        self._replace_vars_in_dict(payload, var_name, var_value)
                
                logger.info(f"Llamando API: {method} {endpoint}")
                
                # Simulación - en producción usaríamos requests
                # if method.upper() == 'GET':
                #     response = requests.get(endpoint, headers=headers)
                # elif method.upper() == 'POST':
                #     response = requests.post(endpoint, headers=headers, json=payload)
                # # ... otros métodos
                # success = response.status_code < 400
                
                # Para el ejemplo, simulamos éxito
                success = True
                logger.info(f"API llamada exitosamente (simulado)")
                
                return success
                
            else:
                logger.warning(f"Tipo de acción desconocido: {action_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error al ejecutar acción: {str(e)}")
            return False

    def _replace_vars_in_dict(self, d, var_name, var_value):
        """Reemplaza variables en un diccionario de forma recursiva"""
        for k, v in d.items():
            if isinstance(v, str):
                d[k] = v.replace(f"{{{var_name}}}", str(var_value))
            elif isinstance(v, dict):
                self._replace_vars_in_dict(v, var_name, var_value)

    def process_anomaly(self, message):
        """Procesa un mensaje de anomalía y recomienda/ejecuta acciones"""
        try:
            data = message.value
            service_id = data.get('service_id', 'unknown')
            metrics = {}
            
            # Extraer métricas del mensaje
            for key, value in data.items():
                if isinstance(value, (int, float)) and key not in ['timestamp', 'anomaly_score']:
                    metrics[key] = value
            
            # Añadir detalles de anomalía a las métricas
            anomaly_details = data.get('anomaly_details', {})
            for feature, details in anomaly_details.items():
                if 'value' in details:
                    metrics[feature] = details['value']
            
            # También añadir el score de anomalía
            metrics['anomaly_score'] = data.get('anomaly_score', 0)
            
            # Recomendar acción
            action = self.recommend_action(service_id, metrics, 'anomaly')
            
            if action:
                action_data = {
                    'timestamp': datetime.now().isoformat(),
                    'service_id': service_id,
                    'node_id': data.get('node_id', 'unknown'),
                    'issue_type': 'anomaly',
                    'metrics': metrics,
                    'recommended_action': action,
                    'executed': False,
                    'success': None
                }
                
                # Ejecutar acción automáticamente si está habilitado
                if self.auto_remediation:
                    success = self.execute_action(action, metrics)
                    action_data['executed'] = True
                    action_data['success'] = success
                    
                    # Almacenar en histórico para aprendizaje
                    self.action_history.append({
                        'timestamp': datetime.now(),
                        'service_id': service_id,
                        'metrics': metrics,
                        'action': action,
                        'success': success
                    })
                    
                    # Limitar tamaño del histórico
                    if len(self.action_history) > self.max_history_size:
                        self.action_history = self.action_history[-self.max_history_size:]
                
                # Publicar recomendación
                self.producer.send('recommendations', action_data)
                
                # Almacenar recomendación
                self.store_recommendation(action_data)
                
                logger.info(f"Acción recomendada para anomalía en {service_id}: {action['action_id']}")
                
                return True
            else:
                logger.warning(f"No se pudo recomendar acción para anomalía en {service_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error al procesar anomalía: {str(e)}")
            return False

    def process_prediction(self, message):
        """Procesa un mensaje de predicción y recomienda/ejecuta acciones preventivas"""
        try:
            data = message.value
            service_id = data.get('service_id', 'unknown')
            
            # Extraer métricas del mensaje original
            original_data = data.get('original_data', {})
            metrics = {}
            
            for key, value in original_data.items():
                if isinstance(value, (int, float)) and key not in ['timestamp']:
                    metrics[key] = value
            
            # Añadir información de la predicción
            metrics['failure_probability'] = data.get('failure_probability', 0)
            metrics['prediction_horizon'] = data.get('prediction_horizon', 0)
            
            # Recomendar acción preventiva
            action = self.recommend_action(service_id, metrics, 'prediction')
            
            if action:
                action_data = {
                    'timestamp': datetime.now().isoformat(),
                    'service_id': service_id,
                    'node_id': data.get('node_id', 'unknown'),
                    'issue_type': 'prediction',
                    'metrics': metrics,
                    'recommended_action': action,
                    'executed': False,
                    'success': None,
                    'prevention': True
                }
                
                # Ejecutar acción preventiva automáticamente si está habilitado
                if self.auto_remediation:
                    success = self.execute_action(action, metrics)
                    action_data['executed'] = True
                    action_data['success'] = success
                    
                    # Almacenar en histórico para aprendizaje
                    self.action_history.append({
                        'timestamp': datetime.now(),
                        'service_id': service_id,
                        'metrics': metrics,
                        'action': action,
                        'success': success,
                        'preventive': True
                    })
                    
                    # Limitar tamaño del histórico
                    if len(self.action_history) > self.max_history_size:
                        self.action_history = self.action_history[-self.max_history_size:]
                
                # Publicar recomendación
                self.producer.send('recommendations', action_data)
                
                # Almacenar recomendación
                self.store_recommendation(action_data)
                
                logger.info(f"Acción preventiva recomendada para {service_id}: {action['action_id']}")
                
                return True
            else:
                logger.warning(f"No se pudo recomendar acción preventiva para {service_id}")
                return False
                
        except Exception as e:
            logger.error(f"Error al procesar predicción: {str(e)}")
            return False

    def store_recommendation(self, recommendation_data):
        """Almacena la recomendación en la base de datos"""
        try:
            # Preparar datos para la base de datos
            recommendation_df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'service_id': recommendation_data['service_id'],
                'node_id': recommendation_data['node_id'],
                'issue_type': recommendation_data['issue_type'],
                'action_id': recommendation_data['recommended_action']['action_id'],
                'executed': recommendation_data['executed'],
                'success': recommendation_data['success'],
                'recommendation_data': json.dumps(recommendation_data)
            }])
            
            # Insertar en la tabla de recomendaciones
            recommendation_df.to_sql('recommendations', self.engine, if_exists='append', index=False)
            
        except Exception as e:
            logger.error(f"Error al almacenar recomendación: {str(e)}")

    def train_recommendation_models(self):
        """Entrena modelos de recomendación utilizando el histórico de acciones"""
        try:
            # Agrupar histórico por servicio
            service_history = {}
            for entry in self.action_history:
                service_id = entry['service_id']
                if service_id not in service_history:
                    service_history[service_id] = []
                service_history[service_id].append(entry)
            
            # Entrenar modelo para cada servicio con suficientes datos
            for service_id, history in service_history.items():
                if len(history) < 10:  # Necesitamos al menos 10 ejemplos
                    continue
                
                # Preparar datos de entrenamiento
                X = []  # Características (métricas)
                y = []  # Etiquetas (acción exitosa o no)
                
                for entry in history:
                    # Extraer características
                    features = []
                    for key, value in entry['metrics'].items():
                        if isinstance(value, (int, float)):
                            features.append(value)
                    
                    # Normalizar tamaño de características
                    target_size = 10
                    if len(features) < target_size:
                        features.extend([0] * (target_size - len(features)))
                    else:
                        features = features[:target_size]
                    
                    # Extraer etiqueta (índice de la acción)
                    # Si tenemos éxito, usamos el índice real, sino un índice aleatorio diferente
                    action_id = entry['action']['action_id']
                    action_idx = list(self.action_policies.get(service_id, {}).get('actions', {}).keys()).index(action_id)
                    
                    X.append(features)
                    y.append(action_idx if entry.get('success', False) else random.randint(0, 3))
                
                # Entrenar modelo
                X = np.array(X)
                y = np.array(y)
                
                model = RandomForestClassifier(n_estimators=100, random_state=42)
                model.fit(X, y)
                
                # Guardar modelo
                self.recommendation_models[service_id] = model
                models_dir = "/app/models/recommender"
                model_path = os.path.join(models_dir, f"{service_id}_recommender.joblib")
                joblib.dump(model, model_path)
                
                logger.info(f"Modelo de recomendación entrenado para servicio {service_id}")
                
        except Exception as e:
            logger.error(f"Error al entrenar modelos de recomendación: {str(e)}")

    def train_models_periodically(self):
        """Función para entrenar los modelos periódicamente"""
        while True:
            try:
                # Entrenar cada 12 horas o cuando haya suficientes datos nuevos
                time.sleep(43200)  # 12 horas en segundos
                
                if len(self.action_history) > 20:
                    logger.info("Iniciando entrenamiento de modelos de recomendación...")
                    self.train_recommendation_models()
                    logger.info("Entrenamiento de modelos de recomendación completado")
                
            except Exception as e:
                logger.error(f"Error en entrenamiento periódico: {str(e)}")
                time.sleep(3600)  # Esperar 1 hora antes de reintentar

    def run(self):
        """Ejecuta el recomendador de acciones"""
        # Iniciar hilo para entrenamiento periódico
        training_thread = Thread(target=self.train_models_periodically, daemon=True)
        training_thread.start()
        
        # Iniciar hilos para consumir de múltiples tópicos
        anomaly_thread = Thread(target=self.consume_anomalies, daemon=True)
        prediction_thread = Thread(target=self.consume_predictions, daemon=True)
        
        anomaly_thread.start()
        prediction_thread.start()
        
        logger.info("Recomendador de acciones iniciado, esperando mensajes...")
        
        try:
            # Mantener el proceso principal vivo
            while True:
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("Recomendador de acciones detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el recomendador de acciones: {str(e)}")
        finally:
            # Cerrar conexiones (esto no se ejecutará a menos que se detenga el proceso)
            self.anomaly_consumer.close()
            self.prediction_consumer.close()
            self.producer.close()

    def consume_anomalies(self):
        """Consume mensajes de anomalías"""
        try:
            for message in self.anomaly_consumer:
                self.process_anomaly(message)
        except Exception as e:
            logger.error(f"Error en consumidor de anomalías: {str(e)}")
            
    def consume_predictions(self):
        """Consume mensajes de predicciones"""
        try:
            for message in self.prediction_consumer:
                self.process_prediction(message)
        except Exception as e:
            logger.error(f"Error en consumidor de predicciones: {str(e)}")


if __name__ == "__main__":
    # Esperar a que Kafka esté disponible
    time.sleep(20)
    
    # Iniciar el recomendador de acciones
    recommender = ActionRecommender()
    recommender.run()