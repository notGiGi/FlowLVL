# -*- coding: utf-8 -*-
import requests
import logging
import time
import json
import os
import yaml
from datetime import datetime

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("collector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('simple_collector')

class SimpleCollector:
    """Colector simplificado para prueba real"""
    
    def __init__(self, config_path="./config/collector_config.yaml"):
        self.config = self.load_config(config_path)
        self.output_dir = self.config.get('output_dir', './data')
        
        # Crear directorio de salida si no existe
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Métricas recolectadas
        self.metrics_history = {}
        
        logger.info("Colector inicializado")
    
    def load_config(self, config_path):
        """Carga la configuración desde un archivo YAML"""
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            logger.info(f"Configuración cargada desde {config_path}")
            return config
        except Exception as e:
            logger.error(f"Error al cargar configuración: {str(e)}")
            return self.get_default_config()
    
    def get_default_config(self):
        """Devuelve configuración por defecto"""
        return {
            'collection_interval': 60,  # segundos
            'services': [
                {
                    'service_id': 'example-service',
                    'endpoint_type': 'prometheus',
                    'endpoint': 'http://localhost:9090',
                    'metrics': ['up', 'memory_usage', 'cpu_usage']
                }
            ],
            'output_dir': './data'
        }
    
    def collect_metrics(self):
        """Recolecta métricas de los servicios configurados"""
        while True:
            try:
                for service in self.config.get('services', []):
                    service_id = service.get('service_id', 'unknown')
                    endpoint_type = service.get('endpoint_type', 'prometheus')
                    
                    logger.info(f"Recolectando métricas para {service_id} ({endpoint_type})")
                    
                    # Recolectar según tipo de endpoint
                    if endpoint_type == 'prometheus':
                        metrics = self.collect_from_prometheus(service)
                    elif endpoint_type == 'direct':
                        metrics = self.collect_direct(service)
                    else:
                        logger.warning(f"Tipo de endpoint desconocido: {endpoint_type}")
                        continue
                    
                    if metrics:
                        # Añadir timestamp
                        metrics['timestamp'] = datetime.now().isoformat()
                        metrics['service_id'] = service_id
                        
                        # Guardar métricas
                        self.save_metrics(service_id, metrics)
                        
                        # Actualizar historial
                        if service_id not in self.metrics_history:
                            self.metrics_history[service_id] = []
                        
                        # Limitar historial a 100 puntos
                        self.metrics_history[service_id].append(metrics)
                        if len(self.metrics_history[service_id]) > 100:
                            self.metrics_history[service_id] = self.metrics_history[service_id][-100:]
                
                # Esperar hasta la próxima recolección
                time.sleep(self.config.get('collection_interval', 60))
                
            except Exception as e:
                logger.error(f"Error en recolección: {str(e)}")
                time.sleep(30)  # Esperar antes de reintentar
    
    def collect_from_prometheus(self, service):
        """Recolecta métricas desde un endpoint Prometheus"""
        try:
            endpoint = service.get('endpoint', '')
            metrics_to_collect = service.get('metrics', [])
            result = {}
            
            for metric_name in metrics_to_collect:
                # Consultar Prometheus
                response = requests.get(
                    f"{endpoint}/api/v1/query",
                    params={'query': metric_name},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Procesar resultado
                    if 'data' in data and 'result' in data['data']:
                        for item in data['data']['result']:
                            # Extraer etiquetas
                            labels = item.get('metric', {})
                            instance = labels.get('instance', 'unknown')
                            
                            # Crear clave única
                            metric_key = f"{metric_name}_{instance}".replace('.', '_').replace(':', '_')
                            
                            # Extraer valor
                            if 'value' in item:
                                try:
                                    value = float(item['value'][1])
                                    result[metric_key] = value
                                except (ValueError, TypeError):
                                    logger.warning(f"Valor no numérico para {metric_key}")
            
            logger.info(f"Recolectadas {len(result)} métricas de Prometheus")
            return result
            
        except Exception as e:
            logger.error(f"Error al recolectar de Prometheus: {str(e)}")
            return {}
    
    def collect_direct(self, service):
        """Recolecta métricas directamente de un endpoint"""
        try:
            endpoint = service.get('endpoint', '')
            headers = service.get('headers', {})
            
            # Realizar solicitud
            response = requests.get(
                endpoint,
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                # Intentar parsear como JSON
                try:
                    data = response.json()
                    
                    # Extraer métricas según configuración
                    metrics = {}
                    metrics_map = service.get('metrics_map', {})
                    
                    if metrics_map:
                        # Mapeo personalizado
                        for dest_key, source_path in metrics_map.items():
                            # Navegación por path
                            value = data
                            for key in source_path.split('.'):
                                if key in value:
                                    value = value[key]
                                else:
                                    value = None
                                    break
                            
                            if value is not None and isinstance(value, (int, float)):
                                metrics[dest_key] = value
                    else:
                        # Sin mapeo, tomar todos los valores numéricos
                        for key, value in data.items():
                            if isinstance(value, (int, float)):
                                metrics[key] = value
                    
                    logger.info(f"Recolectadas {len(metrics)} métricas directamente")
                    return metrics
                    
                except ValueError:
                    logger.error("Respuesta no es JSON válido")
                    return {}
            else:
                logger.error(f"Error en respuesta: {response.status_code}")
                return {}
                
        except Exception as e:
            logger.error(f"Error al recolectar directamente: {str(e)}")
            return {}
    
    def save_metrics(self, service_id, metrics):
        """Guarda métricas en archivo"""
        try:
            # Crear nombre de archivo
            filename = f"{service_id}_{datetime.now().strftime('%Y%m%d')}.json"
            filepath = os.path.join(self.output_dir, filename)
            
            # Leer archivo existente si existe
            data = []
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
            
            # Añadir nuevas métricas
            data.append(metrics)
            
            # Guardar archivo
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
                
            logger.debug(f"Métricas guardadas en {filepath}")
            
        except Exception as e:
            logger.error(f"Error al guardar métricas: {str(e)}")
    
    def get_latest_metrics(self, service_id):
        """Obtiene las métricas más recientes para un servicio"""
        if service_id in self.metrics_history and self.metrics_history[service_id]:
            return self.metrics_history[service_id][-1]
        return None

# Script principal
if __name__ == "__main__":
    collector = SimpleCollector()
    try:
        collector.collect_metrics()
    except KeyboardInterrupt:
        logger.info("Colector detenido por el usuario")