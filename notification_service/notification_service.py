import os
import json
import time
import logging
import threading
import smtplib
import ssl
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
import redis

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('notification_service')

class NotificationService:
    """
    Servicio de notificaciones para alertas y comunicación con usuarios.
    Soporta múltiples canales: email, Slack, webhook personalizado.
    """
    
    def __init__(self, config=None):
        """
        Inicializa el servicio de notificaciones
        
        Args:
            config: Configuración opcional
        """
        self.config = config or {}
        
        # Cargar configuración desde variables de entorno si no se proporciona
        self._load_config_from_env()
        
        # Conexión a Redis para colas de mensajes
        self.redis_client = self._initialize_redis()
        
        # Control para worker thread
        self.running = True
        self.worker_thread = None
        
        # Historial de notificaciones
        self.notification_history = []
        self.max_history_size = self.config.get('max_history_size', 1000)
        
        # Mapeo de canales a funciones de envío
        self.channel_handlers = {
            'email': self._send_email,
            'slack': self._send_slack,
            'webhook': self._send_webhook,
            'console': self._send_console
        }
        
        # Iniciar worker para procesar colas
        self._start_worker()
        
        logger.info("Servicio de notificaciones inicializado")
    
    def _load_config_from_env(self):
        """Carga configuración desde variables de entorno"""
        # Redis
        self.config.setdefault('redis_host', os.environ.get('REDIS_HOST', 'localhost'))
        self.config.setdefault('redis_port', int(os.environ.get('REDIS_PORT', 6379)))
        self.config.setdefault('redis_password', os.environ.get('REDIS_PASSWORD', ''))
        
        # Email
        self.config.setdefault('email_smtp_host', os.environ.get('EMAIL_SMTP_HOST', 'smtp.example.com'))
        self.config.setdefault('email_smtp_port', int(os.environ.get('EMAIL_SMTP_PORT', 587)))
        self.config.setdefault('email_username', os.environ.get('EMAIL_USERNAME', ''))
        self.config.setdefault('email_password', os.environ.get('EMAIL_PASSWORD', ''))
        self.config.setdefault('email_sender', os.environ.get('EMAIL_SENDER', 'notifications@example.com'))
        
        # Slack
        self.config.setdefault('slack_webhook_url', os.environ.get('SLACK_WEBHOOK_URL', ''))
        
        # Colas y canales
        self.config.setdefault('queue_prefix', 'notifications:queue:')
        self.config.setdefault('default_channels', ['console'])
        
        # Configuración de alertas
        self.config.setdefault('alert_throttling', {
            'critical': 0,      # Sin throttling
            'high': 5 * 60,     # 5 minutos
            'medium': 15 * 60,  # 15 minutos
            'low': 60 * 60      # 1 hora
        })
    
    def _initialize_redis(self):
        """Inicializa conexión a Redis"""
        try:
            client = redis.Redis(
                host=self.config['redis_host'],
                port=self.config['redis_port'],
                password=self.config['redis_password'],
                decode_responses=True
            )
            # Verificar conexión
            client.ping()
            logger.info(f"Conexión a Redis establecida: {self.config['redis_host']}:{self.config['redis_port']}")
            return client
        except redis.exceptions.ConnectionError as e:
            logger.error(f"Error al conectar a Redis: {str(e)}")
            logger.warning("Utilizando modo fallback sin Redis")
            return None
    
    def _start_worker(self):
        """Inicia worker thread para procesar colas"""
        self.worker_thread = threading.Thread(target=self._process_queues)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        logger.info("Worker de notificaciones iniciado")
    
    def _process_queues(self):
        """Procesa colas de notificaciones"""
        if not self.redis_client:
            logger.warning("Redis no disponible, worker de colas deshabilitado")
            return
        
        while self.running:
            try:
                # Obtener todas las colas activas
                queue_pattern = f"{self.config['queue_prefix']}*"
                queues = self.redis_client.keys(queue_pattern)
                
                if not queues:
                    time.sleep(1)
                    continue
                
                # Procesar cada cola
                for queue in queues:
                    # BLPOP con timeout para evitar bloqueo indefinido
                    result = self.redis_client.blpop([queue], timeout=1)
                    if not result:
                        continue
                    
                    # Extraer datos
                    _, message_data = result
                    
                    try:
                        # Parsear mensaje
                        message = json.loads(message_data)
                        
                        # Determinar canales
                        channels = message.get('channels', self.config['default_channels'])
                        
                        # Enviar notificación por cada canal
                        self._send_notification_to_channels(message, channels)
                        
                    except json.JSONDecodeError:
                        logger.error(f"Error al parsear mensaje: {message_data}")
                    except Exception as e:
                        logger.error(f"Error al procesar mensaje: {str(e)}")
            
            except Exception as e:
                logger.error(f"Error en worker de notificaciones: {str(e)}")
                time.sleep(5)  # Esperar antes de reintentar
    
    def _send_notification_to_channels(self, message, channels):
        """
        Envía notificación a múltiples canales
        
        Args:
            message: Mensaje a enviar
            channels: Lista de canales
        """
        for channel in channels:
            if channel in self.channel_handlers:
                try:
                    # Enviar al canal
                    self.channel_handlers[channel](message)
                    
                    # Registrar en historial
                    self._add_to_history({
                        'timestamp': datetime.now().isoformat(),
                        'channel': channel,
                        'status': 'sent',
                        'message_id': message.get('id', str(time.time())),
                        'message_type': message.get('type', 'unknown'),
                        'priority': message.get('priority', 'medium')
                    })
                    
                except Exception as e:
                    logger.error(f"Error al enviar a canal {channel}: {str(e)}")
                    
                    # Registrar error
                    self._add_to_history({
                        'timestamp': datetime.now().isoformat(),
                        'channel': channel,
                        'status': 'error',
                        'message_id': message.get('id', str(time.time())),
                        'message_type': message.get('type', 'unknown'),
                        'priority': message.get('priority', 'medium'),
                        'error': str(e)
                    })
            else:
                logger.warning(f"Canal no soportado: {channel}")
    
    def _add_to_history(self, entry):
        """Añade entrada al historial de notificaciones"""
        self.notification_history.append(entry)
        
        # Limitar tamaño del historial
        if len(self.notification_history) > self.max_history_size:
            self.notification_history = self.notification_history[-self.max_history_size:]
    
    def send_notification(self, message, channels=None, priority='medium'):
        """
        Envía una notificación
        
        Args:
            message: Mensaje a enviar (dict o string)
            channels: Lista de canales (opcional)
            priority: Prioridad (critical, high, medium, low)
            
        Returns:
            bool: True si se encoló correctamente
        """
        try:
            # Si message es string, convertir a dict
            if isinstance(message, str):
                message = {
                    'text': message,
                    'title': 'Notification'
                }
            
            # Añadir datos adicionales
            message['id'] = message.get('id', f"msg_{int(time.time())}")
            message['timestamp'] = message.get('timestamp', datetime.now().isoformat())
            message['priority'] = message.get('priority', priority)
            message['channels'] = channels or self.config['default_channels']
            
            # Verificar throttling
            if not self._check_throttling(message):
                logger.info(f"Notificación suprimida por throttling: {message['id']}")
                return False
            
            # Si no hay Redis, enviar directamente
            if not self.redis_client:
                self._send_notification_to_channels(message, message['channels'])
                return True
            
            # Determinar cola según tipo de mensaje
            message_type = message.get('type', 'general')
            queue_name = f"{self.config['queue_prefix']}{message_type}"
            
            # Serializar y encolar
            message_data = json.dumps(message)
            self.redis_client.rpush(queue_name, message_data)
            
            logger.info(f"Notificación encolada: {message['id']} (Tipo: {message_type}, Prioridad: {priority})")
            return True
            
        except Exception as e:
            logger.error(f"Error al enviar notificación: {str(e)}")
            return False
    
    def _check_throttling(self, message):
        """
        Verifica si una notificación debe ser suprimida por throttling
        
        Args:
            message: Mensaje a verificar
            
        Returns:
            bool: True si se puede enviar, False si debe suprimirse
        """
        # Verificar si aplicar throttling
        if not self.redis_client:
            return True  # Sin Redis, no hay throttling
        
        # Obtener clave
        message_id = message.get('id', '')
        message_type = message.get('type', 'general')
        service_id = message.get('service_id', 'unknown')
        
        throttling_key = f"notifications:throttle:{service_id}:{message_type}"
        
        # Verificar si hay entrada reciente
        last_notification = self.redis_client.get(throttling_key)
        if not last_notification:
            # No hay entrada, establecer y permitir
            priority = message.get('priority', 'medium')
            ttl = self.config['alert_throttling'].get(priority, 300)  # Default 5 minutos
            
            self.redis_client.set(throttling_key, message_id, ex=ttl)
            return True
        
        # Ya existe una notificación reciente, verificar si es crítica
        if message.get('priority') == 'critical':
            # Las notificaciones críticas no se suprimen
            self.redis_client.set(throttling_key, message_id, ex=60)  # 1 minuto
            return True
            
        # Suprimir por throttling
        return False
    
    def send_alert(self, service_id, alert_type, metrics, description=None, priority='medium'):
        """
        Envía una alerta sobre una anomalía o predicción
        
        Args:
            service_id: ID del servicio
            alert_type: Tipo de alerta (anomaly, prediction)
            metrics: Métricas relacionadas
            description: Descripción adicional
            priority: Prioridad de la alerta
            
        Returns:
            bool: True si se envió correctamente
        """
        # Construir mensaje
        title = f"ALERTA - {alert_type.upper()} detectada en {service_id}"
        
        # Formatear métricas como texto
        metrics_text = "\n".join([f"- {k}: {v}" for k, v in metrics.items()]) if metrics else "No hay métricas disponibles"
        
        # Crear mensaje completo
        message = {
            'title': title,
            'text': description or f"Se ha detectado una {alert_type} en el servicio {service_id}",
            'service_id': service_id,
            'type': 'alert',
            'alert_type': alert_type,
            'metrics': metrics,
            'priority': priority,
            'timestamp': datetime.now().isoformat()
        }
        
        # Determinar canales según prioridad
        channels = ['console']
        if priority in ['critical', 'high']:
            channels.extend(['email', 'slack'])
        elif priority == 'medium':
            channels.append('slack')
        
        # Enviar notificación
        return self.send_notification(message, channels=channels, priority=priority)
    
    def _send_email(self, message):
        """
        Envía notificación por email
        
        Args:
            message: Mensaje a enviar
        """
        # Verificar configuración
        if not self.config['email_smtp_host'] or not self.config['email_username']:
            logger.error("Configuración de email incompleta")
            return False
        
        # Obtener destinatarios
        recipients = message.get('recipients', [])
        if not recipients:
            logger.warning("No hay destinatarios para email")
            return False
        
        # Crear mensaje
        msg = MIMEMultipart('alternative')
        msg['Subject'] = message.get('title', 'Notificación')
        msg['From'] = self.config['email_sender']
        msg['To'] = ', '.join(recipients)
        
        # Cuerpo del mensaje
        text_content = message.get('text', '')
        html_content = message.get('html', '')
        
        # Si no hay HTML, convertir texto a HTML simple
        if not html_content and text_content:
            html_content = f"<html><body><p>{text_content.replace('\n', '<br>')}</p></body></html>"
        
        # Añadir partes
        if text_content:
            msg.attach(MIMEText(text_content, 'plain'))
        if html_content:
            msg.attach(MIMEText(html_content, 'html'))
        
        # Enviar email
        context = ssl.create_default_context()
        
        try:
            with smtplib.SMTP(self.config['email_smtp_host'], self.config['email_smtp_port']) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                server.login(self.config['email_username'], self.config['email_password'])
                server.sendmail(self.config['email_sender'], recipients, msg.as_string())
                
            logger.info(f"Email enviado a {len(recipients)} destinatarios")
            return True
            
        except Exception as e:
            logger.error(f"Error al enviar email: {str(e)}")
            return False
    
    def _send_slack(self, message):
        """
        Envía notificación a Slack
        
        Args:
            message: Mensaje a enviar
        """
        # Verificar configuración
        if not self.config['slack_webhook_url']:
            logger.error("URL de webhook de Slack no configurada")
            return False
        
        # Construir payload
        slack_message = {
            'text': message.get('title', 'Notificación'),
            'blocks': [
                {
                    'type': 'header',
                    'text': {
                        'type': 'plain_text',
                        'text': message.get('title', 'Notificación')
                    }
                }
            ]
        }
        
        # Añadir texto principal
        if message.get('text'):
            slack_message['blocks'].append({
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': message.get('text')
                }
            })
        
        # Añadir campos para métricas si existen
        if message.get('metrics'):
            fields = []
            for key, value in message.get('metrics').items():
                fields.append({
                    'type': 'mrkdwn',
                    'text': f"*{key}*\n{value}"
                })
            
            # Agrupar campos en bloques de 4 (limitación de Slack)
            for i in range(0, len(fields), 4):
                slack_message['blocks'].append({
                    'type': 'section',
                    'fields': fields[i:i+4]
                })
        
        # Añadir contexto
        context_elements = []
        
        if message.get('priority'):
            context_elements.append({
                'type': 'mrkdwn',
                'text': f"*Prioridad:* {message.get('priority')}"
            })
        
        if message.get('service_id'):
            context_elements.append({
                'type': 'mrkdwn',
                'text': f"*Servicio:* {message.get('service_id')}"
            })
        
        if message.get('timestamp'):
            context_elements.append({
                'type': 'mrkdwn',
                'text': f"*Hora:* {message.get('timestamp')}"
            })
        
        if context_elements:
            slack_message['blocks'].append({
                'type': 'context',
                'elements': context_elements
            })
        
        # Enviar a Slack
        try:
            response = requests.post(
                self.config['slack_webhook_url'],
                json=slack_message,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code == 200:
                logger.info("Mensaje enviado a Slack correctamente")
                return True
            else:
                logger.error(f"Error al enviar a Slack: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error al enviar a Slack: {str(e)}")
            return False
    
    def _send_webhook(self, message):
        """
        Envía notificación a webhook personalizado
        
        Args:
            message: Mensaje a enviar
        """
        # Verificar webhook URL
        webhook_url = message.get('webhook_url')
        if not webhook_url:
            logger.error("URL de webhook no proporcionada")
            return False
        
        # Enviar a webhook
        try:
            response = requests.post(
                webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'}
            )
            
            if response.status_code >= 200 and response.status_code < 300:
                logger.info(f"Mensaje enviado a webhook correctamente: {webhook_url}")
                return True
            else:
                logger.error(f"Error al enviar a webhook: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error al enviar a webhook: {str(e)}")
            return False
    
    def _send_console(self, message):
        """
        Envía notificación a consola (para desarrollo y depuración)
        
        Args:
            message: Mensaje a enviar
        """
        priority = message.get('priority', 'medium')
        title = message.get('title', 'Notificación')
        text = message.get('text', '')
        service_id = message.get('service_id', 'unknown')
        
        # Formatear según prioridad
        priority_formats = {
            'critical': '\033[91m',  # Rojo
            'high': '\033[93m',      # Amarillo
            'medium': '\033[94m',    # Azul
            'low': '\033[92m'        # Verde
        }
        
        reset = '\033[0m'
        priority_format = priority_formats.get(priority, '')
        
        # Imprimir notificación
        print(f"\n{priority_format}[NOTIFICACIÓN - {priority.upper()}]{reset} {title}")
        print(f"Servicio: {service_id}")
        print(f"Tiempo: {message.get('timestamp', datetime.now().isoformat())}")
        
        if text:
            print(f"\n{text}\n")
        
        # Imprimir métricas si hay
        if message.get('metrics'):
            print("Métricas:")
            for key, value in message.get('metrics').items():
                print(f"  - {key}: {value}")
            print()
        
        return True
    
    def get_notification_history(self, service_id=None, limit=50):
        """
        Obtiene historial de notificaciones
        
        Args:
            service_id: Filtrar por servicio (opcional)
            limit: Número máximo de notificaciones
            
        Returns:
            List: Historial de notificaciones
        """
        # Filtrar por servicio si se proporciona
        if service_id:
            filtered = [n for n in self.notification_history if n.get('service_id') == service_id]
        else:
            filtered = self.notification_history
        
        # Ordenar por timestamp (más recientes primero)
        sorted_history = sorted(
            filtered, 
            key=lambda x: x.get('timestamp', ''), 
            reverse=True
        )
        
        # Limitar número de resultados
        return sorted_history[:limit]
    
    def stop(self):
        """Detiene el servicio de notificaciones"""
        self.running = False
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=5)
        logger.info("Servicio de notificaciones detenido")


# Para pruebas y ejecución directa
if __name__ == "__main__":
    # Configurar logging
    logging.basicConfig(level=logging.INFO)
    
    # Crear servicio de notificaciones
    notification_service = NotificationService()
    
    # Ejemplo de notificación
    notification_service.send_alert(
        service_id="example-service",
        alert_type="anomaly",
        metrics={
            "memory_usage": "85%",
            "response_time": "250ms",
            "error_rate": "2.5%"
        },
        description="Se ha detectado un uso excesivo de memoria en el servicio",
        priority="high"
    )
    
    # Mantener el programa en ejecución
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        notification_service.stop()