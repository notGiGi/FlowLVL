import redis
import json
import logging
import time
import inspect
from functools import wraps

logger = logging.getLogger('distributed_cache')

class DistributedCache:
    def __init__(self, redis_host='redis', redis_port=6379, redis_db=0, prefix='predictive_maintenance'):
        """
        Implementa una caché distribuida usando Redis
        
        Args:
            redis_host: Host de Redis
            redis_port: Puerto de Redis
            redis_db: Base de datos de Redis
            prefix: Prefijo para las claves de Redis
        """
        self.prefix = prefix
        self.ttl = 3600  # TTL default de 1 hora
        
        try:
            self.redis = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                socket_timeout=5,
                socket_connect_timeout=5,
                retry_on_timeout=True
            )
            logger.info(f"Caché distribuida inicializada: {redis_host}:{redis_port}")
        except Exception as e:
            logger.error(f"Error al conectar a Redis: {str(e)}")
            self.redis = None
    
    def get_key(self, key):
        """Genera una clave con prefijo para Redis"""
        return f"{self.prefix}:{key}"
    
    def get(self, key, default=None):
        """Obtiene un valor de la caché"""
        if not self.redis:
            return default
        
        try:
            value = self.redis.get(self.get_key(key))
            if value:
                return json.loads(value)
            return default
        except Exception as e:
            logger.warning(f"Error al obtener valor de caché para {key}: {str(e)}")
            return default
    
    def set(self, key, value, ttl=None):
        """Almacena un valor en la caché"""
        if not self.redis:
            return False
        
        try:
            full_key = self.get_key(key)
            serialized = json.dumps(value)
            return self.redis.set(full_key, serialized, ex=ttl or self.ttl)
        except Exception as e:
            logger.warning(f"Error al almacenar en caché para {key}: {str(e)}")
            return False
    
    def delete(self, key):
        """Elimina un valor de la caché"""
        if not self.redis:
            return False
        
        try:
            return self.redis.delete(self.get_key(key)) > 0
        except Exception as e:
            logger.warning(f"Error al eliminar valor de caché para {key}: {str(e)}")
            return False
    
    def invalidate_pattern(self, pattern):
        """Invalida todas las claves que coinciden con un patrón"""
        if not self.redis:
            return 0
        
        try:
            full_pattern = self.get_key(pattern + '*')
            keys = self.redis.keys(full_pattern)
            if keys:
                return self.redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Error al invalidar patrón {pattern}: {str(e)}")
            return 0


def cached(ttl=3600, key_format=None):
    """
    Decorador para cachear resultados de funciones
    
    Args:
        ttl: Tiempo de vida en segundos
        key_format: Formato de clave (usa nombres de args si no se especifica)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Conseguir instancia de caché
            # Asumimos que el primer arg es self y tiene un atributo cache
            cache = getattr(args[0], 'cache', None)
            if not cache or not isinstance(cache, DistributedCache):
                return func(*args, **kwargs)
            
            # Generar clave de caché
            if key_format:
                # Crear dict con args y kwargs combinados
                all_args = {}
                if args:
                    # Obtener nombres de parámetros de la función
                    arg_names = inspect.getfullargspec(func).args
                    for i, arg in enumerate(args):
                        if i < len(arg_names):
                            all_args[arg_names[i]] = arg
                
                # Añadir kwargs
                all_args.update(kwargs)
                
                # Formatear clave
                cache_key = key_format.format(**all_args)
            else:
                # Generar clave basada en nombre de función y argumentos
                arg_str = ':'.join([str(arg) for arg in args[1:]])  # excluir self
                kwarg_str = ':'.join([f"{k}={v}" for k, v in sorted(kwargs.items())])
                cache_key = f"{func.__name__}:{arg_str}:{kwarg_str}"
            
            # Intentar obtener de caché
            cached_result = cache.get(cache_key)
            if cached_result is not None:
                return cached_result
            
            # Si no está en caché, ejecutar función
            result = func(*args, **kwargs)
            
            # Almacenar resultado en caché
            cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    
    return decorator