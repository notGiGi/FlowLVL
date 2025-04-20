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
        
        # Colector de m�tricas
        collector_config = {
            'config_path': os.path.join(self.config_dir, 'collector_config.yaml'),
            'output_dir': self.data_dir
        }
        self.collector = SimpleCollector(collector_config)
        
        # Detector de anomal�as
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
        
        # Mantener estado
        self.running = False
        self.collector_thread = None
        self.anomaly_thread = None
        
        # Historial de eventos
        self.events = []
        self.max_events = 1000
        
        logger.info("Sistema inicializado correctamente")
    
    def start(self):
        """Inicia todos los componentes del sistema"""
        logger.info("Iniciando sistema...")
        self.running = True
        
        # Iniciar colector en thread separado
        self.collector_thread = threading.Thread(target=self.collector.collect_metrics)
        self.collector_thread.daemon = True
        self.collector_thread.start()
        
        # Iniciar procesamiento de anomal�as en thread separado
        self.anomaly_thread = threading.Thread(target=self.process_metrics)
        self.anomaly_thread.daemon = True
        self.anomaly_thread.start()
        
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
        
        logger.info("Sistema detenido correctamente")
    
    def process_metrics(self):
        """Procesa m�tricas en busca de anomal�as"""
        logger.info("Iniciando procesamiento de m�tricas")
        
        while self.running:
            try:
                # Recorrer cada servicio del colector
                for service_id, metrics_list in self.collector.metrics_history.items():
                    if not metrics_list:
                        continue
                    
                    # Obtener m�tricas m�s recientes
                    latest_metrics = metrics_list[-1]
                    
                    # Detectar anomal�as
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
                    
                    # Si hay anomal�a, recomendar acci�n
                    if is_anomaly:
                        logger.info(f"Anomal�a detectada en {service_id}: {anomaly_score:.3f}")
                        
                        # Procesar recomendaci�n
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
                        
                        # Si hay acci�n recomendada y autoremediaci�n habilitada
                        if self.config.get('auto_remediation', False) and recommendation and 'recommended_action' in recommendation:
                            action = recommendation['recommended_action']
                            
                            logger.info(f"Ejecutando acci�n: {action.get('action_id')} para {service_id}")
                            
                            # Ejecutar acci�n
                            success = self.recommender.execute_action(action, latest_metrics)
                            
                            # Registrar evento
                            self._add_event({
                                'type': 'action_execution',
                                'timestamp': datetime.now().isoformat(),
                                'service_id': service_id,
                                'action_id': action.get('action_id'),
                                'success': success
                            })
                
                # Pausar antes de la siguiente iteraci�n
                time.sleep(self.config.get('processing_interval', 60))
                
            except Exception as e:
                logger.error(f"Error en procesamiento de m�tricas: {str(e)}")
                time.sleep(10)  # Esperar antes de reintentar
    
    def _add_event(self, event):
        """A�ade evento al historial"""
        self.events.append(event)
        
        # Limitar tama�o
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
        
        # Ordenar por tiempo (m�s recientes primero)
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
        
        # Calcular tasa de �xito
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
        """Cambia modo de ejecuci�n"""
        return self.recommender.set_execution_mode(mode)
    
    def save_configuration(self):
        """Guarda configuraci�n actual"""
        config_file = os.path.join(self.config_dir, 'system_config.yaml')
        
        try:
            with open(config_file, 'w') as f:
                yaml.dump(self.config, f)
            logger.info(f"Configuraci�n guardada en {config_file}")
            return True
        except Exception as e:
            logger.error(f"Error al guardar configuraci�n: {str(e)}")
            return False
    
    def set_threshold(self, service_id, metric, value):
        """Establece umbral espec�fico"""
        return self.detector.set_threshold(service_id, metric, value)

# Manejador de se�ales
def signal_handler(sig, frame):
    logger.info("Se�al de interrupci�n recibida")
    if 'system' in globals():
        system.stop()
    sys.exit(0)

# Funciones de l�nea de comandos
def create_default_config():
    """Crea archivos de configuraci�n por defecto"""
    # Configuraci�n del colector
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
    
    # Guardar configuraci�n del colector
    with open('./config/collector_config.yaml', 'w') as f:
        yaml.dump(collector_config, f)
    
    # Configuraci�n del sistema
    system_config = {
        'anomaly_threshold': 0.7,
        'execution_mode': 'simulation',
        'auto_remediation': False,
        'processing_interval': 60
    }
    
    # Guardar configuraci�n del sistema
    with open('./config/system_config.yaml', 'w') as f:
        yaml.dump(system_config, f)
    
    print("Archivos de configuraci�n creados en ./config/")
    print("Recuerda editar collector_config.yaml con la informaci�n de tu servicio real")

# Funci�n principal
def main():
    global system
    
    # Configurar se�ales
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parsear argumentos
    parser = argparse.ArgumentParser(description='Sistema de Mantenimiento Predictivo')
    parser.add_argument('--config', help='Ruta al archivo de configuraci�n', default='./config/system_config.yaml')
    parser.add_argument('--init', action='store_true', help='Crear archivos de configuraci�n por defecto')
    parser.add_argument('--execution-mode', choices=['simulation', 'real'], help='Modo de ejecuci�n')
    
    args = parser.parse_args()
    
    # Crear configuraci�n inicial si se solicita
    if args.init:
        create_default_config()
        return
    
    # Cargar configuraci�n
    config = {}
    if os.path.exists(args.config):
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Archivo de configuraci�n no encontrado: {args.config}")
        logger.warning("Usando configuraci�n por defecto")
    
    # Sobreescribir modo de ejecuci�n si se proporciona como argumento
    if args.execution_mode:
        config['execution_mode'] = args.execution_mode
    
    # Inicializar y arrancar sistema
    system = PredictiveMaintenanceSystem(config)
    
    try:
        # Iniciar el sistema
        system.start()
        
        # Mantener ejecuci�n
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Interrupci�n del usuario")
        system.stop()
    
    except Exception as e:
        logger.error(f"Error en ejecuci�n principal: {str(e)}")
        if 'system' in locals():
            system.stop()

if __name__ == "__main__":
    main()
