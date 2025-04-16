# common/circuit_breaker.py

import time
import threading
import logging
from enum import Enum
from functools import wraps
import random

logger = logging.getLogger('circuit_breaker')

class CircuitState(Enum):
    CLOSED = 'CLOSED'     # Estado normal, operaciones permitidas
    OPEN = 'OPEN'         # Estado de fallo, operaciones bloqueadas
    HALF_OPEN = 'HALF_OPEN'  # Estado de prueba, permitiendo operaciones limitadas

class CircuitBreaker:
    """
    Implementación de Circuit Breaker para mejorar resiliencia de operaciones
    externas en el sistema predictivo.
    """
    
    def __init__(self, name, failure_threshold=5, recovery_timeout=30, 
                 half_open_max_calls=3, failure_window=60):
        """
        Inicializa un nuevo Circuit Breaker
        
        Args:
            name: Nombre identificativo del circuit breaker
            failure_threshold: Número de fallos consecutivos para abrir el circuito
            recovery_timeout: Tiempo en segundos antes de pasar a estado HALF_OPEN
            half_open_max_calls: Número máximo de llamadas en estado HALF_OPEN
            failure_window: Ventana de tiempo en segundos para contar fallos
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.failure_window = failure_window
        
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = 0
        self.half_open_calls = 0
        self.last_state_change = time.time()
        
        self.lock = threading.RLock()
        
        logger.info(f"Circuit Breaker '{name}' inicializado")
    
    def __call__(self, func):
        """Permite usar el circuit breaker como decorador de funciones"""
        @wraps(func)
        def wrapper(*args, **kwargs):
            return self.execute(lambda: func(*args, **kwargs))
        return wrapper
    
    def execute(self, func):
        """
        Ejecuta una función protegida por el circuit breaker
        
        Args:
            func: Función a ejecutar
            
        Returns:
            El resultado de la función si se ejecuta correctamente
            
        Raises:
            CircuitBreakerOpenError: Si el circuito está abierto
            Exception: Cualquier excepción que ocurra durante la ejecución
        """
        self.state_transition()
        
        with self.lock:
            if self.state == CircuitState.OPEN:
                logger.warning(f"Circuit Breaker '{self.name}' está abierto - operación bloqueada")
                raise CircuitBreakerOpenError(f"Circuit Breaker '{self.name}' está abierto")
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.half_open_max_calls:
                    logger.warning(f"Circuit Breaker '{self.name}' en HALF_OPEN excedió máximo de llamadas - operación bloqueada")
                    raise CircuitBreakerOpenError(f"Circuit Breaker '{self.name}' en HALF_OPEN excedió máximo de llamadas")
                
                self.half_open_calls += 1
        
        try:
            result = func()
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise
    
    def state_transition(self):
        """Gestiona las transiciones de estado automáticas del circuit breaker"""
        with self.lock:
            # Eliminar fallos antiguos
            current_time = time.time()
            if (current_time - self.last_failure_time) > self.failure_window:
                old_failures = self.failures
                self.failures = 0
                if old_failures > 0:
                    logger.debug(f"Circuit Breaker '{self.name}' - reseteando contador de fallos por ventana de tiempo")
            
            # Transición de OPEN a HALF_OPEN
            if (self.state == CircuitState.OPEN and 
                (current_time - self.last_state_change) >= self.recovery_timeout):
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.last_state_change = current_time
                logger.info(f"Circuit Breaker '{self.name}' transitando de OPEN a HALF_OPEN")
    
    def record_success(self):
        """Registra una operación exitosa"""
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                # Regresar a estado normal
                self.state = CircuitState.CLOSED
                self.failures = 0
                self.half_open_calls = 0
                self.last_state_change = time.time()
                logger.info(f"Circuit Breaker '{self.name}' restablecido a CLOSED tras operación exitosa")
            
            # En estado CLOSED, simplemente reseteamos fallos
            if self.state == CircuitState.CLOSED:
                self.failures = 0
    
    def record_failure(self):
        """Registra un fallo de operación"""
        with self.lock:
            self.failures += 1
            self.last_failure_time = time.time()
            
            # En CLOSED, abrir el circuito si se supera el umbral
            if self.state == CircuitState.CLOSED and self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
                logger.warning(f"Circuit Breaker '{self.name}' abierto tras {self.failures} fallos consecutivos")
            
            # En HALF_OPEN, volver a abrir ante cualquier fallo
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.last_state_change = time.time()
                logger.warning(f"Circuit Breaker '{self.name}' volvió a OPEN tras fallo en prueba")
    
    def reset(self):
        """Resetea el circuit breaker a su estado inicial"""
        with self.lock:
            self.state = CircuitState.CLOSED
            self.failures = 0
            self.last_failure_time = 0
            self.half_open_calls = 0
            self.last_state_change = time.time()
            logger.info(f"Circuit Breaker '{self.name}' reseteado manualmente")
    
    def force_open(self):
        """Fuerza el circuit breaker a estado abierto"""
        with self.lock:
            self.state = CircuitState.OPEN
            self.last_state_change = time.time()
            logger.warning(f"Circuit Breaker '{self.name}' forzado a estado OPEN")
    
    def get_state(self):
        """Obtiene el estado actual del circuit breaker"""
        return {
            'name': self.name,
            'state': self.state.value,
            'failures': self.failures,
            'last_failure': self.last_failure_time,
            'last_state_change': self.last_state_change,
            'half_open_calls': self.half_open_calls
        }


class CircuitBreakerOpenError(Exception):
    """Excepción lanzada cuando se intenta ejecutar una operación con el circuito abierto"""
    pass


# Gestor global de circuit breakers
class CircuitBreakerRegistry:
    """Registro central de circuit breakers en la aplicación"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(CircuitBreakerRegistry, cls).__new__(cls)
            cls._instance.breakers = {}
            cls._instance.lock = threading.RLock()
        return cls._instance
    
    def get(self, name, create_if_missing=True, **kwargs):
        """
        Obtiene un circuit breaker por nombre o lo crea si no existe
        
        Args:
            name: Nombre del circuit breaker
            create_if_missing: Si debe crear un nuevo circuit breaker cuando no existe
            **kwargs: Parámetros para la creación de un nuevo circuit breaker
            
        Returns:
            Una instancia de CircuitBreaker
        """
        with self.lock:
            if name not in self.breakers and create_if_missing:
                self.breakers[name] = CircuitBreaker(name, **kwargs)
            
            return self.breakers.get(name)
    
    def get_all_states(self):
        """Obtiene el estado de todos los circuit breakers registrados"""
        states = {}
        with self.lock:
            for name, breaker in self.breakers.items():
                states[name] = breaker.get_state()
        return states
    
    def reset_all(self):
        """Resetea todos los circuit breakers"""
        with self.lock:
            for breaker in self.breakers.values():
                breaker.reset()
                
    def remove(self, name):
        """Elimina un circuit breaker del registro"""
        with self.lock:
            if name in self.breakers:
                del self.breakers[name]


# Obtener instancia del registro
def get_circuit_breaker(name, **kwargs):
    """Función de ayuda para obtener un circuit breaker del registro"""
    return CircuitBreakerRegistry().get(name, **kwargs)


# Decorador para funciones
def circuit_breaker(name=None, **kwargs):
    """
    Decorador para proteger funciones con un circuit breaker
    
    Args:
        name: Nombre del circuit breaker (opcional, se generará uno basado en la función)
        **kwargs: Parámetros adicionales para el circuit breaker
        
    Returns:
        Decorador que protege la función con un circuit breaker
    """
    def decorator(func):
        cb_name = name or f"{func.__module__}.{func.__name__}"
        cb = get_circuit_breaker(cb_name, **kwargs)
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            return cb.execute(lambda: func(*args, **kwargs))
        
        return wrapper
    
    return decorator