import os
import json
import logging
import numpy as np
import pandas as pd
import tensorflow as tf
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine
from datetime import datetime, timedelta
import time
from threading import Thread
from tensorflow.keras.models import load_model, Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout, Input
from tensorflow.keras.callbacks import EarlyStopping
from sklearn.preprocessing import MinMaxScaler
import joblib
import pickle

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('predictive_engine')

class PredictiveEngine:
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
        
        # Configurar consumidor Kafka
        self.consumer = KafkaConsumer(
            'processed_metrics',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8')),
            group_id='predictive_engine_group'
        )
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Cargar modelos y escaladores
        self.models = {}
        self.scalers = {}
        self.service_data = {}
        self.sequence_length = 20  # Longitud de secuencia para modelos LSTM
        self.prediction_horizon = 5  # Horizonte de predicción (en intervalos de tiempo)
        self.failure_threshold = 0.7  # Umbral para considerar predicción de fallo
        
        # Cargar o crear modelos por servicio
        self.load_models()
        
        logger.info("Motor predictivo inicializado correctamente")

    def load_models(self):
        """Carga los modelos predictivos existentes o crea nuevos si no existen"""
        # Directorio para modelos
        models_dir = "/app/models/predictive"
        os.makedirs(models_dir, exist_ok=True)
        
        try:
            # Cargar registro de modelos si existe
            model_registry_path = os.path.join(models_dir, "model_registry.json")
            if os.path.exists(model_registry_path):
                with open(model_registry_path, 'r') as f:
                    model_registry = json.load(f)
                
                # Cargar cada modelo registrado
                for service_id, model_info in model_registry.items():
                    model_path = model_info.get('model_path')
                    scaler_path = model_info.get('scaler_path')
                    feature_list = model_info.get('features', [])
                    
                    if os.path.exists(model_path) and os.path.exists(scaler_path):
                        self.models[service_id] = load_model(model_path)
                        self.scalers[service_id] = joblib.load(scaler_path)
                        self.service_data[service_id] = {
                            'features': feature_list,
                            'data_buffer': []
                        }
                        logger.info(f"Modelo cargado para servicio: {service_id}")
            else:
                logger.info("No se encontró registro de modelos, se crearán dinámicamente")
        except Exception as e:
            logger.error(f"Error al cargar modelos: {str(e)}")
    
    def create_lstm_model(self, input_shape, output_shape=1):
        """Crea un modelo LSTM para predicción de series temporales"""
        model = Sequential([
            Input(shape=input_shape),
            LSTM(128, return_sequences=True),
            Dropout(0.2),
            LSTM(64),
            Dropout(0.2),
            Dense(32, activation='relu'),
            Dense(output_shape, activation='sigmoid')
        ])
        
        model.compile(
            optimizer='adam',
            loss='binary_crossentropy' if output_shape == 1 else 'categorical_crossentropy',
            metrics=['accuracy']
        )
        
        return model

    def train_model_for_service(self, service_id):
        """Entrena un modelo para un servicio específico usando datos históricos"""
        try:
            # Obtener datos históricos del servicio
            query = f"""
                SELECT * FROM metrics 
                WHERE service_id = '{service_id}' 
                AND timestamp > NOW() - INTERVAL '30 days'
                ORDER BY timestamp ASC
            """
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                logger.warning(f"No hay suficientes datos para entrenar modelo para servicio {service_id}")
                return None, None
            
            # Obtener datos de fallos históricos
            failure_query = f"""
                SELECT * FROM failures 
                WHERE service_id = '{service_id}' 
                AND timestamp > NOW() - INTERVAL '30 days'
            """
            failures_df = pd.read_sql(failure_query, self.engine)
            
            # Si no hay fallos registrados, no podemos entrenar el modelo predictivo
            if failures_df.empty:
                logger.warning(f"No hay fallos registrados para servicio {service_id}, no se puede entrenar modelo")
                return None, None
            
            # Preprocesar datos
            # Seleccionar características numéricas
            numeric_features = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
            if 'timestamp' in numeric_features:
                numeric_features.remove('timestamp')
            
            feature_df = df[numeric_features].fillna(0)
            
            # Crear etiquetas: 1 si hubo fallo en las próximas N horas, 0 si no
            prediction_window = timedelta(hours=1)  # Ventana de predicción (ej: 1 hora)
            labels = []
            
            for idx, row in df.iterrows():
                current_time = row['timestamp']
                # Verificar si hay fallos en la ventana de predicción
                future_failures = failures_df[
                    (failures_df['timestamp'] > current_time) & 
                    (failures_df['timestamp'] <= current_time + prediction_window)
                ]
                labels.append(1 if not future_failures.empty else 0)
            
            # Normalizar características
            scaler = MinMaxScaler()
            scaled_features = scaler.fit_transform(feature_df)
            
            # Crear secuencias para LSTM
            X, y = [], []
            for i in range(len(scaled_features) - self.sequence_length):
                X.append(scaled_features[i:i + self.sequence_length])
                y.append(labels[i + self.sequence_length])
            
            X = np.array(X)
            y = np.array(y)
            
            # Si hay muy pocos ejemplos positivos, no entrenar
            if sum(y) < 5:
                logger.warning(f"Insuficientes ejemplos de fallos para servicio {service_id}")
                return None, None
            
            # Dividir en entrenamiento y validación
            train_size = int(len(X) * 0.8)
            X_train, X_val = X[:train_size], X[train_size:]
            y_train, y_val = y[:train_size], y[train_size:]
            
            # Crear y entrenar modelo
            model = self.create_lstm_model(input_shape=(self.sequence_length, len(numeric_features)))
            
            early_stopping = EarlyStopping(
                monitor='val_loss',
                patience=5,
                restore_best_weights=True
            )
            
            model.fit(
                X_train, y_train,
                validation_data=(X_val, y_val),
                epochs=50,
                batch_size=32,
                callbacks=[early_stopping],
                verbose=1
            )
            
            # Guardar modelo y scaler
            models_dir = "/app/models/predictive"
            model_path = os.path.join(models_dir, f"{service_id}_model.h5")
            scaler_path = os.path.join(models_dir, f"{service_id}_scaler.joblib")
            
            model.save(model_path)
            joblib.dump(scaler, scaler_path)
            
            # Actualizar registro de modelos
            model_registry_path = os.path.join(models_dir, "model_registry.json")
            model_registry = {}
            
            if os.path.exists(model_registry_path):
                with open(model_registry_path, 'r') as f:
                    model_registry = json.load(f)
            
            model_registry[service_id] = {
                'model_path': model_path,
                'scaler_path': scaler_path,
                'features': numeric_features,
                'created_at': datetime.now().isoformat()
            }
            
            with open(model_registry_path, 'w') as f:
                json.dump(model_registry, f)
            
            logger.info(f"Modelo entrenado y guardado para servicio {service_id}")
            
            return model, scaler, numeric_features
            
        except Exception as e:
            logger.error(f"Error al entrenar modelo para servicio {service_id}: {str(e)}")
            return None, None

    def predict_failures(self, service_id, data_buffer):
        """Predice fallos futuros para un servicio específico"""
        try:
            # Verificar si tenemos suficientes datos en el buffer
            if len(data_buffer) < self.sequence_length:
                return None, 0.0
            
            # Verificar si tenemos modelo para este servicio
            if service_id not in self.models:
                model, scaler, features = self.train_model_for_service(service_id)
                if model is None:
                    return None, 0.0
                
                self.models[service_id] = model
                self.scalers[service_id] = scaler
                self.service_data[service_id] = {
                    'features': features,
                    'data_buffer': data_buffer[-self.sequence_length:]
                }
            
            # Obtener las características relevantes
            features = self.service_data[service_id]['features']
            
            # Extraer las características del buffer de datos
            feature_data = []
            for item in data_buffer[-self.sequence_length:]:
                features_dict = {}
                for feature in features:
                    if feature in item:
                        features_dict[feature] = item[feature]
                    else:
                        features_dict[feature] = 0  # Valor por defecto si falta
                
                feature_values = [features_dict[f] for f in features]
                feature_data.append(feature_values)
            
            # Normalizar datos
            scaler = self.scalers[service_id]
            feature_data_array = np.array(feature_data)
            scaled_data = scaler.transform(feature_data_array)
            
            # Preparar input para el modelo (añadir dimensión de batch)
            model_input = np.expand_dims(scaled_data, axis=0)
            
            # Realizar predicción
            model = self.models[service_id]
            failure_probability = model.predict(model_input, verbose=0)[0][0]
            
            # Si la probabilidad supera el umbral, predecir fallo
            predicted_failure = failure_probability >= self.failure_threshold
            
            return predicted_failure, float(failure_probability)
            
        except Exception as e:
            logger.error(f"Error al predecir fallos para servicio {service_id}: {str(e)}")
            return None, 0.0

    def process_message(self, message):
        """Procesa un mensaje con métricas y realiza predicciones"""
        try:
            data = message.value
            service_id = data.get('service_id', 'unknown')
            
            # Inicializar buffer de datos para este servicio si no existe
            if service_id not in self.service_data:
                self.service_data[service_id] = {
                    'features': [],
                    'data_buffer': []
                }
            
            # Añadir datos al buffer
            self.service_data[service_id]['data_buffer'].append(data)
            
            # Mantener solo los últimos N elementos en el buffer
            buffer_size = max(100, self.sequence_length * 2)
            if len(self.service_data[service_id]['data_buffer']) > buffer_size:
                self.service_data[service_id]['data_buffer'] = self.service_data[service_id]['data_buffer'][-buffer_size:]
            
            # Realizar predicción si tenemos suficientes datos
            if len(self.service_data[service_id]['data_buffer']) >= self.sequence_length:
                predicted_failure, probability = self.predict_failures(
                    service_id, 
                    self.service_data[service_id]['data_buffer']
                )
                
                # Si se predijo un fallo, enviar alerta
                if predicted_failure:
                    prediction_data = {
                        'timestamp': datetime.now().isoformat(),
                        'service_id': service_id,
                        'node_id': data.get('node_id', 'unknown'),
                        'predicted_failure': True,
                        'failure_probability': probability,
                        'prediction_horizon': self.prediction_horizon,
                        'original_data': data
                    }
                    
                    # Enviar a tópico de predicciones
                    self.producer.send('failure_predictions', prediction_data)
                    
                    # Almacenar la predicción
                    self.store_prediction(prediction_data)
                    
                    logger.info(f"Fallo predicho para servicio {service_id} con probabilidad {probability:.4f}")
                    
                    return True
            
            return False
                
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {str(e)}")
            return False

    def store_prediction(self, prediction_data):
        """Almacena la predicción en la base de datos"""
        try:
            # Preparar datos para la base de datos
            prediction_df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'service_id': prediction_data['service_id'],
                'node_id': prediction_data['node_id'],
                'failure_probability': prediction_data['failure_probability'],
                'prediction_horizon': prediction_data['prediction_horizon'],
                'prediction_data': json.dumps(prediction_data)
            }])
            
            # Insertar en la tabla de predicciones
            prediction_df.to_sql('failure_predictions', self.engine, if_exists='append', index=False)
            
        except Exception as e:
            logger.error(f"Error al almacenar predicción: {str(e)}")

    def retrain_models_periodically(self):
        """Función para reentrenar los modelos periódicamente"""
        while True:
            try:
                # Reentrenar cada 48 horas
                time.sleep(172800)  # 48 horas en segundos
                logger.info("Iniciando reentrenamiento de modelos predictivos...")
                
                # Reentrenar cada modelo existente
                for service_id in list(self.models.keys()):
                    logger.info(f"Reentrenando modelo para servicio: {service_id}")
                    model, scaler, features = self.train_model_for_service(service_id)
                    if model is not None:
                        self.models[service_id] = model
                        self.scalers[service_id] = scaler
                        self.service_data[service_id]['features'] = features
                
                logger.info("Reentrenamiento de modelos predictivos completado")
                
            except Exception as e:
                logger.error(f"Error en reentrenamiento de modelos: {str(e)}")
                time.sleep(3600)  # Esperar 1 hora antes de reintentar

    def run(self):
        """Ejecuta el motor predictivo"""
        # Iniciar hilo para reentrenamiento periódico
        retraining_thread = Thread(target=self.retrain_models_periodically, daemon=True)
        retraining_thread.start()
        
        logger.info("Motor predictivo iniciado, esperando mensajes...")
        
        try:
            # Consumir mensajes de Kafka
            for message in self.consumer:
                self.process_message(message)
                
        except KeyboardInterrupt:
            logger.info("Motor predictivo detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el motor predictivo: {str(e)}")
        finally:
            # Cerrar conexiones
            self.consumer.close()
            self.producer.close()


if __name__ == "__main__":
    # Esperar a que Kafka esté disponible
    time.sleep(15)
    
    # Iniciar el motor predictivo
    engine = PredictiveEngine()
    engine.run()