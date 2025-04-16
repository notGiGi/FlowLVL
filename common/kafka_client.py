# common/kafka_client.py

import os
import json
import logging
import time
import uuid
from datetime import datetime
from functools import wraps
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError

from .circuit_breaker import get_circuit_breaker, CircuitBreakerOpenError
from .persistent_queue import get_persistent_queue, MessageState

logger = logging.getLogger('kafka_client')

class RobustKafkaProducer:
    """
    Productor Kafka con soporte para reintentos y persistencia en caso de fallos
    """
    
    def __init__(self, bootstrap_servers=None, use_persistent_queue=True,
                 queue_name=None, circuit_breaker_name=None, **kafka_args):
        """
        Inicializa un productor Kafka robusto
        
        Args:
            bootstrap_servers: Lista de servidores Kafka (None para usar configuración de entorno)
            use_persistent_queue: Si se debe usar una cola persistente para fallos
            queue_name: Nombre de la cola persistente (None para nombre por defecto)
            circuit_breaker_name: Nombre del circuit breaker (None para nombre por defecto)
            **kafka_args: Argumentos adicionales para KafkaProducer
        """
        self.bootstrap_servers = bootstrap_servers or os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        self.use_persistent_queue = use_persistent_queue
        
        # Serialización de mensajes
        if 'value_serializer' not in kafka_args:
            kafka_args['value_serializer'] = lambda x: json.dumps(x).encode('utf-8')
        
        # Nombre del productor para identificación
        self.producer_id = str(uuid.uuid4())[:8]
        self.client_name = f"producer-{self.producer_id}"
        
        # Inicializar circuit breaker
        self.cb_name = circuit_breaker_name or f"kafka-producer-{self.producer_id}"
        self.circuit_breaker = get_circuit_breaker(
            self.cb_name,
            failure_threshold=3,
            recovery_timeout=15,
            half_open_max_calls=1
        )
        
        # Inicializar cola persistente si se requiere
        self.queue = None
        if use_persistent_queue:
            self.queue_name = queue_name or f"kafka-outbox-{self.producer_id}"
            self.queue = get_persistent_queue(
                self.queue_name,
                max_retries=5,
                retry_delay=10
            )
        
        # Inicializar productor Kafka
        self._init_producer(**kafka_args)
        
        # Iniciar procesamiento de cola si está habilitado
        if self.use_persistent_queue:
            self._start_queue_processor()
        
        logger.info(f"Productor Kafka robusto inicializado: {self.client_name}")
    
    def _init_producer(self, **kafka_args):
        """Inicializa la conexión al productor Kafka"""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                client_id=self.client_name,
                **kafka_args
            )
            logger.info(f"Productor Kafka conectado: {self.client_name}")
        except Exception as e:
            self.producer = None
            logger.error(f"Error al conectar productor Kafka: {str(e)}")
            self.circuit_breaker.force_open()
    
    def _start_queue_processor(self):
        """Inicia el procesamiento de la cola persistente"""
        import threading
        
        def process_queue():
            while True:
                try:
                    # Solo procesar si el circuit breaker lo permite
                    if self.circuit_breaker.state != CircuitState.OPEN:
                        messages = self.queue.dequeue(
                            batch_size=10,
                            processing_id=self.producer_id
                        )
                        
                        for msg in messages:
                            try:
                                topic = msg['topic']
                                payload = msg['payload']
                                
                                # Enviar directamente a Kafka
                                self.producer.send(topic, payload)
                                self.queue.ack(msg['id'])
                                
                            except Exception as e:
                                logger.error(f"Error al procesar mensaje de cola: {str(e)}")
                                self.queue.nack(msg['id'], str(e))
                    
                    # Esperar antes del siguiente ciclo
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Error en proceso de cola: {str(e)}")
                    time.sleep(5)
        
        # Iniciar hilo en segundo plano
        queue_thread = threading.Thread(target=process_queue, daemon=True)
        queue_thread.start()
        logger.info(f"Procesador de cola iniciado para productor {self.client_name}")
    
    def send(self, topic, value, key=None, headers=None, partition=None, timestamp_ms=None):
        """
        Envía un mensaje a Kafka con soporte para reintentos
        
        Args:
            topic: Tema al que enviar el mensaje
            value: Contenido del mensaje
            key: Clave opcional del mensaje
            headers: Cabeceras opcionales
            partition: Partición específica
            timestamp_ms: Timestamp opcional en milisegundos
            
        Returns:
            Future del resultado si se envió directamente, o ID del mensaje si se encoló
            
        Raises:
            KafkaError: Si ocurre un error y no se puede encolar
        """
        try:
            # Intentar enviar a través del circuit breaker
            return self.circuit_breaker.execute(lambda: self._do_send(
                topic, value, key, headers, partition, timestamp_ms
            ))
            
        except CircuitBreakerOpenError:
            # Circuit breaker abierto, usar persistencia si está disponible
            if self.use_persistent_queue and self.queue:
                msg_id = self.queue.enqueue(topic, value)
                logger.info(f"Mensaje encolado {msg_id} para tópico {topic} (circuit breaker abierto)")
                return msg_id
            else:
                logger.error(f"No se pudo enviar mensaje a {topic} (circuit breaker abierto y sin cola persistente)")
                raise KafkaError("No se pudo enviar mensaje (circuit breaker abierto)")
            
        except Exception as e:
            # Cualquier otro error, intentar encolar
            if self.use_persistent_queue and self.queue:
                msg_id = self.queue.enqueue(topic, value)
                logger.info(f"Mensaje encolado {msg_id} para tópico {topic} tras error: {str(e)}")
                return msg_id
            else:
                logger.error(f"Error al enviar mensaje a {topic}: {str(e)}")
                if isinstance(e, KafkaError):
                    raise
                else:
                    raise KafkaError(f"Error al enviar mensaje: {str(e)}")
    
    def _do_send(self, topic, value, key=None, headers=None, partition=None, timestamp_ms=None):
        """Realiza el envío real del mensaje a Kafka"""
        if not self.producer:
            self._init_producer()
            if not self.producer:
                raise KafkaError("Productor Kafka no disponible")
        
        # Enviar mensaje y obtener future
        future = self.producer.send(
            topic=topic,
            value=value,
            key=key.encode('utf-8') if isinstance(key, str) else key,
            headers=headers,
            partition=partition,
            timestamp_ms=timestamp_ms
        )
        
        # Registrar éxito en el circuit breaker al completarse
        future.add_callback(lambda res: self.circuit_breaker.record_success())
        
        # Registrar fallo en el circuit breaker en caso de error
        future.add_errback(lambda e: self.circuit_breaker.record_failure())
        
        return future
    
    def flush(self):
        """Espera a que todos los mensajes pendientes sean enviados"""
        if self.producer:
            try:
                self.producer.flush()
            except Exception as e:
                logger.error(f"Error al hacer flush del productor: {str(e)}")
    
    def close(self):
        """Cierra la conexión del productor"""
        if self.producer:
            try:
                self.producer.close()
                self.producer = None
                logger.info(f"Productor Kafka cerrado: {self.client_name}")
            except Exception as e:
                logger.error(f"Error al cerrar productor: {str(e)}")


class RobustKafkaConsumer:
    """
    Consumidor Kafka con gestión de errores y reintentos
    """
    
    def __init__(self, topics, bootstrap_servers=None, group_id=None,
                 circuit_breaker_name=None, enable_auto_commit=True,
                 auto_offset_reset='latest', **kafka_args):
        """
        Inicializa un consumidor Kafka robusto
        
        Args:
            topics: Lista de temas a consumir
            bootstrap_servers: Lista de servidores Kafka (None para usar configuración de entorno)
            group_id: ID de grupo de consumidores (None para generar automáticamente)
            circuit_breaker_name: Nombre del circuit breaker (None para nombre por defecto)
            enable_auto_commit: Si se debe habilitar auto-commit de offsets
            auto_offset_reset: Estrategia de reinicio de offset ('latest' o 'earliest')
            **kafka_args: Argumentos adicionales para KafkaConsumer
        """
        self.bootstrap_servers = bootstrap_servers or os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
        self.topics = topics if isinstance(topics, list) else [topics]
        self.group_id = group_id or f"consumer-{str(uuid.uuid4())[:8]}"
        
        # Deserialización de mensajes
        if 'value_deserializer' not in kafka_args:
            kafka_args['value_deserializer'] = lambda x: json.loads(x.decode('utf-8'))
        
        # Nombre del consumidor para identificación
        self.consumer_id = str(uuid.uuid4())[:8]
        self.client_name = f"consumer-{self.consumer_id}"
        
        # Inicializar circuit breaker
        self.cb_name = circuit_breaker_name or f"kafka-consumer-{self.consumer_id}"
        self.circuit_breaker = get_circuit_breaker(
            self.cb_name,
            failure_threshold=3,
            recovery_timeout=15,
            half_open_max_calls=1
        )
        
        # Configuración para reconexión
        self.enable_auto_commit = enable_auto_commit
        self.auto_offset_reset = auto_offset_reset
        self.kafka_args = kafka_args
        self.consumer = None
        
        # Inicializar consumidor
        self._init_consumer()
        
        logger.info(f"Consumidor Kafka robusto inicializado: {self.client_name} para tópicos {self.topics}")
    
    def _init_consumer(self):
        """Inicializa la conexión al consumidor Kafka"""
        try:
            self.consumer = KafkaConsumer(
                *self.topics,
                bootstrap_servers=self.bootstrap_servers,
                group_id=self.group_id,
                client_id=self.client_name,
                enable_auto_commit=self.enable_auto_commit,
                auto_offset_reset=self.auto_offset_reset,
                **self.kafka_args
            )
            logger.info(f"Consumidor Kafka conectado: {self.client_name}")
            
            # Resetear circuit breaker si la conexión fue exitosa
            self.circuit_breaker.reset()
            
        except Exception as e:
            self.consumer = None
            logger.error(f"Error al conectar consumidor Kafka: {str(e)}")
            self.circuit_breaker.record_failure()
    
    def poll(self, timeout_ms=1000, max_records=None, retries=1):
        """
        Obtiene mensajes de Kafka con soporte para reintentos
        
        Args:
            timeout_ms: Tiempo máximo de espera en milisegundos
            max_records: Número máximo de registros a obtener
            retries: Número de reintentos en caso de error
            
        Returns:
            Diccionario de {TopicPartition: [Message, ...]}
            
        Raises:
            CircuitBreakerOpenError: Si el circuit breaker está abierto
            KafkaError: Si ocurre un error tras los reintentos
        """
        try:
            # Usar circuit breaker para controlar acceso a Kafka
            return self.circuit_breaker.execute(lambda: self._do_poll(timeout_ms, max_records))
            
        except CircuitBreakerOpenError:
            logger.warning(f"No se pueden leer mensajes: circuit breaker {self.cb_name} abierto")
            raise
            
        except Exception as e:
            if retries > 0:
                logger.warning(f"Error al leer mensajes (reintentando {retries}): {str(e)}")
                time.sleep(1)
                return self.poll(timeout_ms, max_records, retries - 1)
            else:
                logger.error(f"Error al leer mensajes (sin reintentos): {str(e)}")
                if isinstance(e, KafkaError):
                    raise
                else:
                    raise KafkaError(f"Error al leer mensajes: {str(e)}")
    
    def _do_poll(self, timeout_ms, max_records):
        """Realiza la lectura real de mensajes de Kafka"""
        if not self.consumer:
            self._init_consumer()
            if not self.consumer:
                raise KafkaError("Consumidor Kafka no disponible")
        
        # Obtener mensajes
        try:
            messages = self.consumer.poll(timeout_ms=timeout_ms, max_records=max_records)
            
            # Registrar éxito en circuit breaker
            self.circuit_breaker.record_success()
            
            return messages
            
        except Exception as e:
            # Registrar fallo en circuit breaker
            self.circuit_breaker.record_failure()
            
            # Intentar reconstruir consumidor
            self.close()
            
            # Reenviar excepción
            raise
    
    def commit(self):
        """Realiza commit de offsets manualmente"""
        if self.consumer:
            try:
                self.consumer.commit()
            except Exception as e:
                logger.error(f"Error al hacer commit: {str(e)}")
    
    def close(self):
        """Cierra la conexión del consumidor"""
        if self.consumer:
            try:
                self.consumer.close()
                self.consumer = None
                logger.info(f"Consumidor Kafka cerrado: {self.client_name}")
            except Exception as e:
                logger.error(f"Error al cerrar consumidor: {str(e)}")
    
    def subscribe(self, topics):
        """
        Suscribe el consumidor a tópicos adicionales
        
        Args:
            topics: Lista de tópicos o tópico individual
        """
        new_topics = topics if isinstance(topics, list) else [topics]
        
        for topic in new_topics:
            if topic not in self.topics:
                self.topics.append(topic)
        
        if self.consumer:
            self.consumer.subscribe(self.topics)
            logger.info(f"Consumidor {self.client_name} suscrito a tópicos: {self.topics}")

# Función para integrar validación de acciones
def validate_action_result(action_function):
    """
    Decorador para validar el resultado de acciones correctivas
    
    Args:
        action_function: Función que ejecuta una acción correctiva
        
    Returns:
        Función decorada que valida y registra el resultado
    """
    @wraps(action_function)
    def wrapper(self, action, metrics, *args, **kwargs):
        action_id = action.get('action_id', 'unknown_action')
        service_id = action.get('service_id', 'unknown_service')
        
        logger.info(f"Ejecutando acción {action_id} para {service_id}")
        
        # Registrar inicio de acción
        start_time = time.time()
        
        try:
            # Ejecutar acción
            result = action_function(self, action, metrics, *args, **kwargs)
            
            # Verificar resultado
            if result:
                logger.info(f"Acción {action_id} completada correctamente en {time.time()-start_time:.2f}s")
                
                # Registrar evento de acción exitosa
                self._register_action_event(action, True, None, metrics)
                
                # Opcional: verificar métricas post-acción
                # self._verify_post_action_metrics(action, metrics)
                
                return True
            else:
                logger.warning(f"Acción {action_id} falló (resultado false)")
                
                # Registrar evento de acción fallida
                self._register_action_event(action, False, "Acción reportó fallo", metrics)
                
                return False
                
        except Exception as e:
            logger.error(f"Error al ejecutar acción {action_id}: {str(e)}")
            
            # Registrar evento de acción con excepción
            self._register_action_event(action, False, str(e), metrics)
            
            return False
    
    return wrapper