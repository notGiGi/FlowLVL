# action_recommender/rl_agent.py

import numpy as np
import random
import tensorflow as tf
from tensorflow.keras.models import Sequential, load_model, Model
from tensorflow.keras.layers import Dense, Input, Concatenate
from tensorflow.keras.optimizers import Adam
from collections import deque
import json
import os
import logging
import joblib

logger = logging.getLogger('rl_agent')

class RLActionRecommender:
    def __init__(self, state_dim, action_dim, memory_size=2000, batch_size=32, 
                 gamma=0.95, epsilon=1.0, epsilon_min=0.01, epsilon_decay=0.995,
                 learning_rate=0.001, target_update_freq=10):
        """
        Recomendador de acciones basado en Deep Q-Learning
        
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
        model.add(Dense(64, input_dim=self.state_dim, activation='relu'))
        model.add(Dense(64, activation='relu'))
        model.add(Dense(32, activation='relu'))
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
        self.training_history['mean_q'].append(float(np.mean(self.model.predict(states, verbose=0))))
        
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
        # Normalized entre -1 y 1
        improvement_factor = np.clip(metrics_improvement / 10.0, -1.0, 1.0)
        
        # Factor de tiempo (menos tiempo = más recompensa)
        # Normalized para que 0 min = 1, 60 min = 0
        time_factor = max(0, 1.0 - (time_to_resolution / 60.0))
        
        # Calcular recompensa total
        reward = base_reward * (
            0.4 +                  # Componente base
            0.3 * relevance_factor +  # Componente de relevancia
            0.2 * improvement_factor + # Componente de mejora
            0.1 * time_factor          # Componente de tiempo
        )
        
        return reward
    
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