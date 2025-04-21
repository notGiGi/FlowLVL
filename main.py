# -*- coding: utf-8 -*-
import os
import json
import time
import logging
import argparse
import yaml
from datetime import datetime
import threading
import signal
import sys

# Importar componentes
from collectors.simple_collector import SimpleCollector
from anomaly_detector.simple_detector import SimpleAnomalyDetector
from action_recommender.simple_recommender import SimpleActionRecommender
from predictor.advanced_predictor import AdvancedPredictor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("predictive_maintenance.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('predictive_maintenance')

class PredictiveMaintenanceSystem:
    """Sistema integrado para prueba real de mantenimiento predictivo"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.config_dir = self.config.get('config_dir', './config')
        self.data_dir = self.config.get('data_dir', './data')
        
        # Asegurar que existen directorios
        os.makedirs(self.config_dir, exist_ok=True)
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Inicializar componentes
        logger.info("Inicializando sistema de mantenimiento predictivo...")
        
        # Colector de mÃ©tricas
        collector_config = os.path.join(self.config_dir, 'collector_config.yaml')
        self.collector = SimpleCollector(collector_config)
        
        # Detector de anomalÃ­as
        detector_config = {
            'anomaly_threshold': self.config.get('anomaly_threshold', 0.7),
            'data_dir': self.data_dir
        }
        self.detector = SimpleAnomalyDetector(detector_config)
        
        # Recomendador de acciones
        recommender_config = {
            'config_dir': self.config_dir,
            'execution_mode': self.config.get('execution_mode', 'simulation')
        }
        self.recommender = SimpleActionRecommender(recommender_config)
        
        # Predictor de tendencias
        predictor_config = {
            'prediction_threshold': self.config.get('prediction_threshold', 0.6),
            'prediction_horizon': self.config.get('prediction_horizon', 24),  # horas
            'data_dir': self.data_dir
        }
        self.predictor = AdvancedPredictor(predictor_config)
        self.predictor.load_prediction_models()
        
        # Mantener estado
        self.running = False
        self.collector_thread = None
        self.anomaly_thread = None
        self.prediction_thread = None
        
        # Historial de eventos
        self.events = []
        self.max_events = 1000
        
        logger.info("Sistema inicializado correctamente")
    
    def load_existing_metrics(self):
        """Carga mÃ©tricas existentes desde archivos en el directorio de datos"""
        try:
            logger.info(f"Cargando mÃ©tricas existentes desde {self.data_dir}")
            files = [f for f in os.listdir(self.data_dir) if f.endswith('.json')]
            
            for file in files:
                service_id = file.split('_')[0]  # Extraer ID de servicio del nombre de archivo
                filepath = os.path.join(self.data_dir, file)
                
                with open(filepath, 'r', encoding='utf-8-sig') as f:
                    data = json.load(f)
                
                # Solo procesar si hay datos
                if data and isinstance(data, list):
                    logger.info(f"Cargando {len(data)} puntos de mÃ©trica para {service_id}")
                    
                    # AÃ±adir cada punto al historial del colector
                    for point in data:
                        if 'service_id' in point and 'timestamp' in point:
                            if service_id not in self.collector.metrics_history:
                                self.collector.metrics_history[service_id] = []
                            
                            # Verificar si ya existe
                            exists = False
                            for existing in self.collector.metrics_history[service_id]:
                                if existing.get('timestamp') == point.get('timestamp'):
                                    exists = True
                                    break
                            
                            if not exists:
                                self.collector.metrics_history[service_id].append(point)
            
            # Ordenar puntos por timestamp
            for service_id, metrics in self.collector.metrics_history.items():
                self.collector.metrics_history[service_id] = sorted(
                    metrics, 
                    key=lambda x: x.get('timestamp', '')
                )
                
        except Exception as e:
            logger.error(f"Error al cargar mÃ©tricas existentes: {str(e)}")
        
    def start(self):
        """Inicia todos los componentes del sistema"""
        logger.info("Iniciando sistema...")
        self.running = True
        
        # Cargar mÃ©tricas existentes
        self.load_existing_metrics()
        
        # Iniciar colector en thread separado
        self.collector_thread = threading.Thread(target=self.collector.collect_metrics)
        self.collector_thread.daemon = True
        self.collector_thread.start()
        
        # Iniciar procesamiento de anomalÃ­as en thread separado
        self.anomaly_thread = threading.Thread(target=self.process_metrics)
        self.anomaly_thread.daemon = True
        self.anomaly_thread.start()
        
        # Iniciar procesamiento de predicciones en thread separado
        self.prediction_thread = threading.Thread(target=self.process_predictions)
        self.prediction_thread.daemon = True
        self.prediction_thread.start()
        
        logger.info("Sistema iniciado correctamente")
    
    def stop(self):
        """Detiene los componentes del sistema"""
        logger.info("Deteniendo sistema...")
        self.running = False
        
        # Esperar a que terminen threads
        if self.collector_thread and self.collector_thread.is_alive():
            self.collector_thread.join(timeout=3)
        
        if self.anomaly_thread and self.anomaly_thread.is_alive():
            self.anomaly_thread.join(timeout=3)
        
        if self.prediction_thread and self.prediction_thread.is_alive():
            self.prediction_thread.join(timeout=3)
        
        logger.info("Sistema detenido correctamente")
    
    def process_metrics(self):
        """Procesa mÃ©tricas en busca de anomalÃ­as"""
        logger.info("Iniciando procesamiento de mÃ©tricas")
        
        while self.running:
            try:
                # Recorrer cada servicio del colector
                for service_id, metrics_list in self.collector.metrics_history.items():
                    if not metrics_list:
                        continue
                    
                    # Obtener mÃ©tricas mÃ¡s recientes
                    latest_metrics = metrics_list[-1]
                    
                    # Detectar anomalÃ­as
                    is_anomaly, anomaly_score, details = self.detector.detect_anomalies(latest_metrics)
                    
                    # Registrar evento
                    self._add_event({
                        'type': 'anomaly_detection',
                        'timestamp': datetime.now().isoformat(),
                        'service_id': service_id,
                        'is_anomaly': is_anomaly,
                        'anomaly_score': anomaly_score,
                        'details': details
                    })
                    
                    # Si hay anomalÃ­a, recomendar acciÃ³n
                    if is_anomaly:
                        logger.info(f"AnomalÃ­a detectada en {service_id}: {anomaly_score:.3f}")
                        
                        # Procesar recomendaciÃ³n
                        recommendation = self.recommender.process_and_recommend(anomaly_data={
                            'service_id': service_id,
                            'anomaly_score': anomaly_score,
                            'details': {
                                'metrics': latest_metrics
                            }
                        })
                        
                        # Registrar evento
                        self._add_event({
                            'type': 'recommendation',
                            'timestamp': datetime.now().isoformat(),
                            'service_id': service_id,
                            'recommendation': recommendation
                        })
                        
                        # Si hay acciÃ³n recomendada y autoremediaciÃ³n habilitada
                        if self.config.get('auto_remediation', False) and recommendation and 'recommended_action' in recommendation:
                            action = recommendation['recommended_action']
                            
                            logger.info(f"Ejecutando acciÃ³n: {action.get('action_id')} para {service_id}")
                            
                            # Ejecutar acciÃ³n
                            success = self.recommender.execute_action(action, latest_metrics)
                            
                            # Registrar evento
                            self._add_event({
                                'type': 'action_execution',
                                'timestamp': datetime.now().isoformat(),
                                'service_id': service_id,
                                'action_id': action.get('action_id'),
                                'success': success
                            })
                
                # Pausar antes de la siguiente iteraciÃ³n
                time.sleep(self.config.get('processing_interval', 60))
                
            except Exception as e:
                logger.error(f"Error en procesamiento de mÃ©tricas: {str(e)}")
                time.sleep(10)  # Esperar antes de reintentar
    
    def process_predictions(self):
        """Procesa predicciones para detectar posibles anomalÃ­as futuras"""
        logger.info("Iniciando procesamiento de predicciones")
        
        while self.running:
            try:
                # Recorrer cada servicio del colector
                for service_id, metrics_list in self.collector.metrics_history.items():
                    if len(metrics_list) < self.predictor.min_history_points:
                        continue
                    
                    # Realizar predicciÃ³n
                    prediction = self.predictor.get_failure_prediction_timeline(service_id, metrics_list)
                    
                    # Registrar predicciÃ³n si existe
                    if prediction and prediction['probability'] > 0:
                        # Guardar predicciÃ³n
                        self.predictor.save_prediction(prediction)
                        
                        # Registrar evento
                        self._add_event({
                            'type': 'prediction',
                            'timestamp': datetime.now().isoformat(),
                            'service_id': service_id,
                            'prediction': {
                                'probability': prediction['probability'],
                                'confidence': prediction['confidence'],
                                'prediction_horizon': prediction['prediction_horizon'],
                                'predicted_metrics': prediction['predicted_metrics']
                            }
                        })
                        
                        # Si la probabilidad es alta, recomendar acciÃ³n preventiva
                        if (prediction['probability'] >= self.predictor.prediction_threshold and
                            prediction['confidence'] >= 0.5):
                            logger.info(f"PredicciÃ³n de anomalÃ­a para {service_id}: {prediction['probability']:.3f}")
                            
                            # Procesar recomendaciÃ³n
                            recommendation = self.recommender.process_and_recommend(prediction_data=prediction)
                            
                            # Registrar evento de recomendaciÃ³n
                            self._add_event({
                                'type': 'preventive_recommendation',
                                'timestamp': datetime.now().isoformat(),
                                'service_id': service_id,
                                'recommendation': recommendation
                            })
                            
                            # Si hay acciÃ³n recomendada y auto-remediation habilitada
                            if (self.config.get('auto_remediation', False) and 
                                recommendation and 
                                'recommended_action' in recommendation):
                                action = recommendation['recommended_action']
                                
                                logger.info(f"Ejecutando acciÃ³n preventiva: {action.get('action_id')} para {service_id}")
                                
                                # Ejecutar acciÃ³n
                                # Usamos las mÃ©tricas actuales para la ejecuciÃ³n
                                success = self.recommender.execute_action(action, metrics_list[-1])
                                
                                # Registrar evento
                                self._add_event({
                                    'type': 'preventive_action_execution',
                                    'timestamp': datetime.now().isoformat(),
                                    'service_id': service_id,
                                    'action_id': action.get('action_id'),
                                    'success': success
                                })
                
                # Pausar antes de la siguiente iteraciÃ³n
                time.sleep(self.config.get('prediction_interval', 3600))  # Por defecto, cada hora
                
            except Exception as e:
                logger.error(f"Error en procesamiento de predicciones: {str(e)}")
                time.sleep(60)  # Esperar antes de reintentar
    
    def _add_event(self, event):
        """AÃ±ade evento al historial"""
        self.events.append(event)
        
        # Limitar tamaÃ±o
        if len(self.events) > self.max_events:
            self.events = self.events[-self.max_events:]
    
    def get_events(self, limit=50, event_type=None, service_id=None):
        """Obtiene eventos filtrados"""
        filtered_events = self.events
        
        # Filtrar por tipo
        if event_type:
            filtered_events = [e for e in filtered_events if e.get('type') == event_type]
        
        # Filtrar por servicio
        if service_id:
            filtered_events = [e for e in filtered_events if e.get('service_id') == service_id]
        
        # Ordenar por tiempo (mÃ¡s recientes primero)
        sorted_events = sorted(filtered_events, key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Limitar resultados
        return sorted_events[:limit]
    
    def get_system_status(self):
        """Obtiene estado actual del sistema"""
        # Contar eventos por tipo
        anomaly_count = len([e for e in self.events if e.get('type') == 'anomaly_detection' and e.get('is_anomaly', False)])
        recommendation_count = len([e for e in self.events if e.get('type') == 'recommendation'])
        action_count = len([e for e in self.events if e.get('type') == 'action_execution'])
        success_actions = len([e for e in self.events if e.get('type') == 'action_execution' and e.get('success', False)])
        
        # Calcular tasa de Ã©xito
        success_rate = success_actions / max(1, action_count)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'status': 'running' if self.running else 'stopped',
            'execution_mode': self.recommender.execution_mode,
            'auto_remediation': self.config.get('auto_remediation', False),
            'services_monitored': len(self.collector.metrics_history),
            'anomalies_detected': anomaly_count,
            'recommendations_made': recommendation_count,
            'actions_executed': action_count,
            'action_success_rate': success_rate
        }
    
    def set_execution_mode(self, mode):
        """Cambia modo de ejecuciÃ³n"""
        return self.recommender.set_execution_mode(mode)
    
    def save_configuration(self):
        """Guarda configuraciÃ³n actual"""
        config_file = os.path.join(self.config_dir, 'system_config.yaml')
        
        try:
            with open(config_file, 'w') as f:
                yaml.dump(self.config, f)
            logger.info(f"ConfiguraciÃ³n guardada en {config_file}")
            return True
        except Exception as e:
            logger.error(f"Error al guardar configuraciÃ³n: {str(e)}")
            return False
    
    def set_threshold(self, service_id, metric, value):
        """Establece umbral especÃ­fico"""
        return self.detector.set_threshold(service_id, metric, value)

# Manejador de seÃ±ales
def signal_handler(sig, frame):
    logger.info("SeÃ±al de interrupciÃ³n recibida")
    if 'system' in globals():
        system.stop()
    sys.exit(0)

# Funciones de lÃ­nea de comandos
def create_default_config():
    """Crea archivos de configuraciÃ³n por defecto"""
    # ConfiguraciÃ³n del colector
    collector_config = {
        'collection_interval': 60,  # segundos
        'services': [
            {
                'service_id': 'web-service',
                'endpoint_type': 'prometheus',
                'endpoint': 'http://prometheus:9090',
                'metrics': ['memory_usage', 'cpu_usage', 'gc_collection_time', 'response_time_ms', 'error_rate']
            }
        ],
        'output_dir': './data'
    }
    
    # Crear directorio config si no existe
    os.makedirs('./config', exist_ok=True)
    
    # Guardar configuraciÃ³n del colector
    with open('./config/collector_config.yaml', 'w') as f:
        yaml.dump(collector_config, f)
    
    # ConfiguraciÃ³n del sistema
    system_config = {
        'anomaly_threshold': 0.7,
        'execution_mode': 'simulation',
        'auto_remediation': False,
        'processing_interval': 60,
        'prediction_threshold': 0.6,
        'prediction_horizon': 24,
        'prediction_interval': 3600
    }
    
    # Guardar configuraciÃ³n del sistema
    with open('./config/system_config.yaml', 'w') as f:
        yaml.dump(system_config, f)
    
    print("Archivos de configuraciÃ³n creados en ./config/")
    print("Recuerda editar collector_config.yaml con la informaciÃ³n de tu servicio real")

# FunciÃ³n principal
def main():
    global system
    
    # Configurar seÃ±ales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parsear argumentos
    parser = argparse.ArgumentParser(description='Sistema de Mantenimiento Predictivo')
    parser.add_argument('--config', help='Ruta al archivo de configuraciÃ³n', default='./config/system_config.yaml')
    parser.add_argument('--init', action='store_true', help='Crear archivos de configuraciÃ³n por defecto')
    parser.add_argument('--execution-mode', choices=['simulation', 'real'], help='Modo de ejecuciÃ³n')
    
    args = parser.parse_args()
    
    # Crear configuraciÃ³n inicial si se solicita
    if args.init:
        create_default_config()
        return
    
    # Cargar configuraciÃ³n
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Archivo de configuraciÃ³n no encontrado: {args.config}")
        logger.warning("Usando configuraciÃ³n por defecto")
    
    # Sobreescribir modo de ejecuciÃ³n si se proporciona como argumento
    if args.execution_mode:
        config['execution_mode'] = args.execution_mode
    
    # Inicializar y arrancar sistema
    system = PredictiveMaintenanceSystem(config)
    
    try:
        # Iniciar el sistema
        system.start()
        
        # Mantener ejecuciÃ³n
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("InterrupciÃ³n del usuario")
        system.stop()
    
    except Exception as e:
        logger.error(f"Error en ejecuciÃ³n principal: {str(e)}")
        if 'system' in locals():
            system.stop()

if __name__ == "__main__":
    main()



