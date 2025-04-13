import os
import json
import logging
import numpy as np
import pandas as pd
import tensorflow as tf
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import joblib
import time
from tensorflow.keras.models import load_model
from threading import Thread

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('anomaly_detector')

class AnomalyDetector:
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
            'preprocessed_metrics',
            bootstrap_servers=self.kafka_servers,
            auto_offset_reset='latest',
            value_deserializer=lambda x: json.loads(x.decode('utf-8'))
        )
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Cargar modelos
        self.models = self.load_models()
        self.scaler = self.load_scaler()
        
        # Parámetros del detector
        self.batch_size = 100
        self.metrics_buffer = []
        self.anomaly_threshold = 0.85  # Umbral para considerar anomalía
        
        logger.info("Detector de anomalías inicializado correctamente")

    def load_models(self):
        """Carga los modelos de detección de anomalías"""
        models = {}
        
        # Comprobar y cargar el modelo de Isolation Forest si existe
        if_model_path = "/app/models/isolation_forest.joblib"
        if os.path.exists(if_model_path):
            models['isolation_forest'] = joblib.load(if_model_path)
            logger.info("Modelo de Isolation Forest cargado")
        else:
            # Crear y entrenar un modelo básico de Isolation Forest si no existe
            logger.info("Creando modelo de Isolation Forest")
            models['isolation_forest'] = self.train_isolation_forest()
        
        # Comprobar y cargar el modelo de Autoencoder si existe
        autoencoder_path = "/app/models/autoencoder.h5"
        if os.path.exists(autoencoder_path):
            models['autoencoder'] = load_model(autoencoder_path)
            logger.info("Modelo de Autoencoder cargado")
        else:
            logger.warning("Modelo de Autoencoder no encontrado")
        
        return models

    def load_scaler(self):
        """Carga el scaler para normalizar los datos"""
        scaler_path = "/app/models/scaler.joblib"
        if os.path.exists(scaler_path):
            return joblib.load(scaler_path)
        else:
            logger.info("Creando nuevo scaler")
            return StandardScaler()
    
    def train_isolation_forest(self):
        """Entrena un modelo básico de Isolation Forest con datos históricos"""
        try:
            # Obtener datos históricos de la última semana para el entrenamiento
            query = """
                SELECT * FROM metrics 
                WHERE timestamp > NOW() - INTERVAL '7 days'
                ORDER BY timestamp DESC
                LIMIT 10000
            """
            df = pd.read_sql(query, self.engine)
            
            if df.empty:
                logger.warning("No hay datos históricos para entrenar. Creando modelo con parámetros por defecto.")
                model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
                # Guardar el modelo
                joblib.dump(model, "/app/models/isolation_forest.joblib")
                return model
            
            # Preprocesar datos
            numeric_features = df.select_dtypes(include=['float64', 'int64']).columns
            X = df[numeric_features].fillna(0)
            
            # Entrenar el scaler y transformar los datos
            X_scaled = self.scaler.fit_transform(X)
            
            # Entrenar el modelo
            model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
            model.fit(X_scaled)
            
            # Guardar el modelo y el scaler
            joblib.dump(model, "/app/models/isolation_forest.joblib")
            joblib.dump(self.scaler, "/app/models/scaler.joblib")
            
            logger.info("Modelo de Isolation Forest entrenado y guardado")
            return model
            
        except Exception as e:
            logger.error(f"Error al entrenar el modelo: {str(e)}")
            # Crear un modelo por defecto
            model = IsolationForest(n_estimators=100, contamination=0.01, random_state=42)
            return model

    def preprocess_data(self, data):
        """Preprocesa los datos para la detección de anomalías"""
        # Convertir los datos a un formato adecuado para los modelos
        try:
            # Extraer y normalizar características numéricas
            features = {}
            for key, value in data.items():
                if isinstance(value, (int, float)) and key != 'timestamp':
                    features[key] = value
            
            # Convertir a DataFrame
            df = pd.DataFrame([features])
            
            # Asegurarse de que todas las columnas esperadas estén presentes
            expected_columns = self.scaler.feature_names_in_
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = 0
            
            # Seleccionar solo las columnas esperadas y en el mismo orden
            df = df[expected_columns]
            
            # Aplicar el scaler
            scaled_data = self.scaler.transform(df)
            
            return scaled_data, df
        
        except Exception as e:
            logger.error(f"Error al preprocesar datos: {str(e)}")
            return None, None

    def detect_anomalies(self, data):
        """Detecta anomalías en los datos utilizando múltiples modelos"""
        try:
            scaled_data, original_df = self.preprocess_data(data)
            if scaled_data is None:
                return False, 0, {}
            
            results = {}
            anomaly_scores = []
            
            # Detección con Isolation Forest
            if 'isolation_forest' in self.models:
                # -1 para anomalías, 1 para observaciones normales
                if_score = self.models['isolation_forest'].decision_function(scaled_data)[0]
                # Normalizar a un score entre 0 y 1 (más cercano a 1 = más anómalo)
                if_score_normalized = 1 - ((if_score + 1) / 2)
                anomaly_scores.append(if_score_normalized)
                results['isolation_forest'] = if_score_normalized
            
            # Detección con Autoencoder
            if 'autoencoder' in self.models:
                # Predicción del autoencoder
                reconstruction = self.models['autoencoder'].predict(scaled_data, verbose=0)
                # Error de reconstrucción (MSE)
                mse = np.mean(np.power(scaled_data - reconstruction, 2), axis=1)[0]
                # Normalizar el error (asumiendo que valores de MSE > 0.1 son anómalos)
                ae_score = min(mse / 0.1, 1.0)
                anomaly_scores.append(ae_score)
                results['autoencoder'] = ae_score
            
            # Calcular score final (promedio)
            if anomaly_scores:
                final_score = sum(anomaly_scores) / len(anomaly_scores)
            else:
                final_score = 0
            
            # Determinar si es anomalía
            is_anomaly = final_score >= self.anomaly_threshold
            
            # Obtener detalles adicionales si es una anomalía
            details = {}
            if is_anomaly:
                # Identificar qué métricas contribuyeron a la anomalía
                if 'autoencoder' in self.models and len(anomaly_scores) > 1:
                    # Si usamos autoencoder, podemos comparar el error por característica
                    feature_errors = np.power(scaled_data - reconstruction, 2)[0]
                    feature_contributions = dict(zip(original_df.columns, feature_errors))
                    # Ordenar por error y tomar las top 3
                    sorted_contributions = sorted(feature_contributions.items(), 
                                                key=lambda x: x[1], reverse=True)[:3]
                    for feature, error in sorted_contributions:
                        details[feature] = {'error': float(error), 'value': float(original_df[feature].iloc[0])}
                else:
                    # Sin autoencoder, simplemente indicamos las métricas con valores extremos
                    for col in original_df.columns:
                        val = original_df[col].iloc[0]
                        # Usar Z-score para identificar valores extremos
                        z_score = abs((val - self.scaler.mean_[list(original_df.columns).index(col)]) / 
                                      self.scaler.scale_[list(original_df.columns).index(col)])
                        if z_score > 3:  # Más de 3 desviaciones estándar
                            details[col] = {'z_score': float(z_score), 'value': float(val)}
            
            return is_anomaly, final_score, details
        
        except Exception as e:
            logger.error(f"Error al detectar anomalías: {str(e)}")
            return False, 0, {}

    def process_message(self, message):
        """Procesa un mensaje de Kafka y detecta anomalías"""
        try:
            # Extraer datos del mensaje
            data = message.value
            
            # Detectar anomalías
            is_anomaly, anomaly_score, details = self.detect_anomalies(data)
            
            # Añadir información de anomalía al mensaje
            data['anomaly'] = is_anomaly
            data['anomaly_score'] = anomaly_score
            data['anomaly_details'] = details
            data['anomaly_timestamp'] = datetime.now().isoformat()
            
            # Enviar a tópico de anomalías si es necesario
            if is_anomaly:
                self.producer.send('anomalies', data)
                logger.info(f"Anomalía detectada: {anomaly_score:.4f}")
            
            # Siempre enviar al tópico de métricas procesadas
            self.producer.send('processed_metrics', data)
            
            # Almacenar la anomalía en la base de datos
            if is_anomaly:
                self.store_anomaly(data)
            
            return is_anomaly
                
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {str(e)}")
            return False

    def store_anomaly(self, data):
        """Almacena la anomalía en la base de datos"""
        try:
            # Crear DataFrame para la inserción
            anomaly_df = pd.DataFrame([{
                'timestamp': datetime.now(),
                'service_id': data.get('service_id', 'unknown'),
                'node_id': data.get('node_id', 'unknown'),
                'anomaly_score': data['anomaly_score'],
                'anomaly_details': json.dumps(data['anomaly_details']),
                'metric_data': json.dumps(data)
            }])
            
            # Insertar en la tabla de anomalías
            anomaly_df.to_sql('anomalies', self.engine, if_exists='append', index=False)
            
        except Exception as e:
            logger.error(f"Error al almacenar anomalía: {str(e)}")

    def retrain_models_periodically(self):
        """Función para reentrenar los modelos periódicamente"""
        while True:
            try:
                # Reentrenar cada 24 horas
                time.sleep(86400)  # 24 horas en segundos
                logger.info("Iniciando reentrenamiento de modelos...")
                
                # Reentrenar Isolation Forest
                self.models['isolation_forest'] = self.train_isolation_forest()
                
                logger.info("Reentrenamiento de modelos completado")
                
            except Exception as e:
                logger.error(f"Error en reentrenamiento de modelos: {str(e)}")
                time.sleep(3600)  # Esperar 1 hora antes de reintentar

    def run(self):
        """Ejecuta el detector de anomalías"""
        # Iniciar hilo para reentrenamiento periódico
        retraining_thread = Thread(target=self.retrain_models_periodically, daemon=True)
        retraining_thread.start()
        
        logger.info("Detector de anomalías iniciado, esperando mensajes...")
        
        try:
            # Consumir mensajes de Kafka
            for message in self.consumer:
                self.process_message(message)
                
        except KeyboardInterrupt:
            logger.info("Detector de anomalías detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el detector de anomalías: {str(e)}")
        finally:
            # Cerrar conexiones
            self.consumer.close()
            self.producer.close()


if __name__ == "__main__":
    # Esperar a que Kafka esté disponible
    time.sleep(10)
    
    # Iniciar el detector de anomalías
    detector = AnomalyDetector()
    detector.run()