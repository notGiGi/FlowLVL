# common/persistent_queue.py

import os
import json
import time
import uuid
import logging
import threading
import sqlite3
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger('persistent_queue')

class MessageState(Enum):
    """Estados posibles de un mensaje en la cola"""
    PENDING = 'PENDING'       # Pendiente de procesamiento
    PROCESSING = 'PROCESSING' # En procesamiento
    COMPLETED = 'COMPLETED'   # Procesado correctamente
    FAILED = 'FAILED'         # Procesamiento fallido
    RETRYING = 'RETRYING'     # Pendiente de reintento

class PersistentQueue:
    """
    Cola persistente para garantizar procesamiento confiable de mensajes
    incluso en caso de fallos del sistema.
    """
    
    def __init__(self, queue_name, db_path=None, max_retries=3, 
                 retry_delay=60, cleanup_interval=3600, max_age_days=7):
        """
        Inicializa una nueva cola persistente
        
        Args:
            queue_name: Nombre identificativo de la cola
            db_path: Ruta al archivo SQLite para persistencia (por defecto: /data/queues/{queue_name}.db)
            max_retries: Número máximo de reintentos para mensajes fallidos
            retry_delay: Tiempo de espera (segundos) entre reintentos
            cleanup_interval: Intervalo (segundos) para limpieza de mensajes viejos
            max_age_days: Edad máxima (días) de mensajes completados/fallidos antes de eliminarlos
        """
        self.queue_name = queue_name
        
        # Configurar ruta de base de datos
        if db_path is None:
            db_dir = os.environ.get('QUEUE_DATA_DIR', '/data/queues')
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, f"{queue_name}.db")
        
        self.db_path = db_path
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.cleanup_interval = cleanup_interval
        self.max_age_days = max_age_days
        
        # Inicializar base de datos
        self._init_db()
        
        # Control de concurrencia
        self.lock = threading.RLock()
        
        # Iniciar hilo de mantenimiento si es necesario
        self.maintenance_thread = None
        self.running = False
        
        logger.info(f"Cola persistente '{queue_name}' inicializada en {db_path}")
    
    def _init_db(self):
        """Inicializa la estructura de la base de datos"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Crear tabla principal de mensajes
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS queue_messages (
                    id TEXT PRIMARY KEY,
                    topic TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    next_retry_at TIMESTAMP,
                    error_message TEXT,
                    processing_id TEXT
                )
            ''')
            
            # Crear índices para consultas frecuentes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_state ON queue_messages(state)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_topic ON queue_messages(topic)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_next_retry ON queue_messages(next_retry_at)')
            
            conn.commit()
    
    def _get_connection(self):
        """Obtiene una conexión a la base de datos"""
        return sqlite3.connect(self.db_path, 
                              detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES)
    
    def start_maintenance(self):
        """Inicia el hilo de mantenimiento de la cola"""
        with self.lock:
            if self.running:
                logger.warning(f"Cola '{self.queue_name}' ya tiene mantenimiento en ejecución")
                return
            
            self.running = True
            self.maintenance_thread = threading.Thread(
                target=self._maintenance_worker, 
                daemon=True
            )
            self.maintenance_thread.start()
            
            logger.info(f"Mantenimiento de cola '{self.queue_name}' iniciado")
    
    def stop_maintenance(self):
        """Detiene el hilo de mantenimiento"""
        with self.lock:
            self.running = False
            if self.maintenance_thread and self.maintenance_thread.is_alive():
                self.maintenance_thread.join(timeout=5)
            logger.info(f"Mantenimiento de cola '{self.queue_name}' detenido")
    
    def _maintenance_worker(self):
        """Función de mantenimiento ejecutada en segundo plano"""
        last_cleanup = 0
        
        while self.running:
            try:
                # Procesar reintentos
                self._process_retries()
                
                # Procesar timeout de mensajes en procesamiento
                self._handle_processing_timeouts()
                
                # Limpieza periódica
                current_time = time.time()
                if current_time - last_cleanup > self.cleanup_interval:
                    self._cleanup_old_messages()
                    last_cleanup = current_time
                
                # Esperar antes del siguiente ciclo
                time.sleep(5)
                
            except Exception as e:
                logger.error(f"Error en mantenimiento de cola '{self.queue_name}': {str(e)}")
                time.sleep(30)  # Esperar más tiempo en caso de error
    
    def _process_retries(self):
        """Procesa mensajes pendientes de reintento"""
        now = datetime.now()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Obtener mensajes para reintento
            cursor.execute('''
                SELECT id FROM queue_messages
                WHERE state = ? AND next_retry_at <= ?
            ''', (MessageState.RETRYING.value, now))
            
            retry_ids = [row[0] for row in cursor.fetchall()]
            
            # Actualizar estado de los mensajes
            if retry_ids:
                placeholders = ','.join(['?'] * len(retry_ids))
                cursor.execute(f'''
                    UPDATE queue_messages
                    SET state = ?, updated_at = ?
                    WHERE id IN ({placeholders})
                ''', [MessageState.PENDING.value, now] + retry_ids)
                
                conn.commit()
                logger.info(f"Cola '{self.queue_name}': {len(retry_ids)} mensajes marcados para reintento")
    
    def _handle_processing_timeouts(self):
        """Maneja mensajes que han quedado bloqueados en estado de procesamiento"""
        # Tiempo máximo de procesamiento: 5 minutos
        max_processing_time = 300
        timeout_limit = datetime.now() - timedelta(seconds=max_processing_time)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Obtener mensajes en procesamiento por demasiado tiempo
            cursor.execute('''
                SELECT id, retry_count FROM queue_messages
                WHERE state = ? AND updated_at < ?
            ''', (MessageState.PROCESSING.value, timeout_limit))
            
            timed_out = cursor.fetchall()
            
            for msg_id, retry_count in timed_out:
                # Decidir si hay que reintentar o marcar como fallido
                if retry_count < self.max_retries:
                    next_retry = datetime.now() + timedelta(seconds=self.retry_delay)
                    cursor.execute('''
                        UPDATE queue_messages
                        SET state = ?, updated_at = ?, retry_count = retry_count + 1,
                            next_retry_at = ?, error_message = ?, processing_id = NULL
                        WHERE id = ?
                    ''', (MessageState.RETRYING.value, datetime.now(), next_retry, 
                         "Tiempo de procesamiento excedido", msg_id))
                else:
                    cursor.execute('''
                        UPDATE queue_messages
                        SET state = ?, updated_at = ?, 
                            error_message = ?, processing_id = NULL
                        WHERE id = ?
                    ''', (MessageState.FAILED.value, datetime.now(), 
                         f"Máximo de reintentos alcanzado ({self.max_retries})", msg_id))
            
            conn.commit()
            
            if timed_out:
                logger.warning(f"Cola '{self.queue_name}': {len(timed_out)} mensajes en timeout")
    
    def _cleanup_old_messages(self):
        """Elimina mensajes antiguos completados o fallidos"""
        max_age = datetime.now() - timedelta(days=self.max_age_days)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM queue_messages
                WHERE (state = ? OR state = ?) AND updated_at < ?
            ''', (MessageState.COMPLETED.value, MessageState.FAILED.value, max_age))
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            if deleted_count > 0:
                logger.info(f"Cola '{self.queue_name}': eliminados {deleted_count} mensajes antiguos")
    
    def enqueue(self, topic, payload, message_id=None):
        """
        Encola un nuevo mensaje
        
        Args:
            topic: Categoría o tipo de mensaje
            payload: Contenido del mensaje (se guardará como JSON)
            message_id: ID opcional para el mensaje (se generará uno si no se proporciona)
            
        Returns:
            ID del mensaje encolado
        """
        message_id = message_id or str(uuid.uuid4())
        now = datetime.now()
        
        # Convertir payload a JSON si no es string
        if not isinstance(payload, str):
            payload = json.dumps(payload)
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO queue_messages
                (id, topic, payload, state, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (message_id, topic, payload, MessageState.PENDING.value, now, now))
            
            conn.commit()
            
        logger.debug(f"Cola '{self.queue_name}': mensaje {message_id} encolado en tópico {topic}")
        return message_id
    
    def dequeue(self, topics=None, batch_size=1, processing_id=None):
        """
        Obtiene mensajes pendientes de la cola para procesamiento
        
        Args:
            topics: Lista de tópicos a despachar (None para todos)
            batch_size: Número máximo de mensajes a obtener
            processing_id: Identificador opcional del procesador
            
        Returns:
            Lista de mensajes [{id, topic, payload, ...}]
        """
        processing_id = processing_id or str(uuid.uuid4())
        now = datetime.now()
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Construir consulta según tópicos seleccionados
            query = '''
                SELECT id, topic, payload, created_at, retry_count
                FROM queue_messages
                WHERE state = ?
            '''
            params = [MessageState.PENDING.value]
            
            if topics:
                placeholders = ','.join(['?'] * len(topics))
                query += f" AND topic IN ({placeholders})"
                params.extend(topics)
            
            query += " ORDER BY created_at ASC LIMIT ?"
            params.append(batch_size)
            
            # Obtener mensajes pendientes
            cursor.execute(query, params)
            messages = [{
                'id': row[0],
                'topic': row[1],
                'payload': row[2],
                'created_at': row[3],
                'retry_count': row[4]
            } for row in cursor.fetchall()]
            
            # Marcar mensajes como en procesamiento
            if messages:
                message_ids = [msg['id'] for msg in messages]
                placeholders = ','.join(['?'] * len(message_ids))
                
                cursor.execute(f'''
                    UPDATE queue_messages
                    SET state = ?, updated_at = ?, processing_id = ?
                    WHERE id IN ({placeholders})
                ''', [MessageState.PROCESSING.value, now, processing_id] + message_ids)
                
                conn.commit()
                
                logger.debug(f"Cola '{self.queue_name}': {len(messages)} mensajes despachados")
        
        # Deserializar payload JSON
        for msg in messages:
            try:
                msg['payload'] = json.loads(msg['payload'])
            except:
                # Mantener payload original si no es JSON válido
                pass
        
        return messages
    
    def ack(self, message_id):
        """
        Confirma el procesamiento exitoso de un mensaje
        
        Args:
            message_id: ID del mensaje procesado
            
        Returns:
            True si se actualizó correctamente, False si no
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE queue_messages
                SET state = ?, updated_at = ?
                WHERE id = ? AND state = ?
            ''', (MessageState.COMPLETED.value, datetime.now(), 
                 message_id, MessageState.PROCESSING.value))
            
            updated = cursor.rowcount > 0
            conn.commit()
            
            if updated:
                logger.debug(f"Cola '{self.queue_name}': mensaje {message_id} procesado correctamente")
            else:
                logger.warning(f"Cola '{self.queue_name}': mensaje {message_id} no encontrado para ACK")
                
        return updated
    
    def nack(self, message_id, error_message=None):
        """
        Indica que el procesamiento de un mensaje ha fallado
        
        Args:
            message_id: ID del mensaje fallido
            error_message: Descripción opcional del error
            
        Returns:
            True si se programó reintento, False si se marcó como fallido definitivamente
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Obtener información del mensaje
            cursor.execute('''
                SELECT retry_count FROM queue_messages
                WHERE id = ? AND state = ?
            ''', (message_id, MessageState.PROCESSING.value))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"Cola '{self.queue_name}': mensaje {message_id} no encontrado para NACK")
                return False
            
            retry_count = row[0]
            now = datetime.now()
            
            # Determinar si reintentamos o marcamos como fallido definitivo
            if retry_count < self.max_retries:
                # Calcular exponential backoff con jitter
                base_delay = self.retry_delay * (2 ** retry_count)
                jitter = random.uniform(0.8, 1.2)  # ±20% variación
                next_retry = now + timedelta(seconds=base_delay * jitter)
                
                cursor.execute('''
                    UPDATE queue_messages
                    SET state = ?, updated_at = ?, retry_count = retry_count + 1,
                        next_retry_at = ?, error_message = ?, processing_id = NULL
                    WHERE id = ?
                ''', (MessageState.RETRYING.value, now, next_retry, 
                     error_message or "Error desconocido", message_id))
                
                conn.commit()
                logger.info(f"Cola '{self.queue_name}': mensaje {message_id} programado para reintento {retry_count+1}/{self.max_retries}")
                return True
            else:
                # Marcar como fallido definitivamente
                cursor.execute('''
                    UPDATE queue_messages
                    SET state = ?, updated_at = ?, 
                        error_message = ?, processing_id = NULL
                    WHERE id = ?
                ''', (MessageState.FAILED.value, now, 
                     error_message or f"Máximo de reintentos alcanzado ({self.max_retries})", 
                     message_id))
                
                conn.commit()
                logger.warning(f"Cola '{self.queue_name}': mensaje {message_id} marcado como fallido definitivamente tras {self.max_retries} intentos")
                return False
    
    def get_stats(self):
        """Obtiene estadísticas de la cola"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Contar mensajes por estado
            cursor.execute('''
                SELECT state, COUNT(*) FROM queue_messages
                GROUP BY state
            ''')
            
            state_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Contar mensajes por tópico
            cursor.execute('''
                SELECT topic, COUNT(*) FROM queue_messages
                GROUP BY topic
            ''')
            
            topic_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Obtener edades (min/max/avg)
            cursor.execute('''
                SELECT 
                    MIN(julianday('now') - julianday(created_at)) * 24 * 60 as min_age_minutes,
                    MAX(julianday('now') - julianday(created_at)) * 24 * 60 as max_age_minutes,
                    AVG(julianday('now') - julianday(created_at)) * 24 * 60 as avg_age_minutes
                FROM queue_messages
                WHERE state IN (?, ?, ?)
            ''', (MessageState.PENDING.value, MessageState.PROCESSING.value, MessageState.RETRYING.value))
            
            age_row = cursor.fetchone()
            
            return {
                'name': self.queue_name,
                'counts': {
                    'total': sum(state_counts.values()),
                    'pending': state_counts.get(MessageState.PENDING.value, 0),
                    'processing': state_counts.get(MessageState.PROCESSING.value, 0),
                    'completed': state_counts.get(MessageState.COMPLETED.value, 0),
                    'failed': state_counts.get(MessageState.FAILED.value, 0),
                    'retrying': state_counts.get(MessageState.RETRYING.value, 0)
                },
                'topics': topic_counts,
                'age_minutes': {
                    'min': age_row[0] if age_row[0] is not None else 0,
                    'max': age_row[1] if age_row[1] is not None else 0,
                    'avg': age_row[2] if age_row[2] is not None else 0
                }
            }
    
    def purge(self, state=None):
        """
        Elimina mensajes de la cola
        
        Args:
            state: Estado de mensajes a eliminar (None para todos)
            
        Returns:
            Número de mensajes eliminados
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if state:
                cursor.execute('''
                    DELETE FROM queue_messages
                    WHERE state = ?
                ''', (state.value,))
            else:
                cursor.execute('DELETE FROM queue_messages')
            
            deleted_count = cursor.rowcount
            conn.commit()
            
            logger.info(f"Cola '{self.queue_name}': purgados {deleted_count} mensajes")
            return deleted_count


# Registro global de colas persistentes
class PersistentQueueRegistry:
    """Registro central de colas persistentes en la aplicación"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PersistentQueueRegistry, cls).__new__(cls)
            cls._instance.queues = {}
            cls._instance.lock = threading.RLock()
        return cls._instance
    
    def get(self, queue_name, create_if_missing=True, **kwargs):
        """
        Obtiene una cola por nombre o la crea si no existe
        
        Args:
            queue_name: Nombre de la cola
            create_if_missing: Si debe crear una nueva cola cuando no existe
            **kwargs: Parámetros para la creación de una nueva cola
            
        Returns:
            Una instancia de PersistentQueue
        """
        with self.lock:
            if queue_name not in self.queues and create_if_missing:
                self.queues[queue_name] = PersistentQueue(queue_name, **kwargs)
                # Iniciar mantenimiento automáticamente
                self.queues[queue_name].start_maintenance()
            
            return self.queues.get(queue_name)
    
    def get_all_stats(self):
        """Obtiene estadísticas de todas las colas registradas"""
        stats = {}
        with self.lock:
            for name, queue in self.queues.items():
                stats[name] = queue.get_stats()
        return stats
    
    def stop_all(self):
        """Detiene el mantenimiento de todas las colas"""
        with self.lock:
            for queue in self.queues.values():
                queue.stop_maintenance()
                
    def remove(self, queue_name):
        """Elimina una cola del registro"""
        with self.lock:
            if queue_name in self.queues:
                self.queues[queue_name].stop_maintenance()
                del self.queues[queue_name]


# Obtener instancia del registro
def get_persistent_queue(queue_name, **kwargs):
    """Función de ayuda para obtener una cola persistente del registro"""
    return PersistentQueueRegistry().get(queue_name, **kwargs)