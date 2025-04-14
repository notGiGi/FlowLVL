# system_diagnostic/diagnostic_service.py

import pandas as pd
import numpy as np
import logging
import json
import time
import threading
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from kafka import KafkaProducer
import psutil
import requests
import os

logger = logging.getLogger('system_diagnostic')

class SystemDiagnostic:
    def __init__(self, db_engine, kafka_producer, config=None):
        """
        Servicio de diagnóstico del sistema
        
        Args:
            db_engine: Conexión a la base de datos
            kafka_producer: Productor Kafka
            config: Configuración del servicio
        """
        self.engine = db_engine
        self.producer = kafka_producer
        
        # Configuración por defecto
        self.default_config = {
            'diagnostic_interval': 3600,  # 1 hora
            'components': ['preprocessor', 'anomaly_detector', 'predictive_engine', 'action_recommender', 'api'],
            'metrics_to_monitor': ['processing_latency', 'data_quality', 'model_drift', 'resource_usage'],
            'alert_thresholds': {
                'processing_latency': 30.0,  # segundos
                'data_quality': 0.7,  # score mínimo
                'model_performance': 0.7,  # score mínimo
                'cpu_usage': 85.0,  # porcentaje
                'memory_usage': 85.0,  # porcentaje
                'disk_usage': 85.0,  # porcentaje
            }
        }
        
        # Usar configuración proporcionada o default
        self.config = config if config else self.default_config
        
        # Estado actual del sistema
        self.system_status = {
            'overall_health': 'healthy',
            'components_status': {},
            'last_update': datetime.now().isoformat()
        }
        
        logger.info("Servicio de diagnóstico inicializado")
    
    def run(self):
        """Ejecuta el servicio de diagnóstico en un hilo separado"""
        diagnostic_thread = threading.Thread(target=self.run_diagnostics_loop, daemon=True)
        diagnostic_thread.start()
        logger.info("Hilo de diagnóstico iniciado")
    
    def run_diagnostics_loop(self):
        """Ejecuta diagnósticos periódicamente"""
        while True:
            try:
                # Ejecutar diagnóstico completo
                diagnostic_result = self.perform_full_diagnostic()
                
                # Actualizar estado del sistema
                self.update_system_status(diagnostic_result)
                
                # Publicar resultados
                self.publish_diagnostic_results(diagnostic_result)
                
                # Almacenar en base de datos
                self.store_diagnostic_results(diagnostic_result)
                
                # Verificar si hay problemas críticos
                if diagnostic_result['overall_health'] == 'critical':
                    self.handle_critical_issues(diagnostic_result)
                
            except Exception as e:
                logger.error(f"Error en diagnóstico del sistema: {str(e)}")
            
            # Esperar hasta el próximo diagnóstico
            time.sleep(self.config['diagnostic_interval'])
    
    def perform_full_diagnostic(self):
        """Realiza un diagnóstico completo del sistema"""
        diagnostic_result = {
            'timestamp': datetime.now().isoformat(),
            'processing_latency': self.check_processing_latency(),
            'component_health': self.check_component_health(),
            'data_quality': self.check_data_quality(),
            'model_performance': self.check_model_performance(),
            'resource_usage': self.check_resource_usage(),
            'database_health': self.check_database_health(),
            'kafka_health': self.check_kafka_health()
        }
        
        # Calcular salud general
        diagnostic_result['overall_health'] = self.calculate_overall_health(diagnostic_result)
        
        return diagnostic_result
    
    def check_processing_latency(self):
        """Verifica la latencia de procesamiento end-to-end"""
        try:
            # Medir latencia en diferentes etapas del pipeline
            latencies = {}
            
            # 1. Latencia entre raw_metrics y preprocessed_metrics
            query1 = """
                WITH raw_times AS (
                    SELECT timestamp, service_id FROM metrics 
                    WHERE source_type = 'raw'
                    ORDER BY timestamp DESC LIMIT 1000
                ),
                processed_times AS (
                    SELECT timestamp, service_id FROM metrics 
                    WHERE source_type = 'processed'
                    ORDER BY timestamp DESC LIMIT 1000
                )
                SELECT
                    AVG(EXTRACT(EPOCH FROM (p.timestamp - r.timestamp))) as avg_latency
                FROM
                    raw_times r
                    JOIN processed_times p ON r.service_id = p.service_id
                WHERE
                    p.timestamp > r.timestamp
                    AND p.timestamp - r.timestamp < INTERVAL '10 minutes'
            """
            
            # 2. Latencia entre preprocessed_metrics y anomaly_detection
            query2 = """
                WITH processed_times AS (
                    SELECT timestamp, service_id FROM metrics 
                    WHERE source_type = 'processed'
                    ORDER BY timestamp DESC LIMIT 1000
                ),
                anomaly_times AS (
                    SELECT timestamp, service_id FROM anomalies
                    ORDER BY timestamp DESC LIMIT 1000
                )
                SELECT
                    AVG(EXTRACT(EPOCH FROM (a.timestamp - p.timestamp))) as avg_latency
                FROM
                    processed_times p
                    JOIN anomaly_times a ON p.service_id = a.service_id
                WHERE
                    a.timestamp > p.timestamp
                    AND a.timestamp - p.timestamp < INTERVAL '10 minutes'
            """
            
            # Ejecutar consultas
            result1 = pd.read_sql(text(query1), self.engine)
            result2 = pd.read_sql(text(query2), self.engine)
            
            # Extraer resultados
            latencies['collection_to_processing'] = float(result1['avg_latency'].iloc[0]) if not result1.empty and not pd.isna(result1['avg_latency'].iloc[0]) else None
            latencies['processing_to_anomaly'] = float(result2['avg_latency'].iloc[0]) if not result2.empty and not pd.isna(result2['avg_latency'].iloc[0]) else None
            
            # Calcular latencia total
            total_latency = 0
            count = 0
            
            for key, value in latencies.items():
                if value is not None:
                    total_latency += value
                    count += 1
            
            latencies['total'] = total_latency if count > 0 else None
            
            # Determinar estado
            if latencies['total'] is None:
                status = 'unknown'
            elif latencies['total'] < 10.0:
                status = 'healthy'
            elif latencies['total'] < 30.0:
                status = 'warning'
            else:
                status = 'critical'
            
            return {
                'latencies': latencies,
                'status': status,
                'threshold': self.config['alert_thresholds']['processing_latency']
            }
            
        except Exception as e:
            logger.error(f"Error al verificar latencia: {str(e)}")
            return {
                'latencies': {},
                'status': 'error',
                'error': str(e)
            }
    
    def check_component_health(self):
        """Verifica la salud de los componentes del sistema"""
        try:
            components_status = {}
            
            # Verificar cada componente configurado
            for component in self.config['components']:
                # Para este ejemplo, simplemente verificamos si el componente aparece 
                # en logs recientes y si hay errores
                
                # Buscar logs recientes del componente
                query = f"""
                    SELECT
                        COUNT(*) as total_logs,
                        SUM(CASE WHEN log_level IN ('ERROR', 'FATAL', 'CRITICAL') THEN 1 ELSE 0 END) as error_logs
                    FROM logs
                    WHERE service_id = '{component}'
                    AND timestamp > NOW() - INTERVAL '1 hour'
                """
                
                result = pd.read_sql(text(query), self.engine)
                
                if result.empty or result['total_logs'].iloc[0] == 0:
                    # No hay logs recientes, posible componente inactivo
                    components_status[component] = {
                        'status': 'unknown',
                        'last_seen': None,
                        'error_rate': None,
                        'details': 'No logs recientes'
                    }
                else:
                    # Calcular tasa de error
                    total_logs = int(result['total_logs'].iloc[0])
                    error_logs = int(result['error_logs'].iloc[0])
                    error_rate = error_logs / total_logs if total_logs > 0 else 0
                    
                    # Determinar estado
                    if error_rate == 0:
                        status = 'healthy'
                    elif error_rate < 0.05:  # Menos del 5% de errores
                        status = 'warning'
                    else:
                        status = 'critical'
                    
                    # Obtener última vez visto
                    last_seen_query = f"""
                        SELECT MAX(timestamp) as last_seen
                        FROM logs
                        WHERE service_id = '{component}'
                    """
                    
                    last_seen_result = pd.read_sql(text(last_seen_query), self.engine)
                    last_seen = last_seen_result['last_seen'].iloc[0] if not last_seen_result.empty else None
                    
                    components_status[component] = {
                        'status': status,
                        'last_seen': last_seen.isoformat() if last_seen else None,
                        'error_rate': error_rate,
                        'total_logs': total_logs,
                        'error_logs': error_logs
                    }
            
            return components_status
            
        except Exception as e:
            logger.error(f"Error al verificar salud de componentes: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_data_quality(self):
        """Verifica la calidad de los datos en el sistema"""
        try:
            quality_metrics = {}
            
            # 1. Verificar completitud de datos
            completeness_query = """
                SELECT
                    COUNT(*) as total_metrics,
                    SUM(CASE WHEN metric_value IS NULL THEN 1 ELSE 0 END) as null_values
                FROM metrics
                WHERE timestamp > NOW() - INTERVAL '1 day'
            """
            
            completeness_result = pd.read_sql(text(completeness_query), self.engine)
            
            total_metrics = int(completeness_result['total_metrics'].iloc[0]) if not completeness_result.empty else 0
            null_values = int(completeness_result['null_values'].iloc[0]) if not completeness_result.empty else 0
            
            completeness_score = 1.0 - (null_values / total_metrics if total_metrics > 0 else 0)
            
            # 2. Verificar consistencia de datos
            consistency_query = """
                SELECT 
                    service_id,
                    COUNT(DISTINCT metric_name) as unique_metrics,
                    COUNT(*) as total_metrics
                FROM metrics
                WHERE timestamp > NOW() - INTERVAL '1 day'
                GROUP BY service_id
            """
            
            consistency_result = pd.read_sql(text(consistency_query), self.engine)
            
            # Calcular consistencia por servicio
            service_consistency = {}
            for _, row in consistency_result.iterrows():
                service_id = row['service_id']
                unique_metrics = row['unique_metrics']
                total_metrics = row['total_metrics']
                
                # Calculo básico - qué tan bien distribuidas están las métricas
                expected_per_metric = total_metrics / unique_metrics if unique_metrics > 0 else 0
                
                # Consulta para ver la distribución real
                distribution_query = f"""
                    SELECT 
                        metric_name,
                        COUNT(*) as count
                    FROM metrics
                    WHERE service_id = '{service_id}'
                    AND timestamp > NOW() - INTERVAL '1 day'
                    GROUP BY metric_name
                """
                
                distribution_result = pd.read_sql(text(distribution_query), self.engine)
                
                if not distribution_result.empty:
                    counts = distribution_result['count'].values
                    # Medir la desviación de la distribución ideal
                    deviation = np.std(counts) / expected_per_metric if expected_per_metric > 0 else 0
                    consistency_score = 1.0 / (1.0 + deviation)
                else:
                    consistency_score = 0
                
                service_consistency[service_id] = consistency_score
            
            # Calcular score de consistencia promedio
            consistency_score = np.mean(list(service_consistency.values())) if service_consistency else 0
            
            # 3. Verificar frescura de datos
            freshness_query = """
                SELECT
                    MAX(timestamp) as latest_timestamp
                FROM metrics
            """
            
            freshness_result = pd.read_sql(text(freshness_query), self.engine)
            
            if not freshness_result.empty and freshness_result['latest_timestamp'].iloc[0] is not None:
                latest_timestamp = freshness_result['latest_timestamp'].iloc[0]
                now = datetime.now()
                
                # Convertir a timestamp si es string
                if isinstance(latest_timestamp, str):
                    latest_timestamp = datetime.fromisoformat(latest_timestamp.replace('Z', '+00:00'))
                
                # Calcular frescura como qué tan recientes son los datos (1.0 = muy reciente, 0.0 = viejo)
                time_diff_seconds = (now - latest_timestamp).total_seconds()
                freshness_score = 1.0 / (1.0 + time_diff_seconds / 3600.0)  # Normalizado a horas
            else:
                freshness_score = 0
            
            # Calcular score general de calidad
            quality_score = (completeness_score * 0.4) + (consistency_score * 0.3) + (freshness_score * 0.3)
            
            # Determinar estado
            threshold = self.config['alert_thresholds']['data_quality']
            if quality_score >= threshold:
                status = 'healthy'
            elif quality_score >= threshold * 0.7:
                status = 'warning'
            else:
                status = 'critical'
            
            quality_metrics = {
                'completeness': completeness_score,
                'consistency': consistency_score,
                'freshness': freshness_score,
                'overall_score': quality_score,
                'status': status,
                'threshold': threshold
            }
            
            return quality_metrics
            
        except Exception as e:
            logger.error(f"Error al verificar calidad de datos: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_model_performance(self):
        """Verifica el rendimiento de los modelos ML en el sistema"""
        try:
            model_metrics = {}
            
            # Obtener performance métricas de los modelos de predicción
            prediction_query = """
                SELECT
                    service_id,
                    prediction_data
                FROM failure_predictions
                WHERE timestamp > NOW() - INTERVAL '7 days'
                ORDER BY timestamp DESC
            """
            
            prediction_result = pd.read_sql(text(prediction_query), self.engine)
            
            # Procesar resultados por servicio
            service_predictions = {}
            
            for _, row in prediction_result.iterrows():
                service_id = row['service_id']
                prediction_data = row['prediction_data']
                
                if service_id not in service_predictions:
                    service_predictions[service_id] = []
                
                # Añadir datos de predicción
                if isinstance(prediction_data, str):
                    try:
                        prediction_json = json.loads(prediction_data)
                        service_predictions[service_id].append(prediction_json)
                    except:
                        pass
            
            # Evaluar aciertos en predicciones (comparando con fallos reales)
            for service_id, predictions in service_predictions.items():
                # Obtener fallos reales
                failures_query = f"""
                    SELECT timestamp
                    FROM failures
                    WHERE service_id = '{service_id}'
                    AND timestamp > NOW() - INTERVAL '7 days'
                """
                
                failures_result = pd.read_sql(text(failures_query), self.engine)
                failure_times = []
                
                for _, row in failures_result.iterrows():
                    failure_times.append(row['timestamp'])
                
                # Contar aciertos
                true_positives = 0
                false_positives = 0
                
                for prediction in predictions:
                    if 'timestamp' in prediction and 'prediction_horizon' in prediction:
                        # Convertir a timestamp
                        try:
                            pred_time = datetime.fromisoformat(prediction['timestamp'].replace('Z', '+00:00'))
                            horizon_hours = prediction['prediction_horizon']
                            
                            # Ventana de predicción
                            pred_window_start = pred_time
                            pred_window_end = pred_time + timedelta(hours=horizon_hours)
                            
                            # Verificar si algún fallo ocurrió en la ventana
                            failure_in_window = False
                            for failure_time in failure_times:
                                if isinstance(failure_time, str):
                                    failure_time = datetime.fromisoformat(failure_time.replace('Z', '+00:00'))
                                
                                if pred_window_start <= failure_time <= pred_window_end:
                                    failure_in_window = True
                                    break
                            
                            if failure_in_window:
                                true_positives += 1
                            else:
                                false_positives += 1
                        except:
                            continue
                
                # Calcular precisión
                total_predictions = true_positives + false_positives
                precision = true_positives / total_predictions if total_predictions > 0 else 0
                
                # Verificar aciertos en anomalías
                anomaly_query = f"""
                    SELECT
                        COUNT(*) as total_anomalies,
                        SUM(CASE WHEN anomaly_score >= 0.8 THEN 1 ELSE 0 END) as high_score_anomalies
                    FROM anomalies
                    WHERE service_id = '{service_id}'
                    AND timestamp > NOW() - INTERVAL '7 days'
                """
                
                anomaly_result = pd.read_sql(text(anomaly_query), self.engine)
                
                total_anomalies = int(anomaly_result['total_anomalies'].iloc[0]) if not anomaly_result.empty else 0
                high_score_anomalies = int(anomaly_result['high_score_anomalies'].iloc[0]) if not anomaly_result.empty else 0
                
                # Calcular tasa de anomalías de alta confianza
                anomaly_confidence = high_score_anomalies / total_anomalies if total_anomalies > 0 else 0
                
                # Calcular score general para este servicio
                service_score = (precision * 0.7) + (anomaly_confidence * 0.3)
                
                model_metrics[service_id] = {
                    'precision': precision,
                    'anomaly_confidence': anomaly_confidence,
                    'overall_score': service_score,
                    'prediction_count': total_predictions,
                    'anomaly_count': total_anomalies
                }
            
            # Calcular score general
            overall_score = np.mean([m['overall_score'] for m in model_metrics.values()]) if model_metrics else 0
            
            # Determinar estado
            threshold = self.config['alert_thresholds']['model_performance']
            if overall_score >= threshold:
                status = 'healthy'
            elif overall_score >= threshold * 0.7:
                status = 'warning'
            else:
                status = 'critical'
            
            return {
                'services': model_metrics,
                'overall_score': overall_score,
                'status': status,
                'threshold': threshold
            }
            
        except Exception as e:
            logger.error(f"Error al verificar rendimiento de modelos: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_resource_usage(self):
        """Verifica el uso de recursos del sistema"""
        try:
            # Obtener uso de CPU
            cpu_percent = psutil.cpu_percent(interval=1)
            
            # Obtener uso de memoria
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            # Obtener uso de disco
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent
            
            # Determinar estado de cada recurso
            cpu_status = 'healthy'
            if cpu_percent >= self.config['alert_thresholds']['cpu_usage']:
                cpu_status = 'critical'
            elif cpu_percent >= self.config['alert_thresholds']['cpu_usage'] * 0.8:
                cpu_status = 'warning'
            
            memory_status = 'healthy'
            if memory_percent >= self.config['alert_thresholds']['memory_usage']:
                memory_status = 'critical'
            elif memory_percent >= self.config['alert_thresholds']['memory_usage'] * 0.8:
                memory_status = 'warning'
            
            disk_status = 'healthy'
            if disk_percent >= self.config['alert_thresholds']['disk_usage']:
                disk_status = 'critical'
            elif disk_percent >= self.config['alert_thresholds']['disk_usage'] * 0.8:
                disk_status = 'warning'
            
            # Determinar estado general
            if cpu_status == 'critical' or memory_status == 'critical' or disk_status == 'critical':
                overall_status = 'critical'
            elif cpu_status == 'warning' or memory_status == 'warning' or disk_status == 'warning':
                overall_status = 'warning'
            else:
                overall_status = 'healthy'
            
            return {
                'cpu': {
                    'percent': cpu_percent,
                    'status': cpu_status,
                    'threshold': self.config['alert_thresholds']['cpu_usage']
                },
                'memory': {
                    'percent': memory_percent,
                    'total_gb': memory.total / (1024 ** 3),
                    'available_gb': memory.available / (1024 ** 3),
                    'status': memory_status,
                    'threshold': self.config['alert_thresholds']['memory_usage']
                },
                'disk': {
                    'percent': disk_percent,
                    'total_gb': disk.total / (1024 ** 3),
                    'free_gb': disk.free / (1024 ** 3),
                    'status': disk_status,
                    'threshold': self.config['alert_thresholds']['disk_usage']
                },
                'status': overall_status
            }
            
        except Exception as e:
            logger.error(f"Error al verificar uso de recursos: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_database_health(self):
        """Verifica la salud de la base de datos"""
        try:
            # Verificar conexión
            connection_ok = True
            try:
                self.engine.execute(text("SELECT 1"))
            except:
                connection_ok = False
            
            # Verificar tamaño de la base de datos
            size_query = """
                SELECT
                    pg_size_pretty(pg_database_size(current_database())) as db_size,
                    pg_database_size(current_database()) as size_bytes
            """
            
            size_result = pd.read_sql(text(size_query), self.engine)
            
            db_size = size_result['db_size'].iloc[0] if not size_result.empty else "Unknown"
            size_bytes = int(size_result['size_bytes'].iloc[0]) if not size_result.empty else 0
            
            # Verificar conexiones activas
            connections_query = """
                SELECT count(*) as active_connections
                FROM pg_stat_activity
                WHERE state = 'active'
            """
            
            connections_result = pd.read_sql(text(connections_query), self.engine)
            
            active_connections = int(connections_result['active_connections'].iloc[0]) if not connections_result.empty else 0
            
            # Verificar índices ineficientes
            index_query = """
                SELECT
                    relname as table_name,
                    idx_scan as index_scans,
                    seq_scan as seq_scans,
                    idx_tup_read as tuples_read_index,
                    seq_tup_read as tuples_read_seq
                FROM pg_stat_user_tables
                WHERE idx_scan > 0
                ORDER BY seq_scan DESC
            """
            
            try:
                index_result = pd.read_sql(text(index_query), self.engine)
                inefficient_indices = []
                
                for _, row in index_result.iterrows():
                    if row['seq_scans'] > row['index_scans'] * 3:  # Más scans secuenciales que indexados
                        inefficient_indices.append({
                            'table': row['table_name'],
                            'seq_scans': row['seq_scans'],
                            'index_scans': row['index_scans']
                        })
            except:
                inefficient_indices = []
            
            # Determinar estado
            status = 'healthy'
            if not connection_ok:
                status = 'critical'
            elif inefficient_indices or active_connections > 50:
                status = 'warning'
            
            return {
                'connection_ok': connection_ok,
                'db_size': db_size,
                'size_bytes': size_bytes,
                'active_connections': active_connections,
                'inefficient_indices': inefficient_indices,
                'status': status
            }
            
        except Exception as e:
            logger.error(f"Error al verificar salud de la base de datos: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def check_kafka_health(self):
        """Verifica la salud de Kafka"""
        try:
            # Verificar si el productor está conectado
            is_connected = self.producer is not None
            
            # Verificar estadísticas de tópicos (número de mensajes en últimas 24h)
            topic_stats = self.get_topic_stats()
            
            # Determinar estado
            if not is_connected:
                status = 'critical'
            elif any(stat['messages_24h'] == 0 for stat in topic_stats.values()):
                status = 'warning'  # Algún tópico sin actividad
            else:
                status = 'healthy'
            
            return {
                'is_connected': is_connected,
                'topics': topic_stats,
                'status': status
            }
            
        except Exception as e:
            logger.error(f"Error al verificar salud de Kafka: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def get_topic_stats(self):
        """Obtiene estadísticas sobre los tópicos de Kafka desde la base de datos"""
        topics = ['raw_metrics', 'preprocessed_metrics', 'anomalies', 'failure_predictions', 'recommendations']
        topic_stats = {}
        
        for topic in topics:
            # Contar mensajes en últimas 24h (almacenados en la base de datos)
            if topic == 'raw_metrics':
                query = """
                    SELECT COUNT(*) as count
                    FROM metrics
                    WHERE source_type = 'raw'
                    AND timestamp > NOW() - INTERVAL '1 day'
                """
            elif topic == 'preprocessed_metrics':
                query = """
                    SELECT COUNT(*) as count
                    FROM metrics
                    WHERE source_type = 'processed'
                    AND timestamp > NOW() - INTERVAL '1 day'
                """
            elif topic == 'anomalies':
                query = """
                    SELECT COUNT(*) as count
                    FROM anomalies
                    WHERE timestamp > NOW() - INTERVAL '1 day'
                """
            elif topic == 'failure_predictions':
                query = """
                    SELECT COUNT(*) as count
                    FROM failure_predictions
                    WHERE timestamp > NOW() - INTERVAL '1 day'
                """
            elif topic == 'recommendations':
                query = """
                    SELECT COUNT(*) as count
                    FROM recommendations
                    WHERE timestamp > NOW() - INTERVAL '1 day'
                """
            else:
                continue
            
            try:
                result = pd.read_sql(text(query), self.engine)
                count = int(result['count'].iloc[0]) if not result.empty else 0
            except:
                count = 0
            
            topic_stats[topic] = {
                'messages_24h': count
            }
        
        return topic_stats
    
    def calculate_overall_health(self, diagnostic_result):
        """Calcula la salud general del sistema basado en resultados de diagnóstico"""
        # Mapear estados a números
        status_map = {
            'healthy': 0,
            'warning': 1,
            'critical': 2,
            'error': 2,
            'unknown': 1
        }
        
        # Recopilar estados de componentes
        statuses = []
        
        # Latencia de procesamiento
        if 'processing_latency' in diagnostic_result and 'status' in diagnostic_result['processing_latency']:
            statuses.append(status_map.get(diagnostic_result['processing_latency']['status'], 1))
        
        # Salud de componentes
        if 'component_health' in diagnostic_result:
            for component, health in diagnostic_result['component_health'].items():
                if 'status' in health:
                    statuses.append(status_map.get(health['status'], 1))
        
        # Calidad de datos
        if 'data_quality' in diagnostic_result and 'status' in diagnostic_result['data_quality']:
            statuses.append(status_map.get(diagnostic_result['data_quality']['status'], 1))
        
        # Rendimiento de modelos
        if 'model_performance' in diagnostic_result and 'status' in diagnostic_result['model_performance']:
            statuses.append(status_map.get(diagnostic_result['model_performance']['status'], 1))
        
        # Uso de recursos
        if 'resource_usage' in diagnostic_result and 'status' in diagnostic_result['resource_usage']:
            statuses.append(status_map.get(diagnostic_result['resource_usage']['status'], 1))
        
        # Salud de base de datos
        if 'database_health' in diagnostic_result and 'status' in diagnostic_result['database_health']:
            statuses.append(status_map.get(diagnostic_result['database_health']['status'], 1))
        
        # Salud de Kafka
        if 'kafka_health' in diagnostic_result and 'status' in diagnostic_result['kafka_health']:
            statuses.append(status_map.get(diagnostic_result['kafka_health']['status'], 1))
        
        # Determinar estado general
        if not statuses:
            return 'unknown'
        
        max_status = max(statuses)
        
        if max_status == 0:
            return 'healthy'
        elif max_status == 1:
            return 'warning'
        else:
            return 'critical'
    
    def update_system_status(self, diagnostic_result):
        """Actualiza el estado del sistema con los resultados del diagnóstico"""
        # Actualizar estado general
        self.system_status['overall_health'] = diagnostic_result['overall_health']
        
        # Actualizar estados de componentes
        if 'component_health' in diagnostic_result:
            self.system_status['components_status'] = {}
            for component, health in diagnostic_result['component_health'].items():
                self.system_status['components_status'][component] = {
                    'status': health.get('status', 'unknown'),
                    'last_seen': health.get('last_seen')
                }
        
        # Actualizar timestamp
        self.system_status['last_update'] = datetime.now().isoformat()
    
    def publish_diagnostic_results(self, diagnostic_result):
        """Publica los resultados del diagnóstico en Kafka"""
        try:
            if self.producer:
                # Simplificar resultado para publicación
                simplified_result = {
                    'timestamp': diagnostic_result['timestamp'],
                    'overall_health': diagnostic_result['overall_health'],
                    'components': {}
                }
                
                # Incluir estado de componentes
                if 'component_health' in diagnostic_result:
                    for component, health in diagnostic_result['component_health'].items():
                        simplified_result['components'][component] = {
                            'status': health.get('status', 'unknown'),
                            'error_rate': health.get('error_rate')
                        }
                
                # Incluir métricas clave
                if 'processing_latency' in diagnostic_result and 'latencies' in diagnostic_result['processing_latency']:
                    simplified_result['latency'] = diagnostic_result['processing_latency']['latencies'].get('total')
                
                if 'data_quality' in diagnostic_result:
                    simplified_result['data_quality'] = diagnostic_result['data_quality'].get('overall_score')
                
                if 'resource_usage' in diagnostic_result:
                    simplified_result['resource_usage'] = {
                        'cpu': diagnostic_result['resource_usage'].get('cpu', {}).get('percent'),
                        'memory': diagnostic_result['resource_usage'].get('memory', {}).get('percent'),
                        'disk': diagnostic_result['resource_usage'].get('disk', {}).get('percent')
                    }
                
                # Publicar en tópico de diagnósticos
                self.producer.send('system_diagnostics', simplified_result)
                logger.info("Diagnóstico publicado en Kafka")
        except Exception as e:
            logger.error(f"Error al publicar resultados de diagnóstico: {str(e)}")
    
    def store_diagnostic_results(self, diagnostic_result):
        """Almacena los resultados del diagnóstico en la base de datos"""
        try:
            # Preparar datos para la base de datos
            diagnostic_db = {
                'timestamp': datetime.now(),
                'overall_health': diagnostic_result['overall_health'],
                'processing_latency': json.dumps(diagnostic_result.get('processing_latency', {})),
                'component_health': json.dumps(diagnostic_result.get('component_health', {})),
                'data_quality': json.dumps(diagnostic_result.get('data_quality', {})),
                'model_performance': json.dumps(diagnostic_result.get('model_performance', {})),
                'resource_usage': json.dumps(diagnostic_result.get('resource_usage', {})),
                'database_health': json.dumps(diagnostic_result.get('database_health', {})),
                'kafka_health': json.dumps(diagnostic_result.get('kafka_health', {}))
            }
            
            # Convertir a DataFrame para inserción
            diagnostic_df = pd.DataFrame([diagnostic_db])
            
            # Insertar en la tabla de diagnósticos
            diagnostic_df.to_sql('system_diagnostics', self.engine, if_exists='append', index=False)
            
            logger.info("Diagnóstico almacenado en la base de datos")
            
        except Exception as e:
            logger.error(f"Error al almacenar diagnóstico: {str(e)}")
    
    def handle_critical_issues(self, diagnostic_result):
        """Maneja problemas críticos detectados en el diagnóstico"""
        try:
            critical_issues = []
            
            # Identificar problemas críticos
            if diagnostic_result.get('processing_latency', {}).get('status') == 'critical':
                critical_issues.append({
                    'component': 'processing_pipeline',
                    'issue': 'high_latency',
                    'details': f"Latencia de procesamiento alta: {diagnostic_result['processing_latency']['latencies'].get('total')} segundos"
                })
            
            if 'component_health' in diagnostic_result:
                for component, health in diagnostic_result['component_health'].items():
                    if health.get('status') == 'critical':
                        critical_issues.append({
                            'component': component,
                            'issue': 'component_failure',
                            'details': f"Componente {component} en estado crítico, tasa de error: {health.get('error_rate')}"
                        })
            
            if diagnostic_result.get('resource_usage', {}).get('status') == 'critical':
                resource_usage = diagnostic_result['resource_usage']
                if resource_usage.get('cpu', {}).get('status') == 'critical':
                    critical_issues.append({
                        'component': 'system',
                        'issue': 'high_cpu_usage',
                        'details': f"Uso de CPU crítico: {resource_usage['cpu']['percent']}%"
                    })
                
                if resource_usage.get('memory', {}).get('status') == 'critical':
                    critical_issues.append({
                        'component': 'system',
                        'issue': 'high_memory_usage',
                        'details': f"Uso de memoria crítico: {resource_usage['memory']['percent']}%"
                    })
                
                if resource_usage.get('disk', {}).get('status') == 'critical':
                    critical_issues.append({
                        'component': 'system',
                        'issue': 'high_disk_usage',
                        'details': f"Uso de disco crí