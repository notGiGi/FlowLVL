import requests
import time
import json
import logging
import threading
import atexit
import platform
import psutil
import socket
from datetime import datetime

class PredictiveMaintenanceClient:
    """
    Cliente Python para enviar métricas al Sistema de Mantenimiento Predictivo.
    Permite una fácil integración con aplicaciones Python para monitoreo automatizado.
    """
    
    def __init__(self, api_url, api_key, service_id=None, auto_collect=True, metrics_interval=60):
        """
        Inicializa el cliente de monitoreo
        
        Args:
            api_url: URL base del API (ej: 'http://localhost:8000')
            api_key: Clave API para autenticación
            service_id: ID del servicio (opcional, si no se proporciona usa el hostname)
            auto_collect: Si True, recolecta automáticamente métricas del sistema
            metrics_interval: Intervalo en segundos para recolección automática
        """
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.service_id = service_id or socket.gethostname()
        self.auto_collect = auto_collect
        self.metrics_interval = metrics_interval
        
        # Eventos para control
        self.running = True
        self.collector_thread = None
        
        # Registro de métricas enviadas
        self.last_metrics = None
        self.metrics_count = 0
        
        # Configurar logging
        self.logger = logging.getLogger('predictive_client')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Iniciar colector automático si está habilitado
        if auto_collect:
            self._start_collector()
            atexit.register(self.stop)
            self.logger.info(f"Cliente inicializado para servicio '{service_id}' con recolección automática cada {metrics_interval}s")
        else:
            self.logger.info(f"Cliente inicializado para servicio '{service_id}' en modo manual")
    
    def _start_collector(self):
        """Inicia thread de recolección automática"""
        self.collector_thread = threading.Thread(target=self._collect_loop)
        self.collector_thread.daemon = True
        self.collector_thread.start()
    
    def _collect_loop(self):
        """Bucle de recolección automática de métricas"""
        while self.running:
            try:
                # Recolectar métricas del sistema
                metrics = self.collect_system_metrics()
                
                # Enviar métricas
                self.send_metrics(metrics)
                
                # Esperar para siguiente recolección
                time.sleep(self.metrics_interval)
                
            except Exception as e:
                self.logger.error(f"Error en recolección automática: {str(e)}")
                time.sleep(5)  # Esperar antes de reintentar
    
    def collect_system_metrics(self):
        """
        Recolecta métricas del sistema actual
        
        Returns:
            dict: Métricas recolectadas
        """
        metrics = {}
        
        try:
            # CPU
            metrics['cpu_usage'] = psutil.cpu_percent(interval=1)
            metrics['cpu_count'] = psutil.cpu_count()
            
            # Memoria
            memory = psutil.virtual_memory()
            metrics['memory_usage'] = memory.percent
            metrics['memory_available'] = memory.available / (1024 * 1024)  # MB
            metrics['memory_total'] = memory.total / (1024 * 1024)  # MB
            
            # Disco
            disk = psutil.disk_usage('/')
            metrics['disk_usage'] = disk.percent
            metrics['disk_free'] = disk.free / (1024 * 1024 * 1024)  # GB
            
            # Red (conexiones)
            try:
                connections = len(psutil.net_connections())
                metrics['network_connections'] = connections
            except Exception:
                # Puede requerir permisos elevados en algunos sistemas
                pass
            
            # Información de carga (Linux/macOS)
            if platform.system() != 'Windows':
                load_avg = [x / psutil.cpu_count() * 100 for x in psutil.getloadavg()]
                metrics['load_average_1min'] = load_avg[0]
                metrics['load_average_5min'] = load_avg[1]
                metrics['load_average_15min'] = load_avg[2]
            
            # Procesos
            metrics['process_count'] = len(psutil.pids())
            
            # Para la aplicación actual
            process = psutil.Process()
            metrics['app_cpu_usage'] = process.cpu_percent(interval=0.1)
            metrics['app_memory_usage'] = process.memory_percent()
            metrics['app_threads'] = process.num_threads()
            
            self.logger.debug(f"Métricas recolectadas: {len(metrics)} valores")
            
        except Exception as e:
            self.logger.error(f"Error al recolectar métricas: {str(e)}")
        
        return metrics
    
    def send_metrics(self, metrics, custom_timestamp=None):
        """
        Envía métricas al servidor
        
        Args:
            metrics: Dict con métricas
            custom_timestamp: Timestamp personalizado (opcional)
            
        Returns:
            bool: True si se enviaron correctamente
        """
        if not metrics:
            self.logger.warning("No hay métricas para enviar")
            return False
        
        # Preparar payload
        payload = {
            "service_id": self.service_id,
            "metrics": metrics
        }
        
        if custom_timestamp:
            payload["timestamp"] = custom_timestamp
        
        # Enviar solicitud
        try:
            response = requests.post(
                f"{self.api_url}/submit-metrics",
                json=payload,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                self.last_metrics = metrics
                self.metrics_count += 1
                self.logger.debug(f"Métricas enviadas correctamente: {response.status_code}")
                return True
            else:
                self.logger.error(f"Error al enviar métricas: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            self.logger.error(f"Excepción al enviar métricas: {str(e)}")
            return False
    
    def check_anomalies(self, metrics=None):
        """
        Solicita detección de anomalías para métricas específicas
        
        Args:
            metrics: Dict con métricas (opcional, usa last_metrics si no se proporciona)
            
        Returns:
            dict: Resultado de la detección o None si hay error
        """
        if not metrics and not self.last_metrics:
            self.logger.warning("No hay métricas para verificar anomalías")
            return None
        
        metrics_to_check = metrics or self.last_metrics
        
        # Preparar payload
        payload = {
            "service_id": self.service_id,
            "metrics": metrics_to_check
        }
        
        # Enviar solicitud
        try:
            response = requests.post(
                f"{self.api_url}/detect-anomaly",
                json=payload,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                result = response.json()
                
                # Log si hay anomalía
                if result.get("is_anomaly", False):
                    self.logger.warning(
                        f"Anomalía detectada: Score={result.get('anomaly_score', 0):.3f}, "
                        f"Tipo={result.get('details', {}).get('anomaly_type', 'unknown')}"
                    )
                else:
                    self.logger.debug(f"No se detectaron anomalías (Score: {result.get('anomaly_score', 0):.3f})")
                
                return result
            else:
                self.logger.error(f"Error en detección de anomalías: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Excepción en detección de anomalías: {str(e)}")
            return None
    
    def get_service_status(self):
        """
        Obtiene estado actual del servicio
        
        Returns:
            dict: Estado del servicio o None si hay error
        """
        try:
            response = requests.get(
                f"{self.api_url}/service-status/{self.service_id}",
                headers={"X-API-Key": self.api_key},
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                return response.json()
            else:
                self.logger.error(f"Error al obtener estado: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Excepción al obtener estado: {str(e)}")
            return None
    
    def get_recommended_actions(self):
        """
        Obtiene acciones recomendadas para el servicio
        
        Returns:
            list: Lista de acciones recomendadas o None si hay error
        """
        try:
            response = requests.get(
                f"{self.api_url}/action-history/{self.service_id}",
                headers={"X-API-Key": self.api_key},
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                return response.json().get('actions', [])
            else:
                self.logger.error(f"Error al obtener acciones: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Excepción al obtener acciones: {str(e)}")
            return None
    
    def execute_action(self, action_id, parameters=None):
        """
        Solicita ejecución de una acción específica
        
        Args:
            action_id: ID de la acción a ejecutar
            parameters: Parámetros adicionales (opcional)
            
        Returns:
            dict: Resultado de la ejecución o None si hay error
        """
        try:
            payload = {
                "service_id": self.service_id,
                "action_id": action_id
            }
            
            if parameters:
                payload["parameters"] = parameters
            
            response = requests.post(
                f"{self.api_url}/execute-action",
                json=payload,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=20  # Timeout más largo para acciones
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                result = response.json()
                self.logger.info(f"Acción {action_id} ejecutada: {result.get('status')}")
                return result
            else:
                self.logger.error(f"Error al ejecutar acción: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Excepción al ejecutar acción: {str(e)}")
            return None
    
    def register_service(self, service_name=None, service_type=None, description=None):
        """
        Registra el servicio en el sistema de mantenimiento predictivo
        
        Args:
            service_name: Nombre del servicio (opcional)
            service_type: Tipo de servicio (opcional)
            description: Descripción del servicio (opcional)
            
        Returns:
            dict: Resultado del registro o None si hay error
        """
        try:
            payload = {
                "service_id": self.service_id,
                "service_name": service_name or self.service_id,
                "service_type": service_type or "generic_service",
                "description": description or f"Servicio {self.service_id}"
            }
            
            response = requests.post(
                f"{self.api_url}/register-service",
                json=payload,
                headers={
                    "X-API-Key": self.api_key,
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                result = response.json()
                self.logger.info(f"Servicio registrado correctamente: {result.get('status')}")
                return result
            else:
                self.logger.error(f"Error al registrar servicio: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.logger.error(f"Excepción al registrar servicio: {str(e)}")
            return None
    
    def stop(self):
        """Detiene el cliente y libera recursos"""
        self.running = False
        if self.collector_thread and self.collector_thread.is_alive():
            self.collector_thread.join(timeout=2)
        self.logger.info("Cliente detenido")


# Ejemplo de uso
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Crear cliente
    client = PredictiveMaintenanceClient(
        api_url="http://localhost:8000",
        api_key="test_key",
        service_id="example-service",
        auto_collect=True,
        metrics_interval=30
    )
    
    # Registrar servicio
    client.register_service(
        service_name="Servicio de Ejemplo",
        service_type="web_service",
        description="Servicio de ejemplo para demostración"
    )
    
    # Mantener ejecución
    try:
        while True:
            # Verificar si hay anomalías cada 2 minutos
            time.sleep(120)
            client.check_anomalies()
            
            # Obtener estado del servicio y acciones recomendadas
            status = client.get_service_status()
            if status and status.get('status') != 'normal':
                actions = client.get_recommended_actions()
                if actions:
                    print(f"Acciones recomendadas: {len(actions)}")
    
    except KeyboardInterrupt:
        client.stop()