#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Predictive Engine - Sistema predictivo de mantenimiento para sistemas distribuidos
--------------------------------------------------------------------------------
Módulo de predicción de fallos con LSTM y mecanismo de atención.
"""

import os
import json
import logging
import numpy as np
import pandas as pd
import joblib
import time
from datetime import datetime, timedelta
from sklearn.preprocessing import StandardScaler, MinMaxScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, roc_auc_score, confusion_matrix, precision_recall_curve
import tensorflow as tf
from tensorflow.keras.models import Model, Sequential, load_model
from tensorflow.keras.layers import Input, Dense, LSTM, Dropout, TimeDistributed
from tensorflow.keras.layers import RepeatVector, Flatten, Activation, Permute, Multiply, Lambda
from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau, ModelCheckpoint
from tensorflow.keras import backend as K
import matplotlib.pyplot as plt
import seaborn as sns
import warnings

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s]: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('predictive_engine')

# Suprimir advertencias
warnings.filterwarnings("ignore")

# Configurar uso de memoria GPU si está disponible
gpus = tf.config.experimental.list_physical_devices('GPU')
if gpus:
    try:
        for gpu in gpus:
            tf.config.experimental.set_memory_growth(gpu, True)
        logger.info(f"GPU disponible para entrenamiento: {len(gpus)} dispositivos")
    except RuntimeError as e:
        logger.warning(f"Error al configurar GPU: {str(e)}")
else:
    logger.info("No se detectó GPU, usando CPU para entrenamiento")


class AttentionLayer(tf.keras.layers.Layer):
    """
    Capa de atención personalizada para LSTM
    Permite al modelo enfocarse en pasos de tiempo específicos
    """
    def __init__(self, **kwargs):
        super(AttentionLayer, self).__init__(**kwargs)
        
    def build(self, input_shape):
        # Crea los pesos para la capa de atención
        self.W = self.add_weight(
            name="attention_weight",
            shape=(input_shape[-1], 1),
            initializer="random_normal",
            trainable=True
        )
        self.b = self.add_weight(
            name="attention_bias",
            shape=(input_shape[1], 1),
            initializer="zeros",
            trainable=True
        )
        super(AttentionLayer, self).build(input_shape)
    
    def call(self, inputs):
        # Calcular puntuaciones de atención
        e = K.tanh(K.dot(inputs, self.W) + self.b)
        # Obtener pesos de atención vía softmax
        a = K.softmax(e, axis=1)
        # Aplicar atención a las entradas
        output = K.sum(inputs * a, axis=1)
        return output
    
    def compute_output_shape(self, input_shape):
        return (input_shape[0], input_shape[-1])
    
    def get_config(self):
        return super(AttentionLayer, self).get_config()


def create_attention_lstm_model(input_shape, output_shape=1, lstm_units=128, dropout_rate=0.2):
    """
    Crea un modelo LSTM con mecanismo de atención
    
    Args:
        input_shape: Forma de los datos de entrada (sequence_length, features)
        output_shape: Número de salidas (1 para clasificación binaria)
        lstm_units: Número de unidades en la capa LSTM
        dropout_rate: Tasa de dropout para regularización
    
    Returns:
        Modelo compilado
    """
    # Capa de entrada
    inputs = Input(shape=input_shape)
    
    # Primera capa LSTM (devuelve secuencias)
    lstm_out = LSTM(lstm_units, return_sequences=True)(inputs)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Segunda capa LSTM (devuelve secuencias)
    lstm_out = LSTM(lstm_units//2, return_sequences=True)(lstm_out)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Capa de atención
    attention_out = AttentionLayer()(lstm_out)
    
    # Capas densas para clasificación
    dense_out = Dense(lstm_units//4, activation='relu')(attention_out)
    dense_out = Dropout(dropout_rate)(dense_out)
    outputs = Dense(output_shape, activation='sigmoid')(dense_out)
    
    # Crear y compilar modelo
    model = Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=0.001),
        loss='binary_crossentropy',
        metrics=['accuracy']
    )
    
    return model


# Alternativa utilizando capas básicas
def create_simplified_attention_lstm(input_shape, output_shape=1, lstm_units=128, dropout_rate=0.2):
    """
    Implementación alternativa usando capas estándar de Keras
    """
    # Capa de entrada
    inputs = Input(shape=input_shape)
    
    # Primera capa LSTM
    lstm_out = LSTM(lstm_units, return_sequences=True)(inputs)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Segunda capa LSTM
    lstm_out = LSTM(lstm_units//2, return_sequences=True)(lstm_out)
    lstm_out = Dropout(dropout_rate)(lstm_out)
    
    # Mecanismo de atención
    attention = TimeDistributed(Dense(1, activation='tanh'))(lstm_out)
    attention = Flatten()(attention)
    attention = Activation('softmax')(attention)
    attention = RepeatVector(lstm_units//2)(attention)
    attention = Permute([2, 1])(attention)
    
    # Aplicar atención
    merged = Multiply()([lstm_out, attention])
    merged = Lambda(lambda x: K.sum(x, axis=1))(merged)
    
    # Capas densas finales
    dense_out = Dense(lstm_units//4, activation='relu')(merged)
    dense_out = Dropout(dropout_rate)(dense_out)
    outputs = Dense(output_shape, activation='sigmoid')(dense_out)
    
    # Crear y compilar modelo
    model = Model(inputs=inputs, outputs=outputs)
    model.compile(
        optimizer='adam',
        loss='binary_crossentropy',
        metrics=['accuracy']
    )
    
    return model


class PredictiveEngine:
    """
    Motor predictivo para sistemas distribuidos utilizando LSTM con atención
    para la predicción anticipada de fallos.
    """
    
    def __init__(self, config=None, engine=None, kafka_producer=None):
        """
        Inicializa el motor predictivo.
        
        Args:
            config: Configuración del motor predictivo
            engine: Conexión a la base de datos
            kafka_producer: Productor Kafka para publicar predicciones
        """
        self.config = config or {}
        self.engine = engine
        self.kafka_producer = kafka_producer
        
        # Parámetros de configuración
        self.models_dir = self.config.get('models_dir', '/app/models/predictive')
        self.sequence_length = self.config.get('sequence_length', 12)  # 12 puntos de tiempo
        self.prediction_threshold = self.config.get('prediction_threshold', 0.7)
        self.horizon_hours = self.config.get('horizon_hours', [1, 6, 24])  # Horizonte de predicción en horas
        self.retrain_interval = self.config.get('retrain_interval', 168)  # Reentrenar cada 7 días (en horas)
        
        # Crear directorio de modelos si no existe
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Inicializar scalers y modelos
        self.scalers = {}  # Scaler por servicio
        self.models = {}  # Modelo por servicio
        self.service_features = {}  # Características importantes por servicio
        self.model_metadata = {}  # Metadatos de modelo por servicio
        self.attention_weights = {}  # Pesos de atención por servicio
        
        # Estadísticas de predicción
        self.prediction_stats = {
            'total_predictions': 0,
            'positive_predictions': 0,
            'last_predictions': [],
            'last_update': datetime.now().isoformat()
        }
        
        # Cargar modelos existentes
        self.load_models()
        
        logger.info("Motor predictivo inicializado")
    
    def load_models(self):
        """Carga modelos predictivos previamente entrenados"""
        try:
            # Obtener lista de servicios con modelos
            services = []
            for filename in os.listdir(self.models_dir):
                if filename.endswith('_model.h5'):
                    service_id = filename.replace('_model.h5', '')
                    services.append(service_id)
            
            # Cargar modelo y scaler para cada servicio
            for service_id in services:
                model_path = os.path.join(self.models_dir, f"{service_id}_model.h5")
                scaler_path = os.path.join(self.models_dir, f"{service_id}_scaler.joblib")
                metadata_path = os.path.join(self.models_dir, f"{service_id}_metadata.json")
                
                # Cargar modelo
                if os.path.exists(model_path):
                    # Necesitamos registrar la capa personalizada para cargar el modelo
                    custom_objects = {"AttentionLayer": AttentionLayer}
                    self.models[service_id] = load_model(model_path, custom_objects=custom_objects)
                    logger.info(f"Modelo predictivo cargado para servicio {service_id}")
                
                # Cargar scaler
                if os.path.exists(scaler_path):
                    self.scalers[service_id] = joblib.load(scaler_path)
                    logger.info(f"Scaler cargado para servicio {service_id}")
                
                # Cargar metadatos
                if os.path.exists(metadata_path):
                    with open(metadata_path, 'r') as f:
                        self.model_metadata[service_id] = json.load(f)
                    logger.info(f"Metadatos cargados para servicio {service_id}")
                    
                    # Extraer características importantes
                    if 'feature_importance' in self.model_metadata[service_id]:
                        self.service_features[service_id] = self.model_metadata[service_id]['feature_importance']
                    
                    # Extraer pesos de atención si existen
                    if 'attention_weights' in self.model_metadata[service_id]:
                        self.attention_weights[service_id] = self.model_metadata[service_id]['attention_weights']
            
            # Cargar estadísticas generales si existen
            stats_path = os.path.join(self.models_dir, 'prediction_stats.json')
            if os.path.exists(stats_path):
                with open(stats_path, 'r') as f:
                    self.prediction_stats = json.load(f)
                logger.info("Estadísticas de predicción cargadas")
            
            logger.info(f"Se cargaron modelos para {len(self.models)} servicios")
            
        except Exception as e:
            logger.error(f"Error al cargar modelos: {str(e)}")
    
    def prepare_sequence_data(self, data, service_id, train_mode=False):
        """
        Prepara los datos en secuencias para entrada al modelo LSTM.
        
        Args:
            data: DataFrame con datos históricos ordenados por tiempo
            service_id: ID del servicio
            train_mode: Si es True, entrena un nuevo scaler
            
        Returns:
            Tuple: (X_sequences, y_labels)
        """
        try:
            # Asegurarse que hay suficientes datos
            if len(data) < self.sequence_length + 1:
                logger.warning(f"Datos insuficientes para {service_id}: {len(data)} filas")
                return None, None
            
            # Seleccionar solo características numéricas
            numeric_features = data.select_dtypes(include=['number']).columns.tolist()
            
            # Excluir columnas no deseadas
            exclude_cols = ['id', 'timestamp', 'is_failure', 'service_id', 'prediction']
            numeric_features = [f for f in numeric_features if f not in exclude_cols]
            
            if not numeric_features:
                logger.warning(f"No se encontraron características numéricas para {service_id}")
                return None, None
            
            # Extraer características y etiquetas
            X = data[numeric_features].values
            
            # Para entrenamiento, necesitamos etiquetas
            if train_mode:
                if 'is_failure' not in data.columns:
                    logger.warning(f"No se encontró columna 'is_failure' para {service_id}")
                    return None, None
                y = data['is_failure'].values
            else:
                y = None
            
            # Escalar datos
            if service_id in self.scalers and not train_mode:
                scaler = self.scalers[service_id]
                X_scaled = scaler.transform(X)
            else:
                # Para entrenamiento o si no existe scaler
                scaler = StandardScaler()
                X_scaled = scaler.fit_transform(X)
                self.scalers[service_id] = scaler
                
                # Guardar scaler
                scaler_path = os.path.join(self.models_dir, f"{service_id}_scaler.joblib")
                joblib.dump(scaler, scaler_path)
            
            # Crear secuencias para LSTM
            X_sequences = []
            y_labels = []
            
            for i in range(len(X_scaled) - self.sequence_length):
                # Secuencia de características
                X_sequences.append(X_scaled[i:i + self.sequence_length])
                
                # Para entrenamiento, etiqueta es si hubo fallo después de la secuencia
                if train_mode:
                    y_labels.append(y[i + self.sequence_length])
            
            # Convertir a arrays numpy
            X_sequences = np.array(X_sequences)
            if train_mode:
                y_labels = np.array(y_labels)
            
            # Guardar las características utilizadas
            self.service_features[service_id] = numeric_features
            
            return X_sequences, y_labels
            
        except Exception as e:
            logger.error(f"Error al preparar datos de secuencia: {str(e)}")
            return None, None
    
    def train_model_for_service(self, service_id, data=None):
        """
        Entrena un modelo para un servicio específico.
        
        Args:
            service_id: ID del servicio
            data: DataFrame con datos históricos (opcional)
            
        Returns:
            Tuple: (model, metadata)
        """
        try:
            # Si no se proporcionan datos, obtenerlos de la base de datos
            if data is None and self.engine is not None:
                # Consulta para obtener datos históricos con etiquetas de fallos
                query = f"""
                    SELECT m.*, 
                           CASE WHEN f.failure_id IS NOT NULL THEN 1 ELSE 0 END as is_failure
                    FROM metrics m
                    LEFT JOIN failures f 
                      ON m.service_id = f.service_id 
                      AND f.timestamp BETWEEN m.timestamp AND m.timestamp + INTERVAL '24 hours'
                    WHERE m.service_id = '{service_id}'
                    ORDER BY m.timestamp
                """
                data = pd.read_sql(query, self.engine)
                
                if data.empty:
                    logger.warning(f"No se encontraron datos para {service_id}")
                    return None, None
                
                logger.info(f"Datos obtenidos para entrenamiento: {len(data)} filas")
            
            if data is None or data.empty:
                logger.warning(f"No hay datos disponibles para entrenar modelo de {service_id}")
                return None, None
            
            # Verificar distribución de clases
            if 'is_failure' in data.columns:
                failure_count = data['is_failure'].sum()
                total_samples = len(data)
                failure_rate = failure_count / total_samples if total_samples > 0 else 0
                
                logger.info(f"Distribución de clases para {service_id}: "
                           f"{failure_count} fallos de {total_samples} muestras ({failure_rate:.2%})")
                
                # Si hay muy pocos fallos, puede ser difícil entrenar el modelo
                if failure_count < 10:
                    logger.warning(f"Muy pocos fallos para {service_id}: {failure_count} fallos")
                    # Considerar técnicas de balanceo
            
            # Preparar datos de secuencia
            X_sequences, y_labels = self.prepare_sequence_data(data, service_id, train_mode=True)
            
            if X_sequences is None or y_labels is None:
                logger.warning(f"No se pudieron preparar secuencias para {service_id}")
                return None, None
            
            # Dividir en entrenamiento y validación
            X_train, X_val, y_train, y_val = train_test_split(
                X_sequences, y_labels, test_size=0.2, random_state=42, stratify=y_labels
            )
            
            logger.info(f"Datos de entrenamiento: {X_train.shape}, Validación: {X_val.shape}")
            
            # Obtener forma de entrada
            input_shape = (X_train.shape[1], X_train.shape[2])
            
            # Crear modelo con atención
            model = create_attention_lstm_model(
                input_shape=input_shape,
                output_shape=1,
                lstm_units=128,
                dropout_rate=0.3
            )
            
            # Callbacks para entrenamiento
            early_stopping = EarlyStopping(
                monitor='val_loss',
                patience=8,
                restore_best_weights=True
            )
            
            reduce_lr = ReduceLROnPlateau(
                monitor='val_loss',
                factor=0.5,
                patience=3,
                min_lr=0.0001
            )
            
            checkpoint = ModelCheckpoint(
                os.path.join(self.models_dir, f"{service_id}_best_model.h5"),
                monitor='val_loss',
                save_best_only=True,
                verbose=1
            )
            
            # Calcular pesos de clase para balanceo
            class_weights = None
            if len(np.unique(y_train)) > 1:
                neg_samples = np.sum(y_train == 0)
                pos_samples = np.sum(y_train == 1)
                if pos_samples > 0:
                    weight_ratio = neg_samples / pos_samples
                    class_weights = {0: 1.0, 1: weight_ratio}
                    logger.info(f"Pesos de clase para balanceo: {class_weights}")
            
            # Entrenar modelo
            history = model.fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=100,
                batch_size=32,
                callbacks=[early_stopping, reduce_lr, checkpoint],
                verbose=1,
                class_weight=class_weights
            )
            
            # Evaluar modelo
            val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
            
            # Calcular métricas avanzadas
            val_pred = model.predict(X_val).ravel()
            val_pred_binary = (val_pred >= 0.5).astype(int)
            
            f1 = f1_score(y_val, val_pred_binary)
            auc = roc_auc_score(y_val, val_pred)
            tn, fp, fn, tp = confusion_matrix(y_val, val_pred_binary).ravel()
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            
            # Extraer pesos de atención para interpretabilidad
            # Esto requiere modificar el modelo para extraer estos pesos
            attention_weights = None
            # TODO: Implementar extracción de pesos de atención
            
            # Calcular importancia de características usando permutation importance
            # Esto requiere entrenamiento adicional
            feature_importance = {}
            for i, feature in enumerate(self.service_features.get(service_id, [])):
                feature_importance[feature] = 1.0  # Placeholder, implementar cálculo real
            
            # Ordenar por importancia
            feature_importance = {k: v for k, v in sorted(feature_importance.items(), 
                                                         key=lambda item: item[1], 
                                                         reverse=True)}
            
            # Guardar modelo
            model_path = os.path.join(self.models_dir, f"{service_id}_model.h5")
            model.save(model_path)
            
            # Guardar metadatos
            metadata = {
                'trained_at': datetime.now().isoformat(),
                'metrics': {
                    'val_loss': float(val_loss),
                    'val_accuracy': float(val_acc),
                    'f1_score': float(f1),
                    'auc': float(auc),
                    'precision': float(precision),
                    'recall': float(recall),
                    'confusion_matrix': {
                        'tn': int(tn),
                        'fp': int(fp),
                        'fn': int(fn),
                        'tp': int(tp)
                    }
                },
                'features': self.service_features.get(service_id, []),
                'feature_importance': feature_importance,
                'training_history': {
                    'loss': [float(x) for x in history.history['loss']],
                    'val_loss': [float(x) for x in history.history['val_loss']],
                    'accuracy': [float(x) for x in history.history['accuracy']],
                    'val_accuracy': [float(x) for x in history.history['val_accuracy']]
                },
                'model_config': {
                    'sequence_length': self.sequence_length,
                    'prediction_threshold': self.prediction_threshold,
                    'input_shape': input_shape
                }
            }
            
            if attention_weights:
                metadata['attention_weights'] = attention_weights
            
            # Guardar metadatos
            metadata_path = os.path.join(self.models_dir, f"{service_id}_metadata.json")
            with open(metadata_path, 'w') as f:
                json.dump(metadata, f)
            
            # Actualizar modelos y metadatos en memoria
            self.models[service_id] = model
            self.model_metadata[service_id] = metadata
            
            logger.info(f"Modelo entrenado y guardado para {service_id}, "
                      f"F1-score: {f1:.3f}, AUC: {auc:.3f}")
            
            return model, metadata
            
        except Exception as e:
            logger.error(f"Error al entrenar modelo para {service_id}: {str(e)}")
            return None, None
    
    def predict_failures(self, service_id, data, horizon_hours=None):
        """
        Predice la probabilidad de fallo para un servicio.
        
        Args:
            service_id: ID del servicio
            data: Datos recientes para predicción
            horizon_hours: Horizonte de predicción en horas (lista de horas)
            
        Returns:
            dict: Resultado de la predicción
        """
        try:
            # Incrementar contador de predicciones
            self.prediction_stats['total_predictions'] += 1
            
            # Verificar si tenemos modelo para este servicio
            if service_id not in self.models:
                logger.warning(f"No hay modelo disponible para {service_id}, intentando entrenar")
                self.train_model_for_service(service_id)
                
                if service_id not in self.models:
                    logger.error(f"No se pudo entrenar modelo para {service_id}")
                    return {
                        'service_id': service_id,
                        'timestamp': datetime.now().isoformat(),
                        'prediction': False,
                        'probability': 0.0,
                        'error': 'Modelo no disponible'
                    }
            
            # Convertir a DataFrame si es un diccionario
            if isinstance(data, dict):
                data_df = pd.DataFrame([data])
            else:
                data_df = pd.DataFrame(data)
            
            # Preparar secuencias para predicción
            if len(data_df) < self.sequence_length:
                logger.warning(f"Datos insuficientes para {service_id}, se necesitan al menos {self.sequence_length} puntos")
                return {
                    'service_id': service_id,
                    'timestamp': datetime.now().isoformat(),
                    'prediction': False,
                    'probability': 0.0,
                    'error': 'Datos insuficientes'
                }
            
            # Tomar últimos N puntos para la secuencia
            recent_data = data_df.iloc[-self.sequence_length:].copy()
            
            # Preparar secuencia
            X_sequence, _ = self.prepare_sequence_data(recent_data, service_id, train_mode=False)
            
            if X_sequence is None:
                logger.warning(f"No se pudo preparar secuencia para {service_id}")
                return {
                    'service_id': service_id,
                    'timestamp': datetime.now().isoformat(),
                    'prediction': False,
                    'probability': 0.0,
                    'error': 'Error al preparar secuencia'
                }
            
            # Realizar predicción
            failure_prob = self.models[service_id].predict(X_sequence, verbose=0)[0][0]
            
            # Aplicar umbral de predicción
            prediction = failure_prob >= self.prediction_threshold
            
            # Horizonte de predicción
            if horizon_hours is None:
                horizon_hours = self.horizon_hours
            
            # Determinar qué horizonte tiene mayor probabilidad
            horizon_probs = {}
            
            # Para un modelo completo, tendríamos diferentes modelos para diferentes horizontes
            # Aquí simplificamos asumiendo mayor probabilidad para horizontes más cercanos
            for hours in horizon_hours:
                decay_factor = 1.0 - (0.1 * hours / 24)  # Decaimiento por hora
                horizon_probs[hours] = failure_prob * max(0.1, decay_factor)
            
            # Seleccionar horizonte con mayor probabilidad
            best_horizon = max(horizon_probs, key=horizon_probs.get)
            
            # Identificar métricas con mayor influencia
            # Idealmente esto usaría pesos de atención, pero usamos una aproximación
            # basada en desviaciones de valores normales y tendencias
            influential_metrics = self._identify_influential_metrics(service_id, data_df)
            
            # Registrar predicción positiva si aplica
            if prediction:
                self.prediction_stats['positive_predictions'] += 1
                
                # Guardar predicción para seguimiento
                prediction_record = {
                    'service_id': service_id,
                    'timestamp': datetime.now().isoformat(),
                    'probability': float(failure_prob),
                    'horizon_hours': best_horizon,
                    'predicted_failure_time': (datetime.now() + timedelta(hours=best_horizon)).isoformat(),
                    'influential_metrics': influential_metrics
                }
                
                self.prediction_stats['last_predictions'].append(prediction_record)
                
                # Mantener solo las últimas 100 predicciones
                if len(self.prediction_stats['last_predictions']) > 100:
                    self.prediction_stats['last_predictions'] = self.prediction_stats['last_predictions'][-100:]
                
                # Actualizar timestamp
                self.prediction_stats['last_update'] = datetime.now().isoformat()
                
                # Guardar estadísticas
                stats_path = os.path.join(self.models_dir, 'prediction_stats.json')
                with open(stats_path, 'w') as f:
                    json.dump(self.prediction_stats, f)
            
            # Preparar resultado de predicción
            result = {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction': bool(prediction),
                'probability': float(failure_prob),
                'prediction_horizon': best_horizon,
                'predicted_failure_time': (datetime.now() + timedelta(hours=best_horizon)).isoformat() if prediction else None,
                'confidence': 'high' if failure_prob > 0.85 or failure_prob < 0.15 else 'medium' if failure_prob > 0.7 or failure_prob < 0.3 else 'low',
                'influential_metrics': influential_metrics,
                'horizon_probabilities': {str(h): float(p) for h, p in horizon_probs.items()},
            }
            
            # Publicar en Kafka si es una predicción positiva y tenemos productor
            if prediction and self.kafka_producer:
                try:
                    self.kafka_producer.send('failure_predictions', result)
                    logger.info(f"Predicción de fallo publicada para {service_id} con prob={failure_prob:.3f}")
                except Exception as e:
                    logger.error(f"Error al publicar predicción en Kafka: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error al predecir fallos para {service_id}: {str(e)}")
            return {
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'prediction': False,
                'probability': 0.0,
                'error': str(e)
            }
    
    def _identify_influential_metrics(self, service_id, data_df):
        """
        Identifica las métricas más influyentes en la predicción.
        
        Args:
            service_id: ID del servicio
            data_df: DataFrame con datos recientes
            
        Returns:
            dict: Métricas influyentes y su importancia
        """
        try:
            influential_metrics = {}
            
            # Obtener características del servicio
            if service_id not in self.service_features:
                return influential_metrics
            
            features = self.service_features[service_id]
            
            # Obtener scaler para normalización
            if service_id not in self.scalers:
                return influential_metrics
            
            scaler = self.scalers[service_id]
            
            # Seleccionar solo las características numéricas disponibles
            available_features = [f for f in features if f in data_df.columns and pd.api.types.is_numeric_dtype(data_df[f])]
            
            if not available_features:
                return influential_metrics
            
            # Calcular estadísticas para cada característica
            for feature in available_features:
                if feature not in data_df.columns:
                    continue
                
                # Obtener valores recientes
                recent_values = data_df[feature].values
                
                if len(recent_values) < 2:
                    continue
                
                # Calcular tendencia
                trend = (recent_values[-1] - recent_values[0]) / max(1e-5, abs(recent_values[0]))
                
                # Escalar último valor para comparar con distribución normal
                feature_idx = list(data_df.columns).index(feature)
                last_value = recent_values[-1]
                
                # Calcular z-score aproximado usando parámetros del scaler
                if hasattr(scaler, 'mean_') and feature_idx < len(scaler.mean_):
                    mean = scaler.mean_[feature_idx]
                    std = scaler.scale_[feature_idx]
                    if std > 0:
                        z_score = abs((last_value - mean) / std)
                    else:
                        z_score = 0
                else:
                    # Cálculo alternativo
                    mean = np.mean(recent_values)
                    std = np.std(recent_values) + 1e-5
                    z_score = abs((last_value - mean) / std)
                
                # Calcular score de influencia combinando tendencia y desviación
                influence_score = (0.7 * z_score) + (0.3 * abs(trend))
                
                # Añadir si tiene influencia significativa
                if influence_score > 1.0:
                    influential_metrics[feature] = {
                        'score': float(influence_score),
                        'trend': float(trend),
                        'z_score': float(z_score),
                        'current_value': float(last_value),
                        'direction': 'increasing' if trend > 0 else 'decreasing'
                    }
            
            # Ordenar por puntuación
            return {k: v for k, v in sorted(influential_metrics.items(), 
                                           key=lambda item: item[1]['score'], 
                                           reverse=True)}
            
        except Exception as e:
            logger.error(f"Error al identificar métricas influyentes: {str(e)}")
            return {}
    
    def evaluate_model_performance(self, service_id, test_data=None):
        """
        Evalúa el rendimiento del modelo en datos de prueba.
        
        Args:
            service_id: ID del servicio
            test_data: Datos de prueba (opcional)
            
        Returns:
            dict: Métricas de rendimiento
        """
        try:
            # Verificar si tenemos modelo para este servicio
            if service_id not in self.models:
                logger.warning(f"No hay modelo disponible para {service_id}")
                return {'error': 'Modelo no disponible'}
            
            # Si no se proporcionan datos, obtenerlos de la base de datos
            if test_data is None and self.engine is not None:
                # Consulta para obtener datos de prueba recientes
                query = f"""
                    SELECT m.*, 
                           CASE WHEN f.failure_id IS NOT NULL THEN 1 ELSE 0 END as is_failure
                    FROM metrics m
                    LEFT JOIN failures f 
                      ON m.service_id = f.service_id 
                      AND f.timestamp BETWEEN m.timestamp AND m.timestamp + INTERVAL '24 hours'
                    WHERE m.service_id = '{service_id}'
                    AND m.timestamp > (SELECT MAX(timestamp) FROM metrics WHERE service_id = '{service_id}') - INTERVAL '30 days'
                    ORDER BY m.timestamp
                """
                test_data = pd.read_sql(query, self.engine)
                
                if test_data.empty:
                    logger.warning(f"No se encontraron datos de prueba para {service_id}")
                    return {'error': 'Datos de prueba no disponibles'}
            
            if test_data is None or test_data.empty:
                logger.warning(f"No hay datos disponibles para evaluar modelo de {service_id}")
                return {'error': 'Datos de prueba no disponibles'}
            
            # Verificar si hay etiquetas
            if 'is_failure' not in test_data.columns:
                logger.warning(f"No hay etiquetas de fallo en los datos de prueba para {service_id}")
                return {'error': 'No hay etiquetas de fallo en los datos'}
            
            # Preparar secuencias para evaluación
            X_test, y_test = self.prepare_sequence_data(test_data, service_id, train_mode=False)
            
            if X_test is None or y_test is None or len(X_test) == 0 or len(y_test) == 0:
                logger.warning(f"No se pudieron preparar secuencias para evaluación de {service_id}")
                return {'error': 'Error al preparar secuencias'}
            
            # Evaluar modelo
            test_loss, test_acc = self.models[service_id].evaluate(X_test, y_test, verbose=0)
            
            # Calcular métricas avanzadas
            y_pred = self.models[service_id].predict(X_test).ravel()
            y_pred_binary = (y_pred >= self.prediction_threshold).astype(int)
            
            f1 = f1_score(y_test, y_pred_binary)
            auc = roc_auc_score(y_test, y_pred)
            tn, fp, fn, tp = confusion_matrix(y_test, y_pred_binary).ravel()
            
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            
            # Calcular curva precision-recall
            precisions, recalls, thresholds = precision_recall_curve(y_test, y_pred)
            
            # Gráfico de curva ROC (solo para diagnósticos)
            # plt.figure(figsize=(8, 6))
            # plt.plot(recalls, precisions, 'b-', label=f'AUC = {auc:.3f}')
            # plt.xlabel('Recall')
            # plt.ylabel('Precision')
            # plt.title(f'Precision-Recall Curve - {service_id}')
            # plt.legend(loc='lower left')
            # plt.grid()
            # plt.savefig(os.path.join(self.models_dir, f"{service_id}_pr_curve.png"))
            # plt.close()
            
            # Preparar resultados
            results = {
                'service_id': service_id,
                'evaluation_time': datetime.now().isoformat(),
                'metrics': {
                    'test_loss': float(test_loss),
                    'test_accuracy': float(test_acc),
                    'f1_score': float(f1),
                    'auc': float(auc),
                    'precision': float(precision),
                    'recall': float(recall),
                    'confusion_matrix': {
                        'tn': int(tn),
                        'fp': int(fp),
                        'fn': int(fn),
                        'tp': int(tp)
                    }
                },
                'prediction_threshold': self.prediction_threshold,
                'sample_count': len(y_test),
                'failure_rate': float(np.mean(y_test))
            }
            
            # Actualizar metadatos del modelo
            if service_id in self.model_metadata:
                self.model_metadata[service_id]['last_evaluation'] = results
                
                # Guardar metadatos actualizados
                metadata_path = os.path.join(self.models_dir, f"{service_id}_metadata.json")
                with open(metadata_path, 'w') as f:
                    json.dump(self.model_metadata[service_id], f)
            
            logger.info(f"Evaluación de modelo para {service_id}: F1={f1:.3f}, AUC={auc:.3f}")
            
            return results
            
        except Exception as e:
            logger.error(f"Error al evaluar modelo para {service_id}: {str(e)}")
            return {'error': str(e)}
    
    def check_drift_and_retrain(self, service_id, current_data):
        """
        Verifica deriva de modelo y lo reentrenar si es necesario.
        
        Args:
            service_id: ID del servicio
            current_data: Datos actuales para verificar deriva
            
        Returns:
            bool: True si el modelo fue reentrenado
        """
        try:
            # Verificar si tenemos modelo y metadatos
            if service_id not in self.models or service_id not in self.model_metadata:
                logger.warning(f"No hay modelo o metadatos para {service_id}")
                return False
            
            # Obtener fecha de último entrenamiento
            last_trained = self.model_metadata[service_id].get('trained_at')
            if not last_trained:
                logger.warning(f"No hay fecha de entrenamiento para {service_id}")
                return False
            
            # Convertir a datetime
            try:
                last_trained_dt = datetime.fromisoformat(last_trained.replace('Z', '+00:00'))
            except:
                last_trained_dt = datetime.now() - timedelta(days=30)  # Valor por defecto
            
            # Calcular tiempo desde último entrenamiento
            hours_since_trained = (datetime.now() - last_trained_dt).total_seconds() / 3600
            
            # Verificar si es tiempo de reentrenar
            if hours_since_trained >= self.retrain_interval:
                logger.info(f"Reentrenando modelo para {service_id} "
                          f"(último entrenamiento hace {hours_since_trained:.1f} horas)")
                
                # Reentrenar modelo
                new_model, new_metadata = self.train_model_for_service(service_id)
                
                if new_model and new_metadata:
                    logger.info(f"Modelo reentrenado exitosamente para {service_id}")
                    return True
            
            # También podemos verificar drift usando métricas de evaluación recientes
            # Esto requeriría datos etiquetados recientes
            
            return False
            
        except Exception as e:
            logger.error(f"Error al verificar deriva para {service_id}: {str(e)}")
            return False
    
    def process_and_predict(self, data):
        """
        Procesa datos y predice fallos.
        
        Args:
            data: Datos a procesar para predicción
            
        Returns:
            dict: Resultado de la predicción
        """
        try:
            start_time = time.time()
            
            # Extraer service_id
            service_id = data.get('service_id', 'unknown_service')
            
            # Verificar si tenemos suficientes datos históricos
            # En un sistema real, obtendríamos datos históricos de la base de datos
            # Aquí asumimos que data ya contiene suficientes datos históricos
            
            # Predecir fallos
            prediction_result = self.predict_failures(service_id, data)
            
            # Calcular tiempo de procesamiento
            processing_time = time.time() - start_time
            prediction_result['processing_time_ms'] = processing_time * 1000
            
            # Verificar si es tiempo de reentrenar
            if service_id in self.models and service_id in self.model_metadata:
                self.check_drift_and_retrain(service_id, data)
            
            return prediction_result
            
        except Exception as e:
            logger.error(f"Error en process_and_predict: {str(e)}")
            return {
                'error': str(e),
                'service_id': data.get('service_id', 'unknown_service'),
                'timestamp': datetime.now().isoformat(),
                'prediction': False
            }

# Función principal de ejemplo
def main():
    """Función principal para pruebas locales"""
    # Configuración de ejemplo
    config = {
        'models_dir': './models/predictive',
        'sequence_length': 12,
        'prediction_threshold': 0.7,
        'horizon_hours': [1, 6, 24]
    }
    
    # Crear motor predictivo
    engine = PredictiveEngine(config=config)
    
    # Datos de ejemplo
    # En un caso real, tendríamos una serie de datos históricos
    example_data = []
    for i in range(15):  # 15 puntos de tiempo
        example_data.append({
            'service_id': 'web_service',
            'cpu_usage': 60 + i * 2,  # Incremento gradual
            'memory_usage': 50 + i * 1.5,
            'disk_usage_percent': 65 + i * 0.3,
            'response_time_ms': 120 + i * 10,
            'error_rate': 0.5 + i * 0.2,
            'active_connections': 100 + i * 5
        })
    
    # Convertir a DataFrame
    example_df = pd.DataFrame(example_data)
    
    # Para entrenamiento, necesitaríamos etiquetas (simuladas aquí)
    example_df['is_failure'] = 0
    example_df.loc[14, 'is_failure'] = 1  # Fallo en el último punto
    
    # Entrenar modelo
    model, metadata = engine.train_model_for_service('web_service', example_df)
    
    if model:
        print("Modelo entrenado exitosamente")
        
        # Realizar predicción
        prediction = engine.predict_failures('web_service', example_data)
        
        # Mostrar resultado
        print("\nPredicción:")
        for key, value in prediction.items():
            print(f"  {key}: {value}")
    else:
        print("Error al entrenar modelo")

if __name__ == "__main__":
    main()