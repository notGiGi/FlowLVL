#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Action Recommender - Sistema predictivo de mantenimiento para sistemas distribuidos
--------------------------------------------------------------------------------
Módulo para recomendación inteligente de acciones correctivas 
con aprendizaje por refuerzo.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
import time
import random
import re
import subprocess
import threading
from datetime import datetime, timedelta
from collections import deque
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model, Model
from tensorflow.keras.layers import Dense, Input, Concatenate, Dropout
from tensorflow.keras.optimizers import Adam
from string import Template
import warnings

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('action_recommender')

# Suprimir advertencias
warnings.filterwarnings("ignore")

class RLActionRecommender:
    """
    Recomendador de acciones basado en Deep Q-Learning (DQN)
    """
    def __init__(self, state_dim, action_dim, memory_size=2000, batch_size=32, 
                 gamma=0.95, epsilon=1.0, epsilon_min=0.01, epsilon_decay=0.995,
                 learning_rate=0.001, target_update_freq=10):
        """
        Inicializa el recomendador basado en RL
        
        Args:
            state_dim: Dimensión del vector de estado (número de métricas)
            action_dim: Dimensión del espacio de acciones (número de acciones posibles)
            memory_size: Tamaño de la memoria de experiencias
            batch_size: Tamaño de lote para entrenamiento
            gamma: Factor de descuento para recompensas futuras
            epsilon: Probabilidad inicial de exploración
            epsilon_min: Probabilidad mínima de exploración
            epsilon_decay: Tasa de decrecimiento de exploración
            learning_rate: Tasa de aprendizaje para el optimizador
            target_update_freq: Frecuencia de actualización del modelo target
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.memory_size = memory_size
        self.batch_size = batch_size
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_min = epsilon_min
        self.epsilon_decay = epsilon_decay
        self.learning_rate = learning_rate
        self.target_update_freq = target_update_freq
        
        # Modelos de Q-Learning
        self.model = self._build_model()
        self.target_model = self._build_model()
        self.update_target_model()
        
        # Memoria de experiencias
        self.memory = deque(maxlen=memory_size)
        
        # Contador de actualizaciones
        self.update_counter = 0
        
        # Historial de entrenamiento
        self.training_history = {
            'loss': [],
            'mean_q': [],
            'reward': []
        }
        
        logger.info(f"Agente RL inicializado con estado={state_dim}, acciones={action_dim}")
    
    def _build_model(self):
        """Construye un modelo de red neuronal para Q-Learning"""
        # Modelo para Q-Learning
        model = Sequential()
        model.add(Dense(64, input_dim=self.state_dim, activation='relu', 
                       kernel_initializer='he_uniform'))
        model.add(Dropout(0.2))
        model.add(Dense(64, activation='relu', kernel_initializer='he_uniform'))
        model.add(Dropout(0.2))
        model.add(Dense(32, activation='relu', kernel_initializer='he_uniform'))
        model.add(Dense(self.action_dim, activation='linear'))
        model.compile(loss='mse', optimizer=Adam(learning_rate=self.learning_rate))
        return model
    
    def update_target_model(self):
        """Actualiza el modelo target con los pesos del modelo principal"""
        self.target_model.set_weights(self.model.get_weights())
        logger.debug("Modelo target actualizado")
    
    def remember(self, state, action, reward, next_state, done):
        """Almacena una experiencia en la memoria"""
        self.memory.append((state, action, reward, next_state, done))
    
    def act(self, state, deterministic=False):
        """
        Selecciona una acción basada en el estado actual
        
        Args:
            state: Vector de estado actual
            deterministic: Si es True, selecciona la mejor acción sin exploración
            
        Returns:
            Índice de la acción seleccionada
        """
        if not deterministic and np.random.rand() <= self.epsilon:
            # Exploración aleatoria
            return random.randrange(self.action_dim)
        
        # Explotación - seleccionar mejor acción
        # Asegurar que el estado tiene la forma correcta (batch_size, state_dim)
        state_array = np.reshape(state, [1, self.state_dim])
        q_values = self.model.predict(state_array, verbose=0)[0]
        return np.argmax(q_values)
    
    def replay(self):
        """Entrena el modelo con experiencias almacenadas en la memoria"""
        if len(self.memory) < self.batch_size:
            return 0  # No suficientes experiencias
        
        # Muestrear experiencias de la memoria
        minibatch = random.sample(self.memory, self.batch_size)
        states = np.zeros((self.batch_size, self.state_dim))
        targets = np.zeros((self.batch_size, self.action_dim))
        
        for i, (state, action, reward, next_state, done) in enumerate(minibatch):
            states[i] = state
            
            # Calcular target Q-value
            target = self.model.predict(state.reshape(1, self.state_dim), verbose=0)[0]
            
            if done:
                target[action] = reward
            else:
                # Double Q-Learning:
                # 1. Seleccionar acción con modelo principal
                a = np.argmax(self.model.predict(next_state.reshape(1, self.state_dim), verbose=0)[0])
                # 2. Evaluar Q-value con modelo target
                t = self.target_model.predict(next_state.reshape(1, self.state_dim), verbose=0)[0][a]
                target[action] = reward + self.gamma * t
            
            targets[i] = target
        
        # Entrenar modelo
        history = self.model.fit(states, targets, epochs=1, verbose=0)
        loss = history.history['loss'][0]
        
        # Actualizar modelo target periódicamente
        self.update_counter += 1
        if self.update_counter % self.target_update_freq == 0:
            self.update_target_model()
        
        # Decaer epsilon para reducir exploración
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        
        # Actualizar historial de entrenamiento
        self.training_history['loss'].append(loss)
        q_values = self.model.predict(states, verbose=0)
        self.training_history['mean_q'].append(float(np.mean(q_values)))
        
        return loss
    
    def calculate_reward(self, action_success, action_relevance, metrics_improvement, time_to_resolution):
        """
        Calcula la recompensa para una acción tomada
        
        Args:
            action_success: Booleano que indica si la acción tuvo éxito (True) o falló (False)
            action_relevance: Puntuación 0-1 que indica cuán relevante fue la acción
            metrics_improvement: Cambio en métricas clave (positivo = mejora)
            time_to_resolution: Tiempo que tomó resolver el problema (menor = mejor)
            
        Returns:
            Valor de recompensa
        """
        # Recompensa base por éxito/fallo
        base_reward = 1.0 if action_success else -1.0
        
        # Factor de relevancia (más relevante = más recompensa)
        relevance_factor = action_relevance  # Valor entre 0 y 1
        
        # Factor de mejora de métricas (más mejora = más recompensa)
        # Normalizado entre -1 y 1
        improvement_factor = np.clip(metrics_improvement / 10.0, -1.0, 1.0)
        
        # Factor de tiempo (menos tiempo = más recompensa)
        # Normalizado para que 0 min = 1, 60 min = 0
        time_factor = max(0, 1.0 - (time_to_resolution / 60.0))
        
        # Calcular recompensa total
        reward = base_reward * (
            0.4 +                     # Componente base
            0.3 * relevance_factor +  # Componente de relevancia
            0.2 * improvement_factor + # Componente de mejora
            0.1 * time_factor          # Componente de tiempo
        )
        
        return reward
    
    def get_q_values(self, state):
        """Obtiene los Q-values para un estado dado"""
        state_array = np.reshape(state, [1, self.state_dim])
        return self.model.predict(state_array, verbose=0)[0]
    
    def save(self, folder_path):
        """Guarda el modelo y estado del agente"""
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        
        # Guardar modelo principal
        self.model.save(os.path.join(folder_path, 'rl_model.h5'))
        
        # Guardar estado del agente
        agent_state = {
            'epsilon': self.epsilon,
            'update_counter': self.update_counter,
            'training_history': self.training_history
        }
        
        with open(os.path.join(folder_path, 'agent_state.json'), 'w') as f:
            json.dump(agent_state, f)
        
        # Guardar memoria de experiencias (opcional)
        if len(self.memory) > 0:
            # Convertir deque a lista para serialización
            memory_list = list(self.memory)
            joblib.dump(memory_list, os.path.join(folder_path, 'memory.joblib'))
        
        logger.info(f"Agente RL guardado en {folder_path}")
    
    def load(self, folder_path):
        """Carga el modelo y estado del agente"""
        if not os.path.exists(folder_path):
            logger.error(f"Ruta {folder_path} no existe")
            return False
        
        try:
            # Cargar modelo principal
            model_path = os.path.join(folder_path, 'rl_model.h5')
            if os.path.exists(model_path):
                self.model = load_model(model_path)
                self.target_model = load_model(model_path)
            
            # Cargar estado del agente
            state_path = os.path.join(folder_path, 'agent_state.json')
            if os.path.exists(state_path):
                with open(state_path, 'r') as f:
                    agent_state = json.load(f)
                
                self.epsilon = agent_state.get('epsilon', self.epsilon)
                self.update_counter = agent_state.get('update_counter', 0)
                self.training_history = agent_state.get('training_history', self.training_history)
            
            # Cargar memoria (opcional)
            memory_path = os.path.join(folder_path, 'memory.joblib')
            if os.path.exists(memory_path):
                memory_list = joblib.load(memory_path)
                self.memory = deque(memory_list, maxlen=self.memory_size)
            
            logger.info(f"Agente RL cargado desde {folder_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error al cargar agente RL: {str(e)}")
            return False


class ActionRecommender:
    """
    Recomendador de acciones correctivas basado en reglas y refuerzo
    que selecciona y ejecuta acciones de remediación para problemas detectados.
    """
    
    def __init__(self, config=None, engine=None, kafka_producer=None):
        """
        Inicializa el recomendador de acciones.
        
        Args:
            config: Configuración del recomendador
            engine: Conexión a la base de datos
            kafka_producer: Productor Kafka para publicar recomendaciones
        """
        self.config = config or {}
        self.engine = engine
        self.kafka_producer = kafka_producer
        
        # Directorio de configuración
        self.config_dir = self.config.get('config_dir', '/app/config')
        
        # Cargar políticas de acción
        self.action_policies = {}
        self.load_action_policies()
        
        # Ejecutor de acciones
        self.action_executor = ActionExecutor(self.config)
        
        # Historial de acciones
        self.action_history = deque(maxlen=1000)
        
        # Caché de mejor acción conocida por servicio
        self.best_action_cache = {}
        
        # Inicializar agentes RL por servicio
        self.rl_agents = {}
        self.state_features = {}  # Características para vectores de estado por servicio
        self.reinforcement_learning = True  # Bandera para habilitar/deshabilitar RL
        
        # Parámetros RL
        self.rl_update_frequency = 10  # Número de acciones antes de entrenar
        self.action_counter = 0
        
        # Política de A/B testing
        self.ab_testing_enabled = self.config.get('ab_testing_enabled', True)
        self.exploration_rate = self.config.get('exploration_rate', 0.2)
        
        # Directorio para modelos RL
        self.models_dir = self.config.get('models_dir', '/app/models/recommender')
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Inicializar agentes para servicios conocidos
        self.initialize_rl_agents()
        
        logger.info("Recomendador de acciones inicializado")
    
    def load_action_policies(self):
        """Carga las políticas de acción desde archivos de configuración"""
        try:
            # Cargar políticas predefinidas
            policy_file = os.path.join(self.config_dir, 'action_policies.json')
            
            if os.path.exists(policy_file):
                with open(policy_file, 'r') as f:
                    self.action_policies = json.load(f)
                    
                logger.info(f"Políticas de acción cargadas: {len(self.action_policies)} servicios")
            else:
                # Cargar políticas por defecto
                self.load_default_policies()
                logger.warning("No se encontró archivo de políticas, usando valores por defecto")
        
        except Exception as e:
            logger.error(f"Error al cargar políticas de acción: {str(e)}")
            # Cargar políticas por defecto
            self.load_default_policies()
    
    def load_default_policies(self):
        """Carga políticas de acción por defecto"""
        try:
            # Políticas por defecto para servicios comunes
            self.action_policies = {
                # Políticas para servicios web
                "web_service": {
                    "description": "Acciones para servicios web basados en Node.js/Express",
                    "actions": {
                        "restart_service": {
                            "description": "Reinicia el servicio web",
                            "command": "kubectl rollout restart deployment ${service_id}",
                            "conditions": {
                                "metrics": {
                                    "memory_usage": "> 85",
                                    "response_time_ms": "> 500"
                                },
                                "anomaly_score": "> 0.8"
                            },
                            "priority": "medium"
                        },
                        "scale_up": {
                            "description": "Escala horizontalmente el servicio",
                            "command": "kubectl scale deployment ${service_id} --replicas=${replicas}",
                            "conditions": {
                                "metrics": {
                                    "cpu_usage": "> 80",
                                    "active_connections": "> 1000"
                                },
                                "failure_probability": "> 0.7"
                            },
                            "parameters": {
                                "replicas": "auto"  # Se calcula automáticamente
                            },
                            "priority": "high"
                        },
                        "clear_cache": {
                            "description": "Limpia la caché del servicio",
                            "command": "kubectl exec $(kubectl get pods -l app=${service_id} -o jsonpath='{.items[0].metadata.name}') -- curl -X POST http://localhost:${port}/api/cache/clear",
                            "conditions": {
                                "metrics": {
                                    "memory_usage": "> 75",
                                    "response_time_ms": "> 300"
                                }
                            },
                            "parameters": {
                                "port": "3000"  # Puerto por defecto
                            },
                            "priority": "low"
                        }
                    }
                },
                
                # Políticas para bases de datos PostgreSQL
                "postgres_service": {
                    "description": "Acciones para servicios PostgreSQL",
                    "actions": {
                        "connection_pool_increase": {
                            "description": "Aumenta el pool de conexiones",
                            "command": "kubectl exec ${service_id}-0 -- psql -c \"ALTER SYSTEM SET max_connections = ${max_connections}; SELECT pg_reload_conf();\"",
                            "conditions": {
                                "metrics": {
                                    "active_connections": "> 80",
                                    "connection_wait_time": "> 100"
                                }
                            },
                            "parameters": {
                                "max_connections": "200"
                            },
                            "priority": "high"
                        },
                        "vacuum_analyze": {
                            "description": "Ejecuta VACUUM ANALYZE",
                            "command": "kubectl exec ${service_id}-0 -- psql -c \"VACUUM ANALYZE;\"",
                            "conditions": {
                                "metrics": {
                                    "query_execution_time_avg": "> 500",
                                    "dead_tuples": "> 10000"
                                }
                            },
                            "priority": "medium"
                        },
                        "pg_restart": {
                            "description": "Reinicia PostgreSQL",
                            "command": "kubectl exec ${service_id}-0 -- pg_ctl restart",
                            "conditions": {
                                "metrics": {
                                    "memory_usage": "> 90",
                                    "query_execution_time_avg": "> 1000"
                                },
                                "anomaly_score": "> 0.9"
                            },
                            "priority": "critical"
                        }
                    }
                },
                
                # Políticas para servicios Redis
                "redis_service": {
                    "description": "Acciones para servicios Redis",
                    "actions": {
                        "redis_memory_purge": {
                            "description": "Purga de memoria de Redis",
                            "command": "kubectl exec ${service_id}-0 -- redis-cli MEMORY PURGE",
                            "conditions": {
                                "metrics": {
                                    "memory_fragmentation_ratio": "> 2.0"
                                }
                            },
                            "priority": "high"
                        },
                        "redis_client_kill": {
                            "description": "Mata conexiones inactivas",
                            "command": "kubectl exec ${service_id}-0 -- redis-cli CLIENT KILL TYPE normal IDLE ${idle_seconds}",
                            "conditions": {
                                "metrics": {
                                    "connected_clients": "> 1000"
                                }
                            },
                            "parameters": {
                                "idle_seconds": "60"
                            },
                            "priority": "medium"
                        },
                        "redis_config_maxmemory": {
                            "description": "Configura límite de memoria",
                            "command": "kubectl exec ${service_id}-0 -- redis-cli CONFIG SET maxmemory ${maxmemory}mb",
                            "conditions": {
                                "metrics": {
                                    "memory_usage": "> 80",
                                }
                            },
                            "parameters": {
                                "maxmemory": "1024"
                            },
                            "priority": "medium"
                        }
                    }
                }
            }
            
            # Guardar políticas por defecto en archivo
            policy_file = os.path.join(self.config_dir, 'action_policies.json')
            os.makedirs(os.path.dirname(policy_file), exist_ok=True)
            
            with open(policy_file, 'w') as f:
                json.dump(self.action_policies, f, indent=2)
            
            logger.info("Políticas por defecto cargadas y guardadas")
            
        except Exception as e:
            logger.error(f"Error al cargar políticas por defecto: {str(e)}")
    
    def initialize_rl_agents(self):
        """Inicializa agentes RL para servicios conocidos"""
        try:
            for service_id in self.action_policies.keys():
                self.initialize_rl_agent_for_service(service_id)
        except Exception as e:
            logger.error(f"Error al inicializar agentes RL: {str(e)}")
    
    def initialize_rl_agent_for_service(self, service_id):
        """Inicializa un agente RL para un servicio específico"""
        try:
            if service_id not in self.action_policies:
                logger.warning(f"No hay política definida para servicio {service_id}")
                return
            
            # Definir características para el vector de estado
            features = self.define_state_features(service_id)
            self.state_features[service_id] = features
            
            # Número de acciones posibles
            num_actions = len(self.action_policies[service_id].get('actions', {}))
            
            if num_actions == 0:
                logger.warning(f"No hay acciones definidas para servicio {service_id}")
                return
            
            # Crear agente RL
            agent = RLActionRecommender(
                state_dim=len(features) + 2,  # +2 para flags de tipo de problema
                action_dim=num_actions,
                memory_size=2000,
                batch_size=32,
                gamma=0.95,
                epsilon=1.0,
                epsilon_min=0.1,
                epsilon_decay=0.995
            )
            
            # Intentar cargar modelo preentrenado
            agent_path = os.path.join(self.models_dir, f"rl_agent_{service_id}")
            if os.path.exists(agent_path):
                agent.load(agent_path)
            
            # Almacenar agente
            self.rl_agents[service_id] = agent
            logger.info(f"Agente RL inicializado para servicio {service_id} con {num_actions} acciones")
            
        except Exception as e:
            logger.error(f"Error al inicializar agente RL para servicio {service_id}: {str(e)}")
    
    def define_state_features(self, service_id):
        """Define las características del vector de estado para un servicio"""
        features = []
        
        # Características comunes
        common_features = [
            'anomaly_score', 'failure_probability', 'cpu_usage', 
            'memory_usage', 'disk_usage_percent', 'connection_count',
            'response_time_ms', 'error_rate', 'request_rate'
        ]
        
        # Extraer métricas mencionadas en las condiciones de las acciones
        policy = self.action_policies.get(service_id, {})
        action_metrics = set()
        
        for action_id, action_def in policy.get('actions', {}).items():
            conditions = action_def.get('conditions', {})
            metrics = conditions.get('metrics', {})
            for metric_name in metrics.keys():
                action_metrics.add(metric_name)
        
        # Combinar características comunes y específicas
        features = list(common_features)
        features.extend([m for m in action_metrics if m not in common_features])
        
        return features
    
    def prepare_state_vector(self, service_id, metrics, issue_type):
        """Prepara el vector de estado para el agente RL"""
        if service_id not in self.state_features:
            self.initialize_rl_agent_for_service(service_id)
        
        features = self.state_features.get(service_id, [])
        state = np.zeros(len(features))
        
        # Llenar vector de estado con métricas disponibles
        for i, feature in enumerate(features):
            # Obtener valor de la métrica, 0 si no existe
            value = float(metrics.get(feature, 0.0))
            state[i] = value
        
        # Añadir bandera de tipo de problema (anomalía o predicción)
        if issue_type == 'anomaly':
            state = np.append(state, [1.0, 0.0])
        elif issue_type == 'prediction':
            state = np.append(state, [0.0, 1.0])
        else:
            state = np.append(state, [0.0, 0.0])
        
        return state
    
    def select_action_with_ab_testing(self, service_id, matching_actions, metrics):
        """Selecciona acción usando A/B testing para optimización continua"""
        experiment_id = f"exp_{int(time.time())}"
        
        # Dividir en grupos (80% mejor acción conocida, 20% exploración)
        if (service_id in self.best_action_cache and 
            random.random() > self.exploration_rate):
            # Usar mejor acción conocida (explotación)
            best_action_id = self.best_action_cache[service_id]
            
            # Encontrar acción en matching_actions
            selected_action = None
            for action in matching_actions:
                if action['action_id'] == best_action_id:
                    selected_action = action
                    break
            
            # Si no se encuentra (o no coincide con las condiciones actuales), seleccionar aleatoriamente
            if selected_action is None:
                selected_action = random.choice(matching_actions)
                group = "experiment"
            else:
                group = "control"
        else:
            # Seleccionar acción aleatoria (exploración)
            selected_action = random.choice(matching_actions)
            group = "experiment"
        
        # Registrar experimento
        experiment_data = {
            'experiment_id': experiment_id,
            'service_id': service_id,
            'action_id': selected_action['action_id'],
            'group': group,
            'metrics_before': metrics,
            'timestamp': datetime.now().isoformat()
        }
        
        # Almacenar experimento en base de datos si hay conexión
        if self.engine:
            try:
                experiment_df = pd.DataFrame([experiment_data])
                experiment_df.to_sql('ab_experiments', self.engine, if_exists='append', index=False)
            except Exception as e:
                logger.error(f"Error al almacenar experimento: {str(e)}")
        
        return selected_action
    
    def update_ab_test_results(self, experiment_id, metrics_after, success):
        """Actualiza resultados de experimento A/B"""
        if not self.engine:
            return
        
        try:
            # Actualizar experimento con resultados
            update_query = f"""
                UPDATE ab_experiments
                SET metrics_after = '{json.dumps(metrics_after)}',
                    success = {success},
                    completed_at = '{datetime.now().isoformat()}'
                WHERE experiment_id = '{experiment_id}'
            """
            
            self.engine.execute(update_query)
            logger.debug(f"Resultados de experimento {experiment_id} actualizados")
            
        except Exception as e:
            logger.error(f"Error al actualizar resultados de experimento: {str(e)}")
    
    def check_condition(self, condition, metrics):
        """
        Verifica si una condición se cumple con las métricas dadas.
        
        Args:
            condition: Condición a verificar (string con operador)
            metrics: Diccionario de métricas
            
        Returns:
            bool: True si la condición se cumple
        """
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
                # Si no es número, usar como string
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
        """
        Verifica si todas las condiciones se cumplen.
        
        Args:
            conditions: Diccionario de condiciones
            metrics: Diccionario de métricas
            
        Returns:
            bool: True si todas las condiciones se cumplen
        """
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
        """
        Encuentra acciones que coinciden con las métricas actuales.
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario de métricas
            
        Returns:
            list: Lista de acciones coincidentes
        """
        matching_actions = []
        
        # Verificar si tenemos políticas para este servicio
        if service_id not in self.action_policies:
            # Intentar determinar tipo de servicio
            service_type = self.detect_service_type(service_id, metrics)
            if service_type and service_type in self.action_policies:
                effective_service_id = service_type
            else:
                logger.warning(f"No hay políticas definidas para {service_id}")
                return []
        else:
            effective_service_id = service_id
        
        # Obtener acciones para este servicio
        service_actions = self.action_policies[effective_service_id].get('actions', {})
        
        # Verificar cada acción
        for action_id, action_def in service_actions.items():
            # Verificar condiciones
            if 'conditions' in action_def:
                if self.check_conditions(action_def['conditions'], metrics):
                    # Crear copia de la acción para añadir contexto
                    action = action_def.copy()
                    action['action_id'] = action_id
                    action['service_id'] = service_id  # Usar el service_id original
                    action['effective_service_id'] = effective_service_id  # Guardar el tipo efectivo
                    
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
    
    def detect_service_type(self, service_id, metrics):
        """
        Intenta detectar el tipo de servicio basado en métricas disponibles.
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario de métricas
            
        Returns:
            str: Tipo de servicio detectado o None
        """
        # Intentar determinar tipo basado en nombre
        service_name = service_id.lower()
        
        if 'postgres' in service_name or 'postgresql' in service_name or 'pg' in service_name:
            return 'postgres_service'
        elif 'redis' in service_name or 'cache' in service_name:
            return 'redis_service'
        elif ('web' in service_name or 'api' in service_name or 'app' in service_name or 
              'service' in service_name):
            return 'web_service'
        
        # Intentar determinar tipo basado en métricas disponibles
        if 'query_execution_time_avg' in metrics or 'dead_tuples' in metrics:
            return 'postgres_service'
        elif 'memory_fragmentation_ratio' in metrics or 'connected_clients' in metrics:
            return 'redis_service'
        elif 'response_time_ms' in metrics or 'active_connections' in metrics:
            return 'web_service'
        
        # No se pudo determinar
        return None
    
    def recommend_action(self, service_id, metrics, issue_type):
        """
        Recomienda la mejor acción para un problema detectado.
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario de métricas
            issue_type: Tipo de problema ('anomaly' o 'prediction')
            
        Returns:
            dict: Acción recomendada o None si no hay recomendación
        """
        try:
            logger.info(f"Buscando acción para {service_id} con issue_type={issue_type}")
            
            # Encontrar acciones que coinciden con las métricas
            matching_actions = self.find_matching_actions(service_id, metrics)
            
            if not matching_actions:
                logger.warning(f"No hay acciones disponibles para {service_id} con las métricas actuales")
                return None
            
            # Si hay solo una acción coincidente, usarla
            if len(matching_actions) == 1:
                return matching_actions[0]
            
            # Si A/B testing está habilitado, usar esa estrategia
            if self.ab_testing_enabled:
                return self.select_action_with_ab_testing(service_id, matching_actions, metrics)
            
            # Si RL está deshabilitado, usar el enfoque basado en reglas (primera acción)
            if not self.reinforcement_learning:
                return matching_actions[0]
            
            # Preparar el estado para el modelo RL
            state = self.prepare_state_vector(service_id, metrics, issue_type)
            
            # Verificar si existe agente para este servicio
            if service_id not in self.rl_agents:
                self.initialize_rl_agent_for_service(service_id)
                # Si falla la inicialización, usar enfoque basado en reglas
                if service_id not in self.rl_agents:
                    return matching_actions[0]
            
            # Obtener agente RL
            agent = self.rl_agents[service_id]
            
            # Seleccionar acción usando agente RL
            action_idx = agent.act(state)
            
            # Asegurar que el índice está dentro del rango
            action_idx = min(action_idx, len(matching_actions) - 1)
            
            # Obtener acción recomendada
            recommended_action = matching_actions[action_idx]
            
            # Almacenar estado para actualización posterior
            recommended_action['_rl_state'] = state
            
            # Mostrar Q-values para diagnóstico
            q_values = agent.get_q_values(state)
            logger.debug(f"Q-values para {service_id}: {q_values}")
            
            # Registrar acción recomendada
            logger.info(f"Acción recomendada para {service_id}: {recommended_action['action_id']}")
            
            return recommended_action
                
        except Exception as e:
            logger.error(f"Error al recomendar acción: {str(e)}")
            if len(matching_actions) > 0:
                return matching_actions[0]  # Fallback a la primera acción
            return None
    
    def recommend_scaling_action(self, service_id, prediction_horizon, failure_probability):
        """
        Recomienda acciones de escalado automático basadas en predicciones.
        
        Args:
            service_id: ID del servicio
            prediction_horizon: Horizonte de predicción en horas
            failure_probability: Probabilidad de fallo
        
        Returns:
            dict: Recomendación de escalado
        """
        try:
            # Obtener réplicas actuales
            current_replicas = 1  # Valor por defecto
            
            try:
                # En un entorno real, esto obtendría las réplicas actuales de Kubernetes
                cmd = f"kubectl get deployment {service_id} -o jsonpath='{{.spec.replicas}}'"
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    current_replicas = int(result.stdout.strip())
            except:
                # Si falla, usar valor por defecto
                pass
            
            # Determinar acción basada en probabilidad y horizonte
            if failure_probability > 0.8 and prediction_horizon <= 1:
                # Fallo inminente, escalar inmediatamente
                return {
                    'action': 'scale_up',
                    'replicas': current_replicas + 2,
                    'urgency': 'immediate'
                }
            elif failure_probability > 0.6 and prediction_horizon <= 3:
                # Fallo probable, escalar preventivamente
                return {
                    'action': 'scale_up',
                    'replicas': current_replicas + 1,
                    'urgency': 'high'
                }
            elif failure_probability < 0.2 and current_replicas > 1:
                # Baja probabilidad, considerar escalar hacia abajo
                return {
                    'action': 'scale_down',
                    'replicas': max(1, current_replicas - 1),
                    'urgency': 'low'
                }
            else:
                # Mantener réplicas actuales
                return {
                    'action': 'maintain',
                    'replicas': current_replicas,
                    'urgency': 'none'
                }
                
        except Exception as e:
            logger.error(f"Error al recomendar acción de escalado: {str(e)}")
            return {
                'action': 'maintain',
                'replicas': 1,
                'urgency': 'none',
                'error': str(e)
            }
    
    def update_rl_from_action_result(self, service_id, action, state, success, metrics_before, metrics_after):
        """
        Actualiza el agente RL con los resultados de una acción.
        
        Args:
            service_id: ID del servicio
            action: Acción ejecutada
            state: Estado antes de la acción
            success: Si la acción tuvo éxito
            metrics_before: Métricas antes de la acción
            metrics_after: Métricas después de la acción
        """
        try:
            if not self.reinforcement_learning or service_id not in self.rl_agents:
                return
            
            # Obtener agente RL
            agent = self.rl_agents[service_id]
            
            # Obtener índice de la acción
            action_id = action['action_id']
            effective_service_id = action.get('effective_service_id', service_id)
            policy = self.action_policies.get(effective_service_id, {})
            action_ids = list(policy.get('actions', {}).keys())
            
            if action_id not in action_ids:
                logger.warning(f"Acción {action_id} no encontrada en política para {effective_service_id}")
                return
            
            action_idx = action_ids.index(action_id)
            
            # Calcular recompensa
            # 1. Éxito de la acción
            action_success = 1.0 if success else -1.0
            
            # 2. Relevancia de la acción (basada en la prioridad)
            priority_map = {
                'critical': 1.0,
                'high': 0.8,
                'medium': 0.5,
                'low': 0.3
            }
            action_relevance = priority_map.get(action.get('priority', 'medium'), 0.5)
            
            # 3. Mejora en métricas
            metrics_improvement = self.calculate_metrics_improvement(metrics_before, metrics_after)
            
            # 4. Tiempo de resolución (simplificado)
            time_to_resolution = 10.0  # Valor fijo para este ejemplo
            
            # Calcular recompensa total
            reward = agent.calculate_reward(
                action_success=(success is True),
                action_relevance=action_relevance,
                metrics_improvement=metrics_improvement,
                time_to_resolution=time_to_resolution
            )
            
            # El próximo estado es el estado actual después de la acción
            next_state = self.prepare_state_vector(service_id, metrics_after, 'resolved')
            
            # Indicar si el episodio ha terminado
            done = success is True
            
            # Recordar experiencia
            agent.remember(state, action_idx, reward, next_state, done)
            
            # Incrementar contador de acciones
            self.action_counter += 1
            
            # Entrenar agente periódicamente
            if self.action_counter % self.rl_update_frequency == 0:
                loss = agent.replay()
                logger.debug(f"Agente RL para {service_id} entrenado, loss={loss:.4f}")
            
            # Guardar agente periódicamente
            if self.action_counter % 100 == 0:
                agent_path = os.path.join(self.models_dir, f"rl_agent_{service_id}")
                agent.save(agent_path)
                logger.info(f"Agente RL para {service_id} guardado en {agent_path}")
            
            # Si la acción fue exitosa con una buena recompensa, actualizamos la caché de mejor acción
            if success and reward > 1.0:
                self.best_action_cache[service_id] = action_id
                logger.info(f"Acción {action_id} guardada como mejor acción para {service_id}")
            
        except Exception as e:
            logger.error(f"Error al actualizar RL con resultado de acción: {str(e)}")
    
    def calculate_metrics_improvement(self, metrics_before, metrics_after):
        """
        Calcula la mejora en las métricas clave después de una acción.
        
        Args:
            metrics_before: Métricas antes de la acción
            metrics_after: Métricas después de la acción
            
        Returns:
            float: Puntuación de mejora
        """
        try:
            improvement = 0.0
            
            # Métricas clave a considerar
            key_metrics = [
                'cpu_usage', 'memory_usage', 'disk_usage_percent',
                'response_time_ms', 'error_rate', 'connection_count'
            ]
            
            # Calcular mejora ponderada
            weights = {
                'cpu_usage': 1.0,
                'memory_usage': 1.0,
                'disk_usage_percent': 0.8,
                'response_time_ms': 1.2,
                'error_rate': 1.5,
                'connection_count': 0.6
            }
            
            total_weight = 0
            
            for metric in key_metrics:
                if metric in metrics_before and metric in metrics_after:
                    # Para métricas donde menor es mejor
                    if metric in ['cpu_usage', 'memory_usage', 'disk_usage_percent', 
                                'response_time_ms', 'error_rate']:
                        change = metrics_before[metric] - metrics_after[metric]
                    else:  # Para métricas donde mayor es mejor
                        change = metrics_after[metric] - metrics_before[metric]
                    
                    # Ponderar cambio
                    weight = weights.get(metric, 1.0)
                    improvement += change * weight
                    total_weight += weight
            
            # Normalizar
            if total_weight > 0:
                improvement /= total_weight
            
            return improvement
            
        except Exception as e:
            logger.error(f"Error al calcular mejora de métricas: {str(e)}")
            return 0.0
    
    def simulate_metrics_after_action(self, metrics_before, action):
        """
        Simula las métricas después de ejecutar una acción (solo para demo).
        
        Args:
            metrics_before: Métricas antes de la acción
            action: Acción ejecutada
            
        Returns:
            dict: Métricas simuladas después de la acción
        """
        metrics_after = metrics_before.copy()
        
        # Simular mejoras basadas en el tipo de acción
        action_id = action['action_id']
        
        if 'cpu' in action_id.lower() or 'scale' in action_id.lower():
            # Simular mejora en CPU
            if 'cpu_usage' in metrics_after:
                metrics_after['cpu_usage'] = max(10.0, metrics_after['cpu_usage'] * 0.7)
        
        elif 'memory' in action_id.lower():
            # Simular mejora en memoria
            if 'memory_usage' in metrics_after:
                metrics_after['memory_usage'] = max(15.0, metrics_after['memory_usage'] * 0.6)
            if 'memory_growth_rate' in metrics_after:
                metrics_after['memory_growth_rate'] = max(0.0, metrics_after['memory_growth_rate'] * 0.1)
        
        elif 'connection' in action_id.lower():
            # Simular mejora en conexiones
            if 'connection_wait_time' in metrics_after:
                metrics_after['connection_wait_time'] = max(10.0, metrics_after['connection_wait_time'] * 0.4)
            if 'active_connections' in metrics_after:
                metrics_after['active_connections'] = max(5.0, metrics_after['active_connections'] * 0.8)
        
        elif 'disk' in action_id.lower():
            # Simular mejora en disco
            if 'disk_usage_percent' in metrics_after:
                metrics_after['disk_usage_percent'] = max(20.0, metrics_after['disk_usage_percent'] * 0.8)
        
        elif 'restart' in action_id.lower():
            # Simular reinicio completo
            for metric in metrics_after:
                if isinstance(metrics_after[metric], (int, float)):
                    if metric == 'uptime_seconds':
                        metrics_after[metric] = 0
                    elif metric in ['cpu_usage', 'memory_usage', 'response_time_ms', 'error_rate']:
                        metrics_after[metric] = max(metrics_after[metric] * 0.4, 5.0)
        
        # Simular mejora general en tiempo de respuesta
        if 'response_time_ms' in metrics_after:
            metrics_after['response_time_ms'] = max(50.0, metrics_after['response_time_ms'] * 0.7)
        
        return metrics_after
    
    def execute_action(self, action, metrics, variables=None):
        """
        Ejecuta una acción de remediación.
        
        Args:
            action: Diccionario con la acción a ejecutar
            metrics: Métricas actuales
            variables: Variables adicionales para la acción
            
        Returns:
            bool: True si la acción se ejecutó con éxito
        """
        try:
            if not action:
                logger.warning("No se proporcionó acción para ejecutar")
                return False
            
            # Extraer información de la acción
            action_id = action.get('action_id', 'unknown_action')
            service_id = action.get('service_id', 'unknown_service')
            command_template = action.get('command', '')
            
            if not command_template:
                logger.warning(f"No hay comando definido para acción {action_id}")
                return False
            
            # Combinar parámetros de la acción y variables adicionales
            params = action.get('parameters', {}).copy()
            if variables:
                params.update(variables)
            
            # Añadir service_id como parámetro
            params['service_id'] = service_id
            
            # Almacenar métricas antes de la acción
            metrics_before = metrics.copy()
            
            # Calcular parámetros automáticos
            self.calculate_auto_parameters(params, metrics)
            
            # Construir comando con plantilla
            template = Template(command_template)
            try:
                command = template.substitute(params)
            except KeyError as e:
                logger.error(f"Parámetro faltante en comando: {str(e)}")
                return False
            
            logger.info(f"Ejecutando acción {action_id} para {service_id}: {command}")
            
            # En un entorno real, aquí ejecutaríamos el comando
            # Para este ejemplo, simulamos éxito con alta probabilidad
            success = random.random() < 0.9
            
            # Registrar resultado
            if success:
                logger.info(f"Acción {action_id} ejecutada exitosamente para {service_id}")
            else:
                logger.error(f"Error al ejecutar acción {action_id} para {service_id}")
            
            # Registrar acción en historial
            action_record = {
                'action_id': action_id,
                'service_id': service_id,
                'command': command,
                'timestamp': datetime.now().isoformat(),
                'success': success,
                'metrics_before': metrics_before
            }
            
            self.action_history.append(action_record)
            
            # Si es una acción real con ejecución de comando, descomentar:
            """
            try:
                result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=60)
                success = result.returncode == 0
                
                if success:
                    logger.info(f"Acción {action_id} ejecutada exitosamente: {result.stdout}")
                else:
                    logger.error(f"Error al ejecutar acción {action_id}: {result.stderr}")
                
                action_record['output'] = result.stdout
                action_record['error'] = result.stderr
                
            except subprocess.TimeoutExpired:
                logger.error(f"Timeout al ejecutar acción {action_id}")
                success = False
                action_record['error'] = "Comando excedió tiempo límite"
            """
            
            # Recopilar métricas después de la acción
            # En un caso real, esperaríamos unos segundos y obtendríamos métricas reales
            # Para este ejemplo, simulamos una mejora
            metrics_after = self.simulate_metrics_after_action(metrics_before, action)
            
            # Actualizar registro con métricas posteriores
            action_record['metrics_after'] = metrics_after
            
            # Actualizar agente RL con resultado si disponible
            if '_rl_state' in action:
                self.update_rl_from_action_result(
                    service_id,
                    action,
                    action['_rl_state'],
                    success,
                    metrics_before,
                    metrics_after
                )
            
            # Publicar resultado en Kafka si hay productor
            if self.kafka_producer:
                try:
                    self.kafka_producer.send('action_results', action_record)
                except Exception as e:
                    logger.error(f"Error al publicar resultado en Kafka: {str(e)}")
            
            # Almacenar en base de datos si hay conexión
            if self.engine:
                try:
                    # Convertir a formato aceptado por SQL
                    record_for_db = action_record.copy()
                    record_for_db['metrics_before'] = json.dumps(record_for_db['metrics_before'])
                    record_for_db['metrics_after'] = json.dumps(record_for_db['metrics_after'])
                    
                    # Insertar en base de datos
                    record_df = pd.DataFrame([record_for_db])
                    record_df.to_sql('action_history', self.engine, if_exists='append', index=False)
                except Exception as e:
                    logger.error(f"Error al almacenar acción en base de datos: {str(e)}")
            
            return success
                
        except Exception as e:
            logger.error(f"Error al ejecutar acción: {str(e)}")
            return False
    
    def calculate_auto_parameters(self, params, metrics):
        """
        Calcula parámetros automáticos basados en métricas.
        
        Args:
            params: Diccionario de parámetros a actualizar
            metrics: Métricas actuales
        """
        # Calcular réplicas si está marcado como auto
        if 'replicas' in params and params['replicas'] == 'auto':
            # Base: calcular basado en CPU o carga
            base_replicas = 1
            
            if 'cpu_usage' in metrics:
                cpu_usage = metrics['cpu_usage']
                # Escalamos basado en uso de CPU
                if cpu_usage > 80:
                    base_replicas = 3
                elif cpu_usage > 60:
                    base_replicas = 2
            
            # También considerar solicitudes activas si disponible
            if 'active_connections' in metrics:
                connections = metrics['active_connections']
                conn_replicas = max(1, int(connections / 500))
                base_replicas = max(base_replicas, conn_replicas)
            
            # Actualizar parámetro
            params['replicas'] = str(base_replicas)
        
        # Calcular max_connections si es auto
        if 'max_connections' in params and params['max_connections'] == 'auto':
            if 'active_connections' in metrics:
                # Calcular conexiones máximas basado en activas
                active = metrics['active_connections']
                # Fórmula: 2x conexiones activas + 50, mínimo 100
                max_conn = max(100, int(active * 2) + 50)
                params['max_connections'] = str(max_conn)
            else:
                # Valor por defecto si no hay métricas
                params['max_connections'] = '200'
    
    def process_and_recommend(self, anomaly_data=None, prediction_data=None):
        """
        Procesa datos de anomalías o predicciones y recomienda acciones.
        
        Args:
            anomaly_data: Datos de anomalía detectada
            prediction_data: Datos de predicción de fallo
            
        Returns:
            dict: Resultado del procesamiento
        """
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


class ActionExecutor:
    """
    Ejecutor de acciones que maneja la ejecución real de comandos
    y realiza seguimiento de resultados.
    """
    
    def __init__(self, config=None):
        """
        Inicializa el ejecutor de acciones.
        
        Args:
            config: Configuración del ejecutor
        """
        self.config = config or {}
        
        # Límites de seguridad
        self.max_concurrent_actions = self.config.get('max_concurrent_actions', 5)
        self.execution_timeout = self.config.get('execution_timeout', 60)  # Segundos
        self.cooldown_period = self.config.get('cooldown_period', 300)  # Segundos
        
        # Registro de acciones recientes
        self.recent_actions = {}  # Por servicio
        
        # Semáforo para limitar acciones concurrentes
        self.action_semaphore = threading.Semaphore(self.max_concurrent_actions)
        
        logger.info(f"Ejecutor de acciones inicializado con límite de {self.max_concurrent_actions} acciones concurrentes")
    
    def can_execute_action(self, service_id, action_id):
        """
        Verifica si es seguro ejecutar una acción para un servicio.
        
        Args:
            service_id: ID del servicio
            action_id: ID de la acción
            
        Returns:
            bool: True si es seguro ejecutar
        """
        # Verificar si hay acción reciente para este servicio
        if service_id in self.recent_actions:
            last_action = self.recent_actions[service_id]
            time_since_last = (datetime.now() - last_action['timestamp']).total_seconds()
            
            # Verificar período de enfriamiento
            if time_since_last < self.cooldown_period:
                logger.warning(f"Acción para {service_id} rechazada: período de enfriamiento activo "
                              f"({time_since_last:.1f}s < {self.cooldown_period}s)")
                return False
            
            # Evitar repetir la misma acción
            if last_action['action_id'] == action_id and time_since_last < self.cooldown_period * 2:
                logger.warning(f"Acción {action_id} para {service_id} rechazada: misma acción reciente")
                return False
        
        return True
    
    def execute_command(self, command, timeout=None):
        """
        Ejecuta un comando shell con límite de tiempo.
        
        Args:
            command: Comando a ejecutar
            timeout: Tiempo máximo en segundos
            
        Returns:
            dict: Resultado de la ejecución
        """
        if timeout is None:
            timeout = self.execution_timeout
        
        try:
            # Ejecutar comando con timeout
            result = subprocess.run(
                command, 
                shell=True, 
                capture_output=True, 
                text=True, 
                timeout=timeout
            )
            
            return {
                'success': result.returncode == 0,
                'return_code': result.returncode,
                'stdout': result.stdout,
                'stderr': result.stderr,
                'command': command
            }
            
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout al ejecutar comando: {command}")
            return {
                'success': False,
                'return_code': -1,
                'stdout': '',
                'stderr': 'Command execution timed out',
                'command': command
            }
        except Exception as e:
            logger.error(f"Error al ejecutar comando {command}: {str(e)}")
            return {
                'success': False,
                'return_code': -1,
                'stdout': '',
                'stderr': str(e),
                'command': command
            }
    
    def execute_action(self, action, async_mode=False):
        """
        Ejecuta una acción, verificando límites de seguridad.
        
        Args:
            action: Diccionario de acción a ejecutar
            async_mode: Si es True, ejecuta en segundo plano
            
        Returns:
            dict: Resultado de la ejecución
        """
        service_id = action.get('service_id', 'unknown')
        action_id = action.get('action_id', 'unknown')
        command = action.get('command', '')
        
        if not command:
            return {
                'success': False,
                'error': 'No command provided',
                'action_id': action_id,
                'service_id': service_id
            }
        
        # Verificar si es seguro ejecutar
        if not self.can_execute_action(service_id, action_id):
            return {
                'success': False,
                'error': 'Safety check failed',
                'action_id': action_id,
                'service_id': service_id
            }
        
        # Registrar acción
        self.recent_actions[service_id] = {
            'action_id': action_id,
            'timestamp': datetime.now(),
            'command': command
        }
        
        # Ejecutar según modo
        if async_mode:
            # Ejecución asíncrona
            thread = threading.Thread(
                target=self._execute_with_semaphore,
                args=(action, command)
            )
            thread.daemon = True
            thread.start()
            
            return {
                'success': True,
                'status': 'executing',
                'action_id': action_id,
                'service_id': service_id,
                'async': True
            }
        else:
            # Ejecución síncrona
            return self._execute_with_semaphore(action, command)
    
    def _execute_with_semaphore(self, action, command):
        """
        Ejecuta un comando usando semáforo para limitar concurrencia.
        
        Args:
            action: Diccionario de acción
            command: Comando a ejecutar
            
        Returns:
            dict: Resultado de ejecución
        """
        service_id = action.get('service_id', 'unknown')
        action_id = action.get('action_id', 'unknown')
        
        # Adquirir semáforo
        acquired = self.action_semaphore.acquire(timeout=5)
        if not acquired:
            logger.warning(f"No se pudo adquirir semáforo para ejecutar {action_id}")
            return {
                'success': False,
                'error': 'Too many concurrent actions',
                'action_id': action_id,
                'service_id': service_id
            }
        
        try:
            # Ejecutar comando
            logger.info(f"Ejecutando acción {action_id} para {service_id}: {command}")
            result = self.execute_command(command)
            
            # Registrar resultado
            if result['success']:
                logger.info(f"Acción {action_id} ejecutada exitosamente: {result['stdout'][:100]}")
            else:
                logger.error(f"Error en acción {action_id}: {result['stderr'][:100]}")
            
            # Añadir información de la acción
            result['action_id'] = action_id
            result['service_id'] = service_id
            result['timestamp'] = datetime.now().isoformat()
            
            return result
            
        finally:
            # Liberar semáforo
            self.action_semaphore.release()

# Función principal de ejemplo
def main():
    """Función principal para pruebas locales"""
    # Configuración de ejemplo
    config = {
        'config_dir': './config',
        'models_dir': './models/recommender',
        'max_concurrent_actions': 3,
        'cooldown_period': 60
    }
    
    # Crear recomendador
    recommender = ActionRecommender(config=config)
    
    # Datos de ejemplo - anomalía
    anomaly_data = {
        'service_id': 'web_service',
        'anomaly_score': 0.85,
        'details': {
            'metrics': {
                'cpu_usage': 85.2,
                'memory_usage': 78.4,
                'response_time_ms': 520
            }
        }
    }
    
    # Datos de ejemplo - predicción
    prediction_data = {
        'service_id': 'postgres_service',
        'probability': 0.78,
        'prediction_horizon': 3,
        'influential_metrics': {
            'cpu_usage': 89.6,
            'memory_usage': 68.2,
            'active_connections': 95,
            'connection_wait_time': 250,
            'query_execution_time_avg': 720
        }
    }
    
    # Probar recomendación para anomalía
    print("\nProcesando anomalía...")
    anomaly_recommendation = recommender.process_and_recommend(anomaly_data=anomaly_data)
    print("Recomendación para anomalía:")
    for key, value in anomaly_recommendation.items():
        if key != 'metrics' and key != 'recommended_action':
            print(f"  {key}: {value}")
    
    print("\nAcción recomendada:")
    action = anomaly_recommendation.get('recommended_action', {})
    print(f"  ID: {action.get('action_id')}")
    print(f"  Comando: {action.get('command')}")
    print(f"  Prioridad: {action.get('priority')}")
    
    # Probar recomendación para predicción
    print("\nProcesando predicción...")
    prediction_recommendation = recommender.process_and_recommend(prediction_data=prediction_data)
    print("Recomendación para predicción:")
    for key, value in prediction_recommendation.items():
        if key != 'metrics' and key != 'recommended_action':
            print(f"  {key}: {value}")
    
    print("\nAcción recomendada:")
    action = prediction_recommendation.get('recommended_action', {})
    print(f"  ID: {action.get('action_id')}")
    print(f"  Comando: {action.get('command')}")
    print(f"  Prioridad: {action.get('priority')}")
    
    # Probar ejecución de acción (simulada)
    if action:
        print("\nEjecutando acción...")
        metrics = prediction_data.get('influential_metrics', {})
        success = recommender.execute_action(action, metrics)
        print(f"Resultado: {'Éxito' if success else 'Fallo'}")

if __name__ == "__main__":
    main()