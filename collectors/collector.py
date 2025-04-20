# -*- coding: utf-8 -*-
import os
import json
import logging
import time
import threading
import requests
import socket
import yaml
import re
from datetime import datetime
from kafka import KafkaProducer
from confluent_kafka import Consumer as ConfluentConsumer
from confluent_kafka import Producer as ConfluentProducer
import subprocess
from prometheus_client.parser import text_string_to_metric_families
import psutil
import pandas as pd
from sqlalchemy import create_engine
from kubernetes import client, config

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('data_collector')

class DataCollector:
    def __init__(self):
        # Configuración de conexiones
        self.kafka_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        
        # Configurar productor Kafka
        self.producer = KafkaProducer(
            bootstrap_servers=self.kafka_servers,
            value_serializer=lambda x: json.dumps(x).encode('utf-8')
        )
        
        # Cargar configuración
        self.config = self.load_config()
        
        # Inicializar colectores
        self.collectors = []
        self.initialize_collectors()
        
        logger.info("Colector de datos inicializado correctamente")

    def load_config(self):
        """Carga la configuración del colector desde archivo YAML"""
        config_path = "/app/config/collector_config.yaml"
        default_config = {
            'collection_interval': 60,  # segundos
            'prometheus': {
                'enabled': True,
                'endpoints': [
                    {
                        'url': 'http://prometheus:9090',
                        'service_id': 'prometheus',
                        'metrics': ['up', 'memory_usage', 'cpu_usage']
                    }
                ]
            },
            'kubernetes': {
                'enabled': False,
                'incluster': True,
                'node_metrics': True,
                'pod_metrics': True
            },
            'node': {
                'enabled': True,
                'metrics': ['cpu', 'memory', 'disk', 'network']
            },
            'log_files': {
                'enabled': True,
                'paths': [
                    {
                        'path': '/var/log/syslog',
                        'service_id': 'system',
                        'pattern': 'ERROR|FATAL|CRITICAL|Exception|Traceback'
                    }
                ]
            }
        }
        
        # Verificar si existe archivo de configuración
        if not os.path.exists(config_path):
            # Crear directorio de configuración si no existe
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            # Crear configuración por defecto
            with open(config_path, 'w') as f:
                yaml.dump(default_config, f)
            
            logger.info(f"Archivo de configuración creado en {config_path}")
            return default_config
        
        # Cargar configuración existente
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            logger.info("Configuración cargada correctamente")
            return config
        except Exception as e:
            logger.error(f"Error al cargar configuración: {str(e)}")
            logger.info("Usando configuración por defecto")
            return default_config

    def initialize_collectors(self):
        """Inicializa los colectores según la configuración"""
        # Intervalo de recolección
        collection_interval = self.config.get('collection_interval', 60)
        
        # Colector de Prometheus
        if self.config.get('prometheus', {}).get('enabled', False):
            prom_collector = PrometheusCollector(
                self.config['prometheus'],
                self.producer,
                collection_interval
            )
            self.collectors.append(prom_collector)
        
        # Colector de Kubernetes
        if self.config.get('kubernetes', {}).get('enabled', False):
            k8s_collector = KubernetesCollector(
                self.config['kubernetes'],
                self.producer,
                collection_interval
            )
            self.collectors.append(k8s_collector)
        
        # Colector de nodo local
        if self.config.get('node', {}).get('enabled', False):
            node_collector = NodeCollector(
                self.config['node'],
                self.producer,
                collection_interval
            )
            self.collectors.append(node_collector)
        
        # Colector de logs
        if self.config.get('log_files', {}).get('enabled', False):
            log_collector = LogCollector(
                self.config['log_files'],
                self.producer,
                collection_interval
            )
            self.collectors.append(log_collector)
        
        logger.info(f"Se inicializaron {len(self.collectors)} colectores")

    def run(self):
        """Ejecuta los colectores en hilos separados"""
        threads = []
        
        # Iniciar cada colector en un hilo
        for collector in self.collectors:
            thread = threading.Thread(target=collector.collect_metrics)
            thread.daemon = True
            thread.start()
            threads.append(thread)
            
            logger.info(f"Iniciado colector: {collector.__class__.__name__}")
        
        logger.info("Todos los colectores iniciados")
        
        # Mantener el proceso principal vivo
        try:
            while True:
                time.sleep(10)
                # Verificar que todos los hilos estén vivos
                for i, thread in enumerate(threads):
                    if not thread.is_alive():
                        logger.warning(f"Colector {self.collectors[i].__class__.__name__} detenido, reiniciando...")
                        thread = threading.Thread(target=self.collectors[i].collect_metrics)
                        thread.daemon = True
                        thread.start()
                        threads[i] = thread
        except KeyboardInterrupt:
            logger.info("Colector de datos detenido por el usuario")
        except Exception as e:
            logger.error(f"Error en el colector de datos: {str(e)}")


class PrometheusCollector:
    def __init__(self, config, producer, interval):
        self.config = config
        self.producer = producer
        self.interval = interval
        self.endpoints = config.get('endpoints', [])
        logger.info(f"Colector Prometheus inicializado con {len(self.endpoints)} endpoints")

    def collect_metrics(self):
        """Recolecta métricas de Prometheus"""
        while True:
            try:
                for endpoint in self.endpoints:
                    url = endpoint.get('url')
                    service_id = endpoint.get('service_id', 'prometheus')
                    metrics_filter = endpoint.get('metrics', [])
                    
                    # Obtener métricas de prometheus
                    metrics = self.fetch_prometheus_metrics(url, metrics_filter)
                    
                    if metrics:
                        # Añadir metadatos
                        metrics['service_id'] = service_id
                        metrics['collector_type'] = 'prometheus'
                        metrics['timestamp'] = datetime.now().isoformat()
                        
                        # Enviar a Kafka
                        self.producer.send('raw_metrics', metrics)
                        logger.debug(f"Métricas de Prometheus enviadas para {service_id}")
                    
            except Exception as e:
                logger.error(f"Error en colector Prometheus: {str(e)}")
            
            # Esperar para la próxima recolección
            time.sleep(self.interval)

    def fetch_prometheus_metrics(self, url, metrics_filter=None):
        """Obtiene métricas de un endpoint de Prometheus"""
        try:
            # Llamar a la API de Prometheus
            response = requests.get(f"{url}/api/v1/query", params={'query': 'up'})
            if response.status_code != 200:
                logger.warning(f"Error al obtener métricas de {url}: {response.status_code}")
                return None
            
            # También obtener otras métricas específicas
            metrics = {}
            
            # Si no hay filtro, usar algunas métricas comunes
            if not metrics_filter:
                metrics_filter = ['up', 'go_goroutines', 'process_cpu_seconds_total', 'process_resident_memory_bytes']
            
            # Obtener cada métrica
            for metric_name in metrics_filter:
                try:
                    metric_response = requests.get(f"{url}/api/v1/query", params={'query': metric_name})
                    if metric_response.status_code == 200:
                        result = metric_response.json()
                        if 'data' in result and 'result' in result['data']:
                            for item in result['data']['result']:
                                # Extraer etiquetas para identificar la instancia/servicio
                                labels = item.get('metric', {})
                                instance = labels.get('instance', 'unknown')
                                job = labels.get('job', 'unknown')
                                
                                # Crear clave única para esta métrica + instancia
                                metric_key = f"{metric_name}_{instance}".replace('.', '_').replace(':', '_')
                                
                                # Extraer valor
                                if 'value' in item:
                                    try:
                                        value = float(item['value'][1])
                                        metrics[metric_key] = value
                                    except (ValueError, TypeError):
                                        # Si no es un número, ignorar
                                        pass
                except Exception as e:
                    logger.warning(f"Error al obtener métrica {metric_name}: {str(e)}")
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error al obtener métricas de Prometheus: {str(e)}")
            return None


class KubernetesCollector:
    def __init__(self, config, producer, interval):
        self.config = config
        self.producer = producer
        self.interval = interval
        self.incluster = config.get('incluster', True)
        self.node_metrics = config.get('node_metrics', True)
        self.pod_metrics = config.get('pod_metrics', True)
        
        # Intentar inicializar cliente Kubernetes
        try:
            if self.incluster:
                # Configuración para ejecutar dentro de un clúster
                config.load_incluster_config()
            else:
                # Configuración desde ~/.kube/config
                config.load_kube_config()
            
            self.core_api = client.CoreV1Api()
            self.initialized = True
            logger.info("Cliente Kubernetes inicializado correctamente")
            
        except Exception as e:
            self.initialized = False
            logger.error(f"Error al inicializar cliente Kubernetes: {str(e)}")

    def collect_metrics(self):
        """Recolecta métricas de Kubernetes"""
        if not self.initialized:
            logger.warning("Colector Kubernetes no inicializado, no se recolectarán métricas")
            return
        
        while True:
            try:
                # Recolectar métricas de nodos
                if self.node_metrics:
                    nodes = self.core_api.list_node()
                    for node in nodes.items:
                        node_metrics = self.collect_node_metrics(node)
                        if node_metrics:
                            # Añadir metadatos
                            node_metrics['service_id'] = f"k8s_node_{node.metadata.name}"
                            node_metrics['collector_type'] = 'kubernetes'
                            node_metrics['timestamp'] = datetime.now().isoformat()
                            
                            # Enviar a Kafka
                            self.producer.send('raw_metrics', node_metrics)
                
                # Recolectar métricas de pods
                if self.pod_metrics:
                    pods = self.core_api.list_pod_for_all_namespaces()
                    for pod in pods.items:
                        pod_metrics = self.collect_pod_metrics(pod)
                        if pod_metrics:
                            # Añadir metadatos
                            pod_metrics['service_id'] = f"k8s_pod_{pod.metadata.namespace}_{pod.metadata.name}"
                            pod_metrics['collector_type'] = 'kubernetes'
                            pod_metrics['timestamp'] = datetime.now().isoformat()
                            
                            # Enviar a Kafka
                            self.producer.send('raw_metrics', pod_metrics)
                
            except Exception as e:
                logger.error(f"Error en colector Kubernetes: {str(e)}")
            
            # Esperar para la próxima recolección
            time.sleep(self.interval)

    def collect_node_metrics(self, node):
        """Recolecta métricas de un nodo Kubernetes"""
        try:
            node_name = node.metadata.name
            node_status = node.status
            
            # Extraer información de la capacidad y asignación
            capacity = node_status.capacity
            allocatable = node_status.allocatable
            
            # Convertir recursos a valores numéricos
            metrics = {
                'node_name': node_name,
                'cpu_capacity': self.parse_k8s_resource(capacity.get('cpu', '0')),
                'memory_capacity_bytes': self.parse_k8s_resource(capacity.get('memory', '0Ki')),
                'pods_capacity': int(capacity.get('pods', '0')),
                'cpu_allocatable': self.parse_k8s_resource(allocatable.get('cpu', '0')),
                'memory_allocatable_bytes': self.parse_k8s_resource(allocatable.get('memory', '0Ki')),
                'pods_allocatable': int(allocatable.get('pods', '0'))
            }
            
            # Extraer condiciones del nodo
            for condition in node_status.conditions:
                condition_type = condition.type
                condition_status = 1 if condition.status == 'True' else 0
                metrics[f"condition_{condition_type.lower()}"] = condition_status
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error al recolectar métricas de nodo {node.metadata.name}: {str(e)}")
            return None

    def collect_pod_metrics(self, pod):
        """Recolecta métricas de un pod Kubernetes"""
        try:
            pod_name = pod.metadata.name
            pod_namespace = pod.metadata.namespace
            pod_status = pod.status
            
            # Información básica
            metrics = {
                'pod_name': pod_name,
                'namespace': pod_namespace,
                'phase': pod_status.phase,
                'host_ip': pod_status.host_ip if pod_status.host_ip else '',
                'pod_ip': pod_status.pod_ip if pod_status.pod_ip else '',
                'start_time': pod_status.start_time.isoformat() if pod_status.start_time else '',
                'container_count': len(pod.spec.containers),
                'restart_count': 0,
                'ready_containers': 0
            }
            
            # Contar contenedores ready y reinicios
            if pod_status.container_statuses:
                for container_status in pod_status.container_statuses:
                    metrics['restart_count'] += container_status.restart_count
                    if container_status.ready:
                        metrics['ready_containers'] += 1
            
            # Calcular métricas de salud
            metrics['health_ratio'] = metrics['ready_containers'] / metrics['container_count'] if metrics['container_count'] > 0 else 0
            metrics['is_healthy'] = 1 if metrics['health_ratio'] == 1 else 0
            
            return metrics
        
        except Exception as e:
            logger.error(f"Error al recolectar métricas de pod {pod.metadata.name}: {str(e)}")
            return None

    def parse_k8s_resource(self, resource_str):
        """Convierte cadenas de recursos de Kubernetes a valores numéricos"""
        try:
            # Convertir CPU (formato como '100m' o '2')
            if resource_str.endswith('m'):
                return float(resource_str[:-1]) / 1000
            
            # Convertir memoria (formato como '100Ki', '1Gi')
            if resource_str.endswith('Ki'):
                return int(resource_str[:-2]) * 1024
            elif resource_str.endswith('Mi'):
                return int(resource_str[:-2]) * 1024 * 1024
            elif resource_str.endswith('Gi'):
                return int(resource_str[:-2]) * 1024 * 1024 * 1024
            elif resource_str.endswith('Ti'):
                return int(resource_str[:-2]) * 1024 * 1024 * 1024 * 1024
            
            # Valor simple
            return float(resource_str)
        
        except Exception:
            return 0


class NodeCollector:
    def __init__(self, config, producer, interval):
        self.config = config
        self.producer = producer
        self.interval = interval
        self.metrics = config.get('metrics', ['cpu', 'memory', 'disk', 'network'])
        self.hostname = socket.gethostname()
        logger.info(f"Colector de nodo inicializado para host: {self.hostname}")

    def collect_metrics(self):
        """Recolecta métricas del nodo local"""
        while True:
            try:
                metrics = {
                    'node_name': self.hostname,
                    'timestamp': datetime.now().isoformat(),
                    'service_id': f"node_{self.hostname}",
                    'collector_type': 'node'
                }
                
                # Métricas de CPU
                if 'cpu' in self.metrics:
                    cpu_metrics = self.collect_cpu_metrics()
                    metrics.update(cpu_metrics)
                
                # Métricas de memoria
                if 'memory' in self.metrics:
                    memory_metrics = self.collect_memory_metrics()
                    metrics.update(memory_metrics)
                
                # Métricas de disco
                if 'disk' in self.metrics:
                    disk_metrics = self.collect_disk_metrics()
                    metrics.update(disk_metrics)
                
                # Métricas de red
                if 'network' in self.metrics:
                    network_metrics = self.collect_network_metrics()
                    metrics.update(network_metrics)
                
                # Enviar a Kafka
                self.producer.send('raw_metrics', metrics)
                logger.debug(f"Métricas de nodo enviadas para {self.hostname}")
                
            except Exception as e:
                logger.error(f"Error en colector de nodo: {str(e)}")
            
            # Esperar para la próxima recolección
            time.sleep(self.interval)

    def collect_cpu_metrics(self):
        """Recolecta métricas de CPU"""
        try:
            cpu_times = psutil.cpu_times_percent(interval=1)
            cpu_count = psutil.cpu_count()
            cpu_percent = psutil.cpu_percent(interval=1)
            load_avg = psutil.getloadavg()
            
            metrics = {
                'cpu_count': cpu_count,
                'cpu_percent': cpu_percent,
                'cpu_user': cpu_times.user,
                'cpu_system': cpu_times.system,
                'cpu_idle': cpu_times.idle,
                'load_avg_1min': load_avg[0],
                'load_avg_5min': load_avg[1],
                'load_avg_15min': load_avg[2]
            }
            
            return metrics
        except Exception as e:
            logger.error(f"Error al recolectar métricas de CPU: {str(e)}")
            return {}

    def collect_memory_metrics(self):
        """Recolecta métricas de memoria"""
        try:
            virtual_memory = psutil.virtual_memory()
            swap_memory = psutil.swap_memory()
            
            metrics = {
                'memory_total': virtual_memory.total,
                'memory_available': virtual_memory.available,
                'memory_used': virtual_memory.used,
                'memory_percent': virtual_memory.percent,
                'swap_total': swap_memory.total,
                'swap_used': swap_memory.used,
                'swap_percent': swap_memory.percent
            }
            
            return metrics
        except Exception as e:
            logger.error(f"Error al recolectar métricas de memoria: {str(e)}")
            return {}

    def collect_disk_metrics(self):
        """Recolecta métricas de disco"""
        try:
            disk_metrics = {}
            
            # Uso de disco por partición
            disk_partitions = psutil.disk_partitions()
            for i, partition in enumerate(disk_partitions):
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    prefix = f"disk_{i}"
                    disk_metrics.update({
                        f"{prefix}_device": partition.device,
                        f"{prefix}_mountpoint": partition.mountpoint,
                        f"{prefix}_total": usage.total,
                        f"{prefix}_used": usage.used,
                        f"{prefix}_free": usage.free,
                        f"{prefix}_percent": usage.percent
                    })
                except:
                    # Algunas particiones pueden no ser accesibles
                    pass
            
            # Estadísticas de I/O
            if hasattr(psutil, 'disk_io_counters'):
                disk_io = psutil.disk_io_counters()
                if disk_io:
                    disk_metrics.update({
                        'disk_io_read_count': disk_io.read_count,
                        'disk_io_write_count': disk_io.write_count,
                        'disk_io_read_bytes': disk_io.read_bytes,
                        'disk_io_write_bytes': disk_io.write_bytes,
                        'disk_io_read_time': disk_io.read_time,
                        'disk_io_write_time': disk_io.write_time
                    })
            
            return disk_metrics
        except Exception as e:
            logger.error(f"Error al recolectar métricas de disco: {str(e)}")
            return {}

    def collect_network_metrics(self):
        """Recolecta métricas de red"""
        try:
            net_metrics = {}
            
            # Estadísticas de red por interfaz
            net_io = psutil.net_io_counters(pernic=True)
            for i, (interface, stats) in enumerate(net_io.items()):
                prefix = f"net_{i}"
                net_metrics.update({
                    f"{prefix}_interface": interface,
                    f"{prefix}_bytes_sent": stats.bytes_sent,
                    f"{prefix}_bytes_recv": stats.bytes_recv,
                    f"{prefix}_packets_sent": stats.packets_sent,
                    f"{prefix}_packets_recv": stats.packets_recv,
                    f"{prefix}_errin": stats.errin,
                    f"{prefix}_errout": stats.errout,
                    f"{prefix}_dropin": stats.dropin,
                    f"{prefix}_dropout": stats.dropout
                })
            
            # Conexiones de red
            connections = psutil.net_connections()
            conn_status = {}
            for conn in connections:
                status = conn.status
                if status in conn_status:
                    conn_status[status] += 1
                else:
                    conn_status[status] = 1
            
            # Añadir contadores por estado
            for status, count in conn_status.items():
                net_metrics[f"connections_{status.lower()}"] = count
            
            return net_metrics
        except Exception as e:
            logger.error(f"Error al recolectar métricas de red: {str(e)}")
            return {}


class LogCollector:
    def __init__(self, config, producer, interval):
        self.config = config
        self.producer = producer
        self.interval = interval
        self.log_paths = config.get('paths', [])
        self.file_positions = {}  # Seguimiento de posición en archivos
        logger.info(f"Colector de logs inicializado con {len(self.log_paths)} archivos de log")

    def collect_metrics(self):
        """Recolecta logs de archivos configurados"""
        while True:
            try:
                for log_config in self.log_paths:
                    path = log_config.get('path')
                    service_id = log_config.get('service_id', 'unknown')
                    pattern = log_config.get('pattern', 'ERROR|FATAL|CRITICAL')
                    
                    # Verificar si el archivo existe
                    if not os.path.exists(path):
                        continue
                    
                    # Leer nuevas líneas
                    new_logs = self.read_new_log_lines(path, pattern)
                    
                    if new_logs:
                        # Procesar cada entrada de log
                        for log_entry in new_logs:
                            log_data = {
                                'timestamp': datetime.now().isoformat(),
                                'service_id': service_id,
                                'collector_type': 'log',
                                'log_file': path,
                                'log_message': log_entry,
                                'log_level': self.detect_log_level(log_entry)
                            }
                            
                            # Enviar a Kafka
                            self.producer.send('logs', log_data)
                        
                        logger.debug(f"Se enviaron {len(new_logs)} logs para {service_id}")
                    
            except Exception as e:
                logger.error(f"Error en colector de logs: {str(e)}")
            
            # Esperar para la próxima recolección
            time.sleep(self.interval)

    def read_new_log_lines(self, file_path, pattern):
        """Lee nuevas líneas de un archivo de log que coincidan con el patrón"""
        try:
            # Obtener tamaño actual del archivo
            current_size = os.path.getsize(file_path)
            
            # Si es la primera vez que accedemos a este archivo
            if file_path not in self.file_positions:
                # Si el archivo es grande, empezar desde el final
                if current_size > 1024 * 1024:  # 1MB
                    self.file_positions[file_path] = current_size
                else:
                    self.file_positions[file_path] = 0
            
            # Si el archivo ha sido truncado o rotado
            if current_size < self.file_positions[file_path]:
                self.file_positions[file_path] = 0
            
            # Si no hay nuevos datos, salir
            if current_size <= self.file_positions[file_path]:
                return []
            
            # Abrir archivo y leer nuevas líneas
            with open(file_path, 'r') as f:
                f.seek(self.file_positions[file_path])
                new_lines = f.readlines()
                self.file_positions[file_path] = f.tell()
            
            # Filtrar líneas que coincidan con el patrón
            pattern_regex = re.compile(pattern)
            matching_lines = [line.strip() for line in new_lines if pattern_regex.search(line)]
            
            return matching_lines
            
        except Exception as e:
            logger.error(f"Error al leer archivo de log {file_path}: {str(e)}")
            return []

    def detect_log_level(self, log_message):
        """Detecta el nivel de log basado en el mensaje"""
        log_message = log_message.upper()
        
        if 'FATAL' in log_message:
            return 'FATAL'
        elif 'CRITICAL' in log_message:
            return 'CRITICAL'
        elif 'ERROR' in log_message:
            return 'ERROR'
        elif 'WARNING' in log_message or 'WARN' in log_message:
            return 'WARNING'
        elif 'INFO' in log_message:
            return 'INFO'
        elif 'DEBUG' in log_message:
            return 'DEBUG'
        else:
            return 'UNKNOWN'


if __name__ == "__main__":
    # Esperar a que Kafka esté disponible
    time.sleep(10)
    
    # Iniciar el colector de datos
    collector = DataCollector()
    collector.run()