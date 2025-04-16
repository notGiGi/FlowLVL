import os
import json
import logging
import subprocess
import threading
import queue
import time
import requests
from datetime import datetime, timedelta

from utils.retry import retry_with_backoff
from utils.metrics import MetricsCollector
from utils.security import CommandValidator, AccessControl
from utils.distributed_cache import DistributedCache

logger = logging.getLogger('action_orchestrator')

class ActionOrchestrator:
    """
    Orquestador de acciones que maneja la ejecución segura y controlada
    de acciones correctivas en el sistema.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Cola de acciones pendientes
        self.action_queue = queue.PriorityQueue()
        
        # Historial de acciones
        self.action_history = []
        self.max_history = self.config.get('max_history_items', 1000)
        
        # Límites de ejecución
        self.cooldown_periods = {
            'low': timedelta(minutes=30),
            'medium': timedelta(minutes=15),
            'high': timedelta(minutes=5),
            'critical': timedelta(minutes=1)
        }
        
        # Componentes de seguridad
        self.command_validator = CommandValidator()
        self.access_control = AccessControl(config=self.config)
        
        # Métrica
        self.metrics = MetricsCollector(config=self.config)
        
        # Caché para estado compartido
        self.cache = DistributedCache(
            redis_host=self.config.get('redis_host', 'localhost'),
            redis_port=self.config.get('redis_port', 6379)
        )
        
        # Iniciar worker thread
        self.running = True
        self.worker_thread = threading.Thread(target=self._process_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        
        logger.info("ActionOrchestrator inicializado")
    
    def enqueue_action(self, action, execution_context=None, priority=None):
        """
        Encola una acción para ejecución
        
        Args:
            action: Definición de la acción a ejecutar
            execution_context: Datos adicionales para ejecución
            priority: Prioridad manual (opcional)
            
        Returns:
            str: ID de la acción encolada o None si falla
        """
        try:
            if not action:
                return None
                
            # Generar ID único para la acción
            action_id = f"{action.get('action_id', 'unknown')}_{int(time.time())}"
            
            # Determinar prioridad
            if priority is None:
                # Usar prioridad de la acción o valor predeterminado
                priority_map = {
                    'critical': 0,
                    'high': 1,
                    'medium': 2,
                    'low': 3
                }
                priority = priority_map.get(action.get('priority', 'medium'), 2)
            
            # Verificar cooling period
            service_id = action.get('service_id', 'unknown')
            action_type = action.get('action_id', 'unknown')
            
            if self._is_in_cooldown(service_id, action_type):
                logger.info(f"Acción {action_type} para {service_id} en periodo de enfriamiento, no se ejecutará")
                return None
            
            # Crear item para la cola
            queue_item = {
                'id': action_id,
                'action': action,
                'context': execution_context or {},
                'timestamp': datetime.now().isoformat(),
                'status': 'pending'
            }
            
            # Encolar con prioridad
            self.action_queue.put((priority, queue_item))
            
            logger.info(f"Acción {action_id} encolada con prioridad {priority}")
            
            return action_id
            
        except Exception as e:
            logger.error(f"Error al encolar acción: {str(e)}")
            return None
    
    def _is_in_cooldown(self, service_id, action_type):
        """Comprueba si una acción está en periodo de enfriamiento"""
        cache_key = f"cooldown:{service_id}:{action_type}"
        return self.cache.get(cache_key) is not None
    
    def _set_cooldown(self, service_id, action_type, priority='medium'):
        """Establece periodo de enfriamiento para una acción"""
        cache_key = f"cooldown:{service_id}:{action_type}"
        cooldown = self.cooldown_periods.get(priority, timedelta(minutes=15))
        ttl = int(cooldown.total_seconds())
        self.cache.set(cache_key, datetime.now().isoformat(), ttl=ttl)
    
    def _process_queue(self):
        """Worker que procesa la cola de acciones"""
        while self.running:
            try:
                # Obtener siguiente acción (esperar hasta 1 segundo)
                try:
                    priority, item = self.action_queue.get(timeout=1)
                except queue.Empty:
                    continue
                
                # Ejecutar acción
                logger.info(f"Procesando acción {item['id']} de prioridad {priority}")
                
                success = self._execute_action(item['action'], item['context'])
                
                # Actualizar estado
                item['status'] = 'completed' if success else 'failed'
                item['completion_time'] = datetime.now().isoformat()
                item['success'] = success
                
                # Almacenar en historial
                self._add_to_history(item)
                
                # Establecer cooldown
                if success:
                    self._set_cooldown(
                        item['action'].get('service_id', 'unknown'),
                        item['action'].get('action_id', 'unknown'),
                        item['action'].get('priority', 'medium')
                    )
                
                # Marcar como completada
                self.action_queue.task_done()
                
            except Exception as e:
                logger.error(f"Error en el procesamiento de la cola: {str(e)}")
                time.sleep(1)  # Evitar ciclos rápidos en caso de error
    
    def _add_to_history(self, item):
        """Añade una acción al historial"""
        self.action_history.append(item)
        
        # Limitar tamaño del historial
        if len(self.action_history) > self.max_history:
            self.action_history = self.action_history[-self.max_history:]
    
    @retry_with_backoff(max_retries=2)
    def _execute_action(self, action, context):
        """
        Ejecuta una acción de forma segura
        
        Args:
            action: Definición de la acción
            context: Contexto de ejecución
            
        Returns:
            bool: True si se ejecutó correctamente
        """
        try:
            # Verificar si tenemos token de autorización en el contexto
            auth_token = context.get('auth_token')
            service_id = action.get('service_id', 'unknown')
            action_id = action.get('action_id', 'unknown')
            priority = action.get('priority', 'medium')
            
            # Determinar nivel de operación requerido según prioridad
            operation_level = {
                'low': 'execute_low',
                'medium': 'execute_medium',
                'high': 'execute_high',
                'critical': 'execute_all'
            }.get(priority, 'execute_medium')
            
            # Verificar permisos si hay token
            if auth_token and not self.access_control.is_operation_allowed(auth_token, operation_level, service_id):
                logger.warning(f"Autorización denegada para acción {action_id} en {service_id}")
                return False
            
            # Ejecutar según tipo de remediación
            remediation_type = action.get('remediation', {}).get('type', 'command')
            
            if remediation_type == 'command':
                return self._execute_command_action(action, context)
            elif remediation_type == 'api':
                return self._execute_api_action(action, context)
            else:
                logger.warning(f"Tipo de remediación desconocido: {remediation_type}")
                return False
                
        except Exception as e:
            logger.error(f"Error al ejecutar acción: {str(e)}")
            
            # Registrar métrica de fallo
            self.metrics.record_action_execution(
                action.get('service_id', 'unknown'),
                action.get('action_id', 'unknown'),
                False
            )
            
            return False
    
    def _execute_command_action(self, action, context):
        """Ejecuta acción de tipo comando"""
        # Obtener comando a ejecutar
        command_template = action.get('command', '') or action.get('remediation', {}).get('command', '')
        
        if not command_template:
            logger.warning("No se encontró comando para ejecutar")
            return False
            
        # Sustituir variables en el comando
        command = self._substitute_variables(command_template, action, context)
        
        # Validar comando por seguridad
        is_safe, reason = self.command_validator.is_safe_command(command)
        if not is_safe:
            logger.warning(f"Comando inseguro rechazado: {command} - Razón: {reason}")
            return False
        
        logger.info(f"Ejecutando comando: {command}")
        
        try:
            # Ejecutar comando
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Esperar a que termine (con timeout)
            stdout, stderr = process.communicate(timeout=30)
            
            # Verificar resultado
            if process.returncode == 0:
                logger.info(f"Comando ejecutado exitosamente")
                if stdout:
                    logger.debug(f"Salida: {stdout[:500]}")
                
                # Registrar métrica de éxito
                self.metrics.record_action_execution(
                    action.get('service_id', 'unknown'),
                    action.get('action_id', 'unknown'),
                    True
                )
                
                return True
            else:
                logger.error(f"Error al ejecutar comando: {stderr}")
                
                # Registrar métrica de fallo
                self.metrics.record_action_execution(
                    action.get('service_id', 'unknown'),
                    action.get('action_id', 'unknown'),
                    False
                )
                
                return False
                
        except subprocess.TimeoutExpired:
            logger.error(f"Timeout al ejecutar comando")
            process.kill()
            return False
        except Exception as e:
            logger.error(f"Error en ejecución de comando: {str(e)}")
            return False
    
    def _execute_api_action(self, action, context):
        """Ejecuta acción mediante llamada a API"""
        remediation = action.get('remediation', {})
        
        # Obtener detalles de la API
        endpoint = self._substitute_variables(remediation.get('endpoint', ''), action, context)
        method = remediation.get('method', 'POST')
        headers = remediation.get('headers', {})
        payload = remediation.get('payload', {})
        timeout = remediation.get('timeout', 10)
        
        if not endpoint:
            logger.warning("No se encontró endpoint para API")
            return False
        
        logger.info(f"Ejecutando acción API: {method} {endpoint}")
        
        try:
            # Sustituir variables en payload si es un diccionario
            if isinstance(payload, dict):
                processed_payload = {}
                for key, value in payload.items():
                    if isinstance(value, str):
                        processed_payload[key] = self._substitute_variables(value, action, context)
                    else:
                        processed_payload[key] = value
            else:
                processed_payload = payload
            
            # Sustituir variables en headers
            processed_headers = {}
            for key, value in headers.items():
                processed_headers[key] = self._substitute_variables(value, action, context)
            
            # Realizar solicitud
            response = requests.request(
                method,
                endpoint,
                headers=processed_headers,
                json=processed_payload,
                timeout=timeout
            )
            
            # Verificar respuesta
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"API respondió correctamente: {response.status_code}")
                
                # Registrar métrica de éxito
                self.metrics.record_action_execution(
                    action.get('service_id', 'unknown'),
                    action.get('action_id', 'unknown'),
                    True
                )
                
                return True
            else:
                logger.error(f"Error en respuesta API: {response.status_code} - {response.text[:200]}")
                
                # Registrar métrica de fallo
                self.metrics.record_action_execution(
                    action.get('service_id', 'unknown'),
                    action.get('action_id', 'unknown'),
                    False
                )
                
                return False
                
        except Exception as e:
            logger.error(f"Error en llamada API: {str(e)}")
            return False
    
    def _substitute_variables(self, template, action, context):
        """
        Sustituye variables en una plantilla
        
        Args:
            template: Plantilla con variables
            action: Definición de la acción
            context: Contexto de ejecución
            
        Returns:
            str: Plantilla con variables sustituidas
        """
        if not template or not isinstance(template, str):
            return template
            
        result = template
        
        # Sustituir variables de acción
        replacements = {
            "${service_id}": action.get('service_id', ''),
            "${action_id}": action.get('action_id', '')
        }
        
        # Añadir parámetros de la acción
        params = action.get('parameters', {})
        for param_name, param_value in params.items():
            replacements[f"${{{param_name}}}"] = str(param_value)
        
        # Añadir variables de contexto
        for key, value in context.items():
            if isinstance(value, (str, int, float, bool)):
                replacements[f"${{{key}}}"] = str(value)
        
        # Realizar sustituciones
        for var, value in replacements.items():
            result = result.replace(var, value)
        
        return result
    
    def get_action_history(self, service_id=None, limit=10):
        """
        Obtiene historial de acciones ejecutadas
        
        Args:
            service_id: Filtrar por servicio (opcional)
            limit: Número máximo de elementos
            
        Returns:
            list: Historial de acciones
        """
        if service_id:
            # Filtrar por servicio
            filtered_history = [
                item for item in self.action_history
                if item['action'].get('service_id') == service_id
            ]
        else:
            filtered_history = self.action_history
        
        # Limitar número de elementos y ordenar por más reciente primero
        sorted_history = sorted(
            filtered_history,
            key=lambda x: x.get('timestamp', ''),
            reverse=True
        )
        
        return sorted_history[:limit]
    
    def stop(self):
        """Detiene el worker thread"""
        self.running = False
        if self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)