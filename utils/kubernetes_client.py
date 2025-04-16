import kubernetes
import logging
from kubernetes import client, config
import time
import os
from datetime import datetime, timedelta
import json
import yaml
import re
import base64
from utils.retry import retry_with_backoff

# Configuración de logging
logger = logging.getLogger('kubernetes_client')

class KubernetesClient:
    """
    Cliente para interactuar con el clúster Kubernetes, abstraer operaciones
    comunes y proporcionar seguridad y validación.
    """
    
    def __init__(self, config_file=None, context=None, in_cluster=None):
        """
        Inicializa el cliente Kubernetes
        
        Args:
            config_file: Ruta al archivo de configuración (opcional)
            context: Contexto a utilizar (opcional)
            in_cluster: Si True, carga la configuración dentro del clúster
        """
        self.config_file = config_file
        self.context = context
        
        # Determinar si estamos dentro de un clúster
        if in_cluster is None:
            # Autodetectar si estamos en un pod
            in_cluster = os.path.exists('/var/run/secrets/kubernetes.io/serviceaccount/token')
        
        try:
            # Cargar configuración según el entorno
            if in_cluster:
                # Dentro del clúster
                config.load_incluster_config()
                logger.info("Configuración cargada desde incluster")
            elif self.config_file:
                # Configuración explícita
                config.load_kube_config(config_file=self.config_file, context=self.context)
                logger.info(f"Configuración cargada desde {self.config_file}")
            else:
                # Configuración por defecto
                config.load_kube_config(context=self.context)
                logger.info("Configuración cargada desde ~/.kube/config")
            
            # Inicializar clientes
            self.core_api = client.CoreV1Api()
            self.apps_api = client.AppsV1Api()
            self.batch_api = client.BatchV1Api()
            self.custom_api = client.CustomObjectsApi()
            self.autoscaling_api = client.AutoscalingV1Api()
            
            # Estado de conexión
            self.connected = True
            
            # Lista de operaciones permitidas
            self.allowed_operations = {
                'get_pod_metrics', 'restart_deployment', 'scale_deployment',
                'execute_command', 'get_logs', 'get_pod_info', 'get_node_metrics',
                'list_pods', 'describe_deployment', 'check_pod_resource_usage'
            }
            
            # Lista de operaciones peligrosas que requieren validación adicional
            self.dangerous_operations = {
                'delete_pod', 'delete_deployment', 'delete_service',
                'patch_deployment', 'apply_yaml', 'update_cronjob'
            }
            
            # Lista de servicios/namespaces protegidos
            self.protected_resources = {
                'kube-system', 'kube-public', 'kube-node-lease',
                'prometheus', 'grafana', 'cluster-autoscaler',
                'cert-manager', 'istio-system', 'monitoring'
            }
            
            # Verificar conexión
            self.check_connection()
            
        except Exception as e:
            logger.error(f"Error al inicializar cliente Kubernetes: {str(e)}")
            self.connected = False
    
    def check_connection(self):
        """Verifica conexión con el clúster"""
        try:
            self.core_api.list_namespace(limit=1)
            logger.info("Conexión exitosa al clúster Kubernetes")
            return True
        except Exception as e:
            logger.error(f"Error de conexión al clúster Kubernetes: {str(e)}")
            self.connected = False
            return False
    
    def is_protected_resource(self, namespace, name=None):
        """
        Verifica si un recurso está protegido
        
        Args:
            namespace: Namespace del recurso
            name: Nombre del recurso (opcional)
        
        Returns:
            bool: True si está protegido
        """
        # Verificar namespace protegido
        if namespace in self.protected_resources:
            return True
        
        # Verificar nombre de recurso protegido
        if name and name in self.protected_resources:
            return True
            
        # Verificar patrones de protección
        for protected in self.protected_resources:
            if '*' in protected:
                pattern = protected.replace('*', '.*')
                if name and re.match(pattern, name):
                    return True
                if re.match(pattern, namespace):
                    return True
        
        return False
    
    def validate_operation(self, operation, namespace, name=None, raise_exception=True):
        """
        Valida si una operación es permitida en un recurso
        
        Args:
            operation: Nombre de la operación
            namespace: Namespace del recurso
            name: Nombre del recurso (opcional)
            raise_exception: Si True, lanza excepción si no es válido
            
        Returns:
            bool: True si la operación es válida
        """
        # Verificar si la operación es permitida
        if operation not in self.allowed_operations and operation not in self.dangerous_operations:
            message = f"Operación {operation} no permitida"
            logger.warning(message)
            if raise_exception:
                raise ValueError(message)
            return False
        
        # Verificar si es operación peligrosa en recurso protegido
        if operation in self.dangerous_operations and self.is_protected_resource(namespace, name):
            message = f"Operación {operation} no permitida en recurso protegido {namespace}/{name}"
            logger.warning(message)
            if raise_exception:
                raise ValueError(message)
            return False
        
        return True
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def get_pod_metrics(self, namespace, pod_name=None, label_selector=None):
        """
        Obtiene métricas de CPU y memoria para pods
        
        Args:
            namespace: Namespace de los pods
            pod_name: Nombre del pod (opcional)
            label_selector: Selector de etiquetas (opcional)
            
        Returns:
            Lista de métricas por pod
        """
        try:
            self.validate_operation('get_pod_metrics', namespace, pod_name)
            
            # Endpoint de la API de métricas
            metrics_api = '/apis/metrics.k8s.io/v1beta1/namespaces/{namespace}/pods'
            
            # Si se proporciona nombre de pod específico
            if pod_name:
                metrics_api += f'/{pod_name}'
                response = self.custom_api.get_cluster_custom_object(
                    'metrics.k8s.io', 'v1beta1',
                    f'namespaces/{namespace}/pods/{pod_name}'
                )
                return self._parse_pod_metrics(response)
            
            # Lista de pods por etiqueta o todos
            params = {}
            if label_selector:
                params['labelSelector'] = label_selector
            
            response = self.custom_api.list_namespaced_custom_object(
                'metrics.k8s.io', 'v1beta1',
                namespace, 'pods',
                **params
            )
            
            return self._parse_pod_metrics_list(response)
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al obtener métricas de pods: {str(e)}")
            return None
    
    def _parse_pod_metrics(self, pod_metrics):
        """Parsea métricas de un solo pod"""
        if not pod_metrics or 'containers' not in pod_metrics:
            return None
        
        result = {
            'name': pod_metrics.get('metadata', {}).get('name', 'unknown'),
            'namespace': pod_metrics.get('metadata', {}).get('namespace', 'unknown'),
            'timestamp': pod_metrics.get('timestamp', datetime.now().isoformat()),
            'containers': {}
        }
        
        # Métricas totales del pod
        total_cpu_usage = 0
        total_memory_usage = 0
        
        # Recorrer contenedores
        for container in pod_metrics.get('containers', []):
            container_name = container.get('name', 'unknown')
            
            # Extraer CPU (valor en formato "125m" - milicores)
            cpu_str = container.get('usage', {}).get('cpu', '0')
            if 'm' in cpu_str:
                cpu_millicores = int(cpu_str.replace('m', ''))
                cpu_cores = cpu_millicores / 1000
            elif cpu_str.endswith('n'):
                cpu_nanocores = int(cpu_str.replace('n', ''))
                cpu_cores = cpu_nanocores / 1000000000
            else:
                # Asumir que es en cores
                cpu_cores = float(cpu_str)
            
            # Extraer memoria (valor en formato "128974Ki" - KiB)
            memory_str = container.get('usage', {}).get('memory', '0')
            memory_bytes = self._parse_memory_value(memory_str)
            memory_mb = memory_bytes / (1024 * 1024)
            
            # Añadir al total
            total_cpu_usage += cpu_cores
            total_memory_usage += memory_bytes
            
            # Almacenar métricas del contenedor
            result['containers'][container_name] = {
                'cpu_usage_cores': cpu_cores,
                'memory_usage_bytes': memory_bytes,
                'memory_usage_mb': memory_mb
            }
        
        # Añadir totales
        result['cpu_usage_cores'] = total_cpu_usage
        result['memory_usage_bytes'] = total_memory_usage
        result['memory_usage_mb'] = total_memory_usage / (1024 * 1024)
        
        return result
    
    def _parse_pod_metrics_list(self, pod_metrics_list):
        """Parsea métricas de una lista de pods"""
        if not pod_metrics_list or 'items' not in pod_metrics_list:
            return []
        
        result = []
        for pod_metrics in pod_metrics_list.get('items', []):
            parsed = self._parse_pod_metrics(pod_metrics)
            if parsed:
                result.append(parsed)
        
        return result
    
    def _parse_memory_value(self, memory_str):
        """
        Convierte string de memoria a bytes
        
        Args:
            memory_str: String de memoria (ej: "128974Ki")
            
        Returns:
            int: Valor en bytes
        """
        if not memory_str:
            return 0
        
        memory_str = str(memory_str).strip()
        
        # Unidades de memoria y sus factores
        units = {
            'Ki': 1024,
            'Mi': 1024**2,
            'Gi': 1024**3,
            'Ti': 1024**4,
            'Pi': 1024**5,
            'K': 1000,
            'M': 1000**2,
            'G': 1000**3,
            'T': 1000**4,
            'P': 1000**5,
            'k': 1000,
            'm': 1000**2,
            'g': 1000**3,
            't': 1000**4,
            'p': 1000**5,
            'E': 1000**6,
            'Ei': 1024**6
        }
        
        # Buscar unidad
        for unit, factor in units.items():
            if memory_str.endswith(unit):
                value_str = memory_str[:-len(unit)]
                try:
                    value = float(value_str)
                    return int(value * factor)
                except ValueError:
                    return 0
        
        # Sin unidad, asumir bytes
        try:
            return int(float(memory_str))
        except ValueError:
            return 0
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def restart_deployment(self, namespace, deployment_name):
        """
        Reinicia un deployment (rollout restart)
        
        Args:
            namespace: Namespace del deployment
            deployment_name: Nombre del deployment
            
        Returns:
            bool: True si se reinició correctamente
        """
        try:
            self.validate_operation('restart_deployment', namespace, deployment_name)
            
            # Patch para forzar reinicio (cambiando anotación)
            now = datetime.now().isoformat()
            patch = {
                'spec': {
                    'template': {
                        'metadata': {
                            'annotations': {
                                'predictive.maintenance/restartedAt': now
                            }
                        }
                    }
                }
            }
            
            # Aplicar patch
            response = self.apps_api.patch_namespaced_deployment(
                name=deployment_name,
                namespace=namespace,
                body=patch
            )
            
            logger.info(f"Deployment {namespace}/{deployment_name} reiniciado")
            return True
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al reiniciar deployment {deployment_name}: {str(e)}")
            return False
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def scale_deployment(self, namespace, deployment_name, replicas):
        """
        Escala un deployment a un número específico de réplicas
        
        Args:
            namespace: Namespace del deployment
            deployment_name: Nombre del deployment
            replicas: Número de réplicas
            
        Returns:
            bool: True si se escaló correctamente
        """
        try:
            self.validate_operation('scale_deployment', namespace, deployment_name)
            
            # Verificar número válido de réplicas
            if replicas < 0:
                logger.error("El número de réplicas no puede ser negativo")
                return False
            
            # Obtener actual scale object
            scale = self.apps_api.read_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace
            )
            
            # Actualizar número de réplicas
            scale.spec.replicas = replicas
            
            # Aplicar cambio
            response = self.apps_api.replace_namespaced_deployment_scale(
                name=deployment_name,
                namespace=namespace,
                body=scale
            )
            
            logger.info(f"Deployment {namespace}/{deployment_name} escalado a {replicas} réplicas")
            return True
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al escalar deployment {deployment_name}: {str(e)}")
            return False
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def execute_command(self, namespace, pod_name, container_name, command, timeout_seconds=60):
        """
        Ejecuta un comando en un contenedor
        
        Args:
            namespace: Namespace del pod
            pod_name: Nombre del pod
            container_name: Nombre del contenedor
            command: Comando a ejecutar (lista de strings)
            timeout_seconds: Timeout en segundos
            
        Returns:
            Dict con stdout, stderr y código de salida
        """
        try:
            self.validate_operation('execute_command', namespace, pod_name)
            
            # Asegurar que comando es lista
            if isinstance(command, str):
                command = ["/bin/sh", "-c", command]
            
            # Ejecutar comando
            exec_response = kubernetes.stream.stream(
                self.core_api.connect_get_namespaced_pod_exec,
                name=pod_name,
                namespace=namespace,
                container=container_name,
                command=command,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
                _preload_content=False
            )
            
            # Esperar resultado con timeout
            result = {
                'stdout': '',
                'stderr': '',
                'exit_code': None
            }
            
            start_time = time.time()
            while exec_response.is_open() and (time.time() - start_time) < timeout_seconds:
                if exec_response.peek_stdout():
                    result['stdout'] += exec_response.read_stdout()
                if exec_response.peek_stderr():
                    result['stderr'] += exec_response.read_stderr()
                time.sleep(0.1)
            
            # Cerrar conexión
            if exec_response.is_open():
                exec_response.close()
            
            # Obtener código de salida
            status = json.loads(exec_response.read_channel(kubernetes.stream.ws_client.ERROR_CHANNEL))
            result['exit_code'] = status.get('status', 'Unknown')
            
            logger.info(f"Comando ejecutado en {namespace}/{pod_name}/{container_name}")
            return result
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al ejecutar comando en {pod_name}: {str(e)}")
            return {
                'stdout': '',
                'stderr': str(e),
                'exit_code': 1
            }
        except Exception as e:
            logger.error(f"Error general al ejecutar comando: {str(e)}")
            return {
                'stdout': '',
                'stderr': str(e),
                'exit_code': 1
            }
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def get_logs(self, namespace, pod_name, container_name=None, tail_lines=100, since_seconds=None):
        """
        Obtiene logs de un pod
        
        Args:
            namespace: Namespace del pod
            pod_name: Nombre del pod
            container_name: Nombre del contenedor (opcional)
            tail_lines: Número de líneas a obtener (desde el final)
            since_seconds: Segundos desde los que obtener logs
            
        Returns:
            str: Logs del pod
        """
        try:
            self.validate_operation('get_logs', namespace, pod_name)
            
            # Parámetros para obtener logs
            params = {
                'name': pod_name,
                'namespace': namespace,
                'tail_lines': tail_lines
            }
            
            if container_name:
                params['container'] = container_name
            
            if since_seconds:
                params['since_seconds'] = since_seconds
            
            # Obtener logs
            logs = self.core_api.read_namespaced_pod_log(**params)
            
            return logs
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al obtener logs de {pod_name}: {str(e)}")
            return f"Error: {str(e)}"
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def get_pod_info(self, namespace, pod_name):
        """
        Obtiene información detallada de un pod
        
        Args:
            namespace: Namespace del pod
            pod_name: Nombre del pod
            
        Returns:
            Dict con información del pod
        """
        try:
            self.validate_operation('get_pod_info', namespace, pod_name)
            
            # Obtener pod
            pod = self.core_api.read_namespaced_pod(
                name=pod_name,
                namespace=namespace
            )
            
            # Parsear información relevante
            result = {
                'name': pod.metadata.name,
                'namespace': pod.metadata.namespace,
                'node': pod.spec.node_name,
                'ip': pod.status.pod_ip,
                'host_ip': pod.status.host_ip,
                'phase': pod.status.phase,
                'created': pod.metadata.creation_timestamp.isoformat(),
                'containers': []
            }
            
            # Información de contenedores
            for container in pod.spec.containers:
                container_info = {
                    'name': container.name,
                    'image': container.image,
                    'resources': {}
                }
                
                # Recursos solicitados y límites
                if container.resources:
                    if container.resources.requests:
                        container_info['resources']['requests'] = {
                            'cpu': container.resources.requests.get('cpu', ''),
                            'memory': container.resources.requests.get('memory', '')
                        }
                    if container.resources.limits:
                        container_info['resources']['limits'] = {
                            'cpu': container.resources.limits.get('cpu', ''),
                            'memory': container.resources.limits.get('memory', '')
                        }
                
                # Puertos
                if container.ports:
                    container_info['ports'] = [
                        {'name': port.name, 'container_port': port.container_port}
                        for port in container.ports
                    ]
                
                result['containers'].append(container_info)
            
            # Estado de contenedores
            if pod.status.container_statuses:
                for status in pod.status.container_statuses:
                    for container in result['containers']:
                        if container['name'] == status.name:
                            container['ready'] = status.ready
                            container['restart_count'] = status.restart_count
                            
                            # Estado actual
                            container_state = {}
                            if status.state.running:
                                container_state['state'] = 'running'
                                container_state['started_at'] = status.state.running.started_at.isoformat()
                            elif status.state.waiting:
                                container_state['state'] = 'waiting'
                                container_state['reason'] = status.state.waiting.reason
                                container_state['message'] = status.state.waiting.message
                            elif status.state.terminated:
                                container_state['state'] = 'terminated'
                                container_state['reason'] = status.state.terminated.reason
                                container_state['exit_code'] = status.state.terminated.exit_code
                            
                            container['state'] = container_state
            
            return result
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al obtener información del pod {pod_name}: {str(e)}")
            return None
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def check_pod_resource_usage(self, namespace, pod_name):
        """
        Verifica el uso de recursos de un pod comparado con sus límites
        
        Args:
            namespace: Namespace del pod
            pod_name: Nombre del pod
            
        Returns:
            Dict con uso de recursos y porcentajes
        """
        try:
            # Obtener información del pod
            pod_info = self.get_pod_info(namespace, pod_name)
            if not pod_info:
                return None
            
            # Obtener métricas
            pod_metrics = self.get_pod_metrics(namespace, pod_name)
            if not pod_metrics:
                return None
            
            # Combinar información
            result = {
                'name': pod_name,
                'namespace': namespace,
                'containers': {}
            }
            
            for container_info in pod_info['containers']:
                container_name = container_info['name']
                
                # Obtener límites
                cpu_limit = None
                memory_limit = None
                
                if 'resources' in container_info and 'limits' in container_info['resources']:
                    limits = container_info['resources']['limits']
                    if 'cpu' in limits:
                        cpu_str = limits['cpu']
                        if cpu_str.endswith('m'):
                            cpu_limit = int(cpu_str[:-1]) / 1000  # millicores to cores
                        else:
                            try:
                                cpu_limit = float(cpu_str)
                            except ValueError:
                                cpu_limit = None
                    
                    if 'memory' in limits:
                        memory_limit_bytes = self._parse_memory_value(limits['memory'])
                        memory_limit = memory_limit_bytes / (1024 * 1024)  # bytes to MB
                
                # Obtener uso actual
                cpu_usage = None
                memory_usage = None
                
                if 'containers' in pod_metrics and container_name in pod_metrics['containers']:
                    container_metrics = pod_metrics['containers'][container_name]
                    cpu_usage = container_metrics.get('cpu_usage_cores')
                    memory_usage = container_metrics.get('memory_usage_mb')
                
                # Calcular porcentajes
                cpu_percent = None
                memory_percent = None
                
                if cpu_usage is not None and cpu_limit is not None and cpu_limit > 0:
                    cpu_percent = (cpu_usage / cpu_limit) * 100
                
                if memory_usage is not None and memory_limit is not None and memory_limit > 0:
                    memory_percent = (memory_usage / memory_limit) * 100
                
                # Guardar resultados
                result['containers'][container_name] = {
                    'cpu': {
                        'usage': cpu_usage,
                        'limit': cpu_limit,
                        'percent': cpu_percent
                    },
                    'memory': {
                        'usage': memory_usage,
                        'limit': memory_limit,
                        'percent': memory_percent
                    }
                }
            
            # Calcular totales
            total_cpu_usage = sum(c['cpu']['usage'] for c in result['containers'].values() if c['cpu']['usage'] is not None)
            total_cpu_limit = sum(c['cpu']['limit'] for c in result['containers'].values() if c['cpu']['limit'] is not None)
            total_memory_usage = sum(c['memory']['usage'] for c in result['containers'].values() if c['memory']['usage'] is not None)
            total_memory_limit = sum(c['memory']['limit'] for c in result['containers'].values() if c['memory']['limit'] is not None)
            
            # Calcular porcentajes totales
            total_cpu_percent = None
            total_memory_percent = None
            
            if total_cpu_usage is not None and total_cpu_limit is not None and total_cpu_limit > 0:
                total_cpu_percent = (total_cpu_usage / total_cpu_limit) * 100
            
            if total_memory_usage is not None and total_memory_limit is not None and total_memory_limit > 0:
                total_memory_percent = (total_memory_usage / total_memory_limit) * 100
            
            # Añadir totales
            result['total'] = {
                'cpu': {
                    'usage': total_cpu_usage,
                    'limit': total_cpu_limit,
                    'percent': total_cpu_percent
                },
                'memory': {
                    'usage': total_memory_usage,
                    'limit': total_memory_limit,
                    'percent': total_memory_percent
                }
            }
            
            return result
            
        except Exception as e:
            logger.error(f"Error al verificar uso de recursos del pod {pod_name}: {str(e)}")
            return None
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def describe_deployment(self, namespace, deployment_name):
        """
        Obtiene información detallada de un deployment
        
        Args:
            namespace: Namespace del deployment
            deployment_name: Nombre del deployment
            
        Returns:
            Dict con información del deployment
        """
        try:
            self.validate_operation('describe_deployment', namespace, deployment_name)
            
            # Obtener deployment
            deployment = self.apps_api.read_namespaced_deployment(
                name=deployment_name,
                namespace=namespace
            )
            
            # Obtener seleccionador de pods
            selector = ''
            for k, v in deployment.spec.selector.match_labels.items():
                selector += f"{k}={v},"
            selector = selector.rstrip(',')
            
            # Obtener pods asociados
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                label_selector=selector
            )
            
            # Parsear información
            result = {
                'name': deployment.metadata.name,
                'namespace': deployment.metadata.namespace,
                'replicas': {
                    'desired': deployment.spec.replicas,
                    'available': deployment.status.available_replicas or 0,
                    'ready': deployment.status.ready_replicas or 0,
                    'updated': deployment.status.updated_replicas or 0
                },
                'created': deployment.metadata.creation_timestamp.isoformat(),
                'strategy': deployment.spec.strategy.type,
                'selector': selector,
                'pods': []
            }
            
            # Información de pods
            for pod in pods.items:
                pod_info = {
                    'name': pod.metadata.name,
                    'node': pod.spec.node_name,
                    'phase': pod.status.phase,
                    'ready': all(c.ready for c in pod.status.container_statuses) if pod.status.container_statuses else False,
                    'created': pod.metadata.creation_timestamp.isoformat()
                }
                result['pods'].append(pod_info)
            
            # Obtener métricas de CPU y memoria
            try:
                metrics = self.get_pod_metrics(namespace, label_selector=selector)
                if metrics:
                    # Calcular promedios y totales
                    total_cpu = sum(m.get('cpu_usage_cores', 0) for m in metrics)
                    total_memory = sum(m.get('memory_usage_mb', 0) for m in metrics)
                    avg_cpu = total_cpu / len(metrics) if metrics else 0
                    avg_memory = total_memory / len(metrics) if metrics else 0
                    
                    result['metrics'] = {
                        'total_cpu_cores': total_cpu,
                        'total_memory_mb': total_memory,
                        'avg_cpu_cores': avg_cpu,
                        'avg_memory_mb': avg_memory
                    }
            except Exception as e:
                logger.warning(f"Error al obtener métricas: {str(e)}")
            
            return result
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al describir deployment {deployment_name}: {str(e)}")
            return None
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def list_pods(self, namespace, label_selector=None, field_selector=None):
        """
        Lista pods en un namespace
        
        Args:
            namespace: Namespace
            label_selector: Selector de etiquetas (opcional)
            field_selector: Selector de campos (opcional)
            
        Returns:
            Lista de pods
        """
        try:
            self.validate_operation('list_pods', namespace)
            
            # Parámetros para lista
            params = {}
            if label_selector:
                params['label_selector'] = label_selector
            if field_selector:
                params['field_selector'] = field_selector
            
            # Obtener lista de pods
            pods = self.core_api.list_namespaced_pod(
                namespace=namespace,
                **params
            )
            
            # Convertir a formato más simple
            result = []
            for pod in pods.items:
                pod_info = {
                    'name': pod.metadata.name,
                    'namespace': pod.metadata.namespace,
                    'node': pod.spec.node_name,
                    'ip': pod.status.pod_ip,
                    'phase': pod.status.phase,
                    'created': pod.metadata.creation_timestamp.isoformat()
                }
                
                # Verificar estado de contenedores
                if pod.status.container_statuses:
                    ready_containers = sum(1 for c in pod.status.container_statuses if c.ready)
                    total_containers = len(pod.status.container_statuses)
                    pod_info['ready'] = f"{ready_containers}/{total_containers}"
                    pod_info['restart_count'] = sum(c.restart_count for c in pod.status.container_statuses)
                
                result.append(pod_info)
            
            return result
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al listar pods en {namespace}: {str(e)}")
            return None
    
    @retry_with_backoff(max_retries=3, initial_delay=1)
    def get_node_metrics(self):
        """
        Obtiene métricas de todos los nodos
        
        Returns:
            Dict con métricas por nodo
        """
        try:
            self.validate_operation('get_node_metrics', 'kube-system')
            
            # Obtener lista de nodos
            nodes = self.core_api.list_node()
            
            # Obtener métricas de nodos
            metrics_api = '/apis/metrics.k8s.io/v1beta1/nodes'
            node_metrics = self.custom_api.list_cluster_custom_object(
                'metrics.k8s.io', 'v1beta1', 'nodes'
            )
            
            # Mapear métricas a nodos
            metrics_map = {}
            for metric in node_metrics.get('items', []):
                name = metric.get('metadata', {}).get('name')
                if name:
                    metrics_map[name] = metric.get('usage', {})
            
            # Construir resultado
            result = {}
            for node in nodes.items:
                node_name = node.metadata.name
                
                # Información básica del nodo
                node_info = {
                    'name': node_name,
                    'ready': any(c.status == 'True' for c in node.status.conditions if c.type == 'Ready'),
                    'created': node.metadata.creation_timestamp.isoformat(),
                    'capacity': {},
                    'allocatable': {},
                    'usage': {}
                }
                
                # Capacidad total
                for k, v in node.status.capacity.items():
                    node_info['capacity'][k] = v
                
                # Recursos asignables
                for k, v in node.status.allocatable.items():
                    node_info['allocatable'][k] = v
                
                # Métricas de uso
                if node_name in metrics_map:
                    usage = metrics_map[node_name]
                    
                    # CPU
                    if 'cpu' in usage:
                        cpu_str = usage['cpu']
                        cpu_cores = self._parse_cpu_value(cpu_str)
                        node_info['usage']['cpu_cores'] = cpu_cores
                        
                        # Calcular porcentaje si tenemos capacidad
                        if 'cpu' in node_info['allocatable']:
                            allocatable_cpu = self._parse_cpu_value(node_info['allocatable']['cpu'])
                            if allocatable_cpu > 0:
                                node_info['usage']['cpu_percent'] = (cpu_cores / allocatable_cpu) * 100
                    
                    # Memoria
                    if 'memory' in usage:
                        memory_str = usage['memory']
                        memory_bytes = self._parse_memory_value(memory_str)
                        node_info['usage']['memory_bytes'] = memory_bytes
                        node_info['usage']['memory_gb'] = memory_bytes / (1024**3)
                        
                        # Calcular porcentaje si tenemos capacidad
                        if 'memory' in node_info['allocatable']:
                            allocatable_memory = self._parse_memory_value(node_info['allocatable']['memory'])
                            if allocatable_memory > 0:
                                node_info['usage']['memory_percent'] = (memory_bytes / allocatable_memory) * 100
                
                # Añadir a resultado
                result[node_name] = node_info
            
            return result
            
        except kubernetes.client.rest.ApiException as e:
            logger.error(f"Error al obtener métricas de nodos: {str(e)}")
            return None
    
    def _parse_cpu_value(self, cpu_str):
        """
        Convierte string de CPU a cores
        
        Args:
            cpu_str: String de CPU (ej: "200m")
            
        Returns:
            float: Valor en cores
        """
        if not cpu_str:
            return 0
        
        cpu_str = str(cpu_str).strip()
        
        if cpu_str.endswith('m'):
            return int(cpu_str[:-1]) / 1000
        elif cpu_str.endswith('n'):
            return int(cpu_str[:-1]) / 1000000000
        
        try:
            return float(cpu_str)
        except ValueError:
            return 0
    
    def get_service_k8s_id(self, service_name, namespace='default'):
        """
        Convierte un nombre de servicio a ID Kubernetes (reemplazando caracteres inválidos)
        
        Args:
            service_name: Nombre del servicio
            namespace: Namespace (opcional)
            
        Returns:
            str: ID válido para Kubernetes
        """
        # Reemplazar caracteres inválidos
        k8s_id = service_name.lower()
        k8s_id = re.sub(r'[^a-z0-9-]', '-', k8s_id)
        k8s_id = re.sub(r'-+', '-', k8s_id)
        k8s_id = k8s_id.strip('-')
        
        # Verificar si existe
        try:
            try:
                self.apps_api.read_namespaced_deployment(k8s_id, namespace)
                return k8s_id
            except kubernetes.client.rest.ApiException:
                # Verificar como StatefulSet
                self.apps_api.read_namespaced_stateful_set(k8s_id, namespace)
                return k8s_id
        except kubernetes.client.rest.ApiException:
            # Si no existe como deployment ni statefulset
            return None