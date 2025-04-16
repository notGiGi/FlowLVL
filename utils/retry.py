import time
import random
import logging
from functools import wraps

logger = logging.getLogger('retry_utils')

def retry_with_backoff(max_retries=5, initial_delay=1, backoff_factor=2, max_delay=60):
    """
    Decorador que reintenta una función con backoff exponencial
    
    Args:
        max_retries: Número máximo de reintentos
        initial_delay: Tiempo inicial de espera en segundos
        backoff_factor: Factor de incremento en cada reintento
        max_delay: Tiempo máximo de espera en segundos
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            retry_count = 0
            delay = initial_delay
            
            while retry_count < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        logger.error(f"Máximo de reintentos ({max_retries}) alcanzado. Error: {str(e)}")
                        raise
                    
                    # Añadir jitter para evitar sincronización en entornos distribuidos
                    jitter = random.uniform(0, 0.1 * delay)
                    actual_delay = min(delay + jitter, max_delay)
                    
                    logger.warning(f"Error en {func.__name__}, reintentando en {actual_delay:.2f}s. "
                                  f"Intento {retry_count}/{max_retries}. Error: {str(e)}")
                    
                    time.sleep(actual_delay)
                    delay = min(delay * backoff_factor, max_delay)
        
        return wrapper
    return decorator