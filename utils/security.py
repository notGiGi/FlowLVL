import re
import logging
import hashlib
import hmac
import base64
import os

logger = logging.getLogger('security')

class CommandValidator:
    """Validador de comandos para evitar inyección y comandos peligrosos"""
    
    def __init__(self):
        # Lista de patrones de comandos prohibidos
        self.forbidden_patterns = [
            r'rm\s+-rf', r';\s*rm', r'&&\s*rm',  # Comandos destructivos
            r'wget\s+http', r'curl\s+http',      # Descarga desde Internet
            r'>\s*/etc/', r'>>\s*/etc/',          # Modificación de archivos del sistema
            r';\s*wget', r';\s*curl',             # Comandos encadenados con descarga
            r'`.*`', r'\$\(.*\)',                 # Sustitución de comandos
            r'mysql\s+-u\s+root', r'psql\s+-U\s+postgres',  # Acceso directo a bases de datos
            r'mv\s+\/\w+', r'cp\s+\/\w+',         # Operaciones sobre directorios raíz
        ]
        
        # Lista de comandos permitidos para Kubernetes
        self.allowed_k8s_commands = [
            'kubectl rollout restart deployment',
            'kubectl scale deployment',
            'kubectl scale statefulset',
            'kubectl exec',
            'kubectl get',
            'kubectl logs',
            'kubectl describe'
        ]
    
    def is_safe_command(self, command):
        """
        Verifica si un comando es seguro para ejecutar
        
        Args:
            command: Comando a validar
            
        Returns:
            (bool, str): (es_seguro, mensaje)
        """
        # Verificar patrones prohibidos
        for pattern in self.forbidden_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, f"Comando contiene patrón prohibido: {pattern}"
        
        # Verificar que sea un comando Kubernetes permitido
        is_allowed = False
        for allowed_cmd in self.allowed_k8s_commands:
            if command.strip().startswith(allowed_cmd):
                is_allowed = True
                break
        
        if not is_allowed:
            return False, "Comando no está en la lista de comandos permitidos"
        
        # Verificar longitud máxima del comando
        if len(command) > 500:
            return False, "Comando excede longitud máxima permitida"
        
        return True, "Comando validado"

class AccessControl:
    """Control de acceso para operaciones sensibles"""
    
    def __init__(self, config=None):
        self.config = config or {}
        self.secret_key = self.config.get('secret_key', os.environ.get('ACTION_SECRET_KEY', 'default_key'))
        
        # Niveles de operación y permisos requeridos
        self.operation_levels = {
            'read': 0,            # Solo lectura
            'recommend': 1,       # Recomendar acciones
            'execute_low': 2,     # Ejecutar acciones de baja prioridad
            'execute_medium': 3,  # Ejecutar acciones de prioridad media
            'execute_high': 4,    # Ejecutar acciones de alta prioridad
            'execute_all': 5      # Ejecutar cualquier acción
        }
    
    def is_operation_allowed(self, token, operation, service_id=None):
        """
        Verifica si una operación está permitida con el token proporcionado
        
        Args:
            token: Token de autorización
            operation: Tipo de operación 
            service_id: ID del servicio (opcional)
            
        Returns:
            bool: True si la operación está permitida
        """
        try:
            # En producción real, esto debería validar contra una base de datos
            # o servicio de autorización como JWT, OAuth, etc.
            
            # Para este ejemplo, usamos HMAC para validar el token
            expected_level = self.operation_levels.get(operation, 999)
            
            # Decodificar token
            try:
                decoded = base64.b64decode(token).decode('utf-8')
                parts = decoded.split(':')
                if len(parts) != 3:
                    logger.warning(f"Token mal formado: {token}")
                    return False
                
                token_service, token_level, token_hmac = parts
                token_level = int(token_level)
            except Exception as e:
                logger.warning(f"Error al decodificar token: {str(e)}")
                return False
            
            # Verificar que sea para el servicio correcto
            if service_id and token_service != '*' and token_service != service_id:
                logger.warning(f"Token no válido para servicio {service_id}")
                return False
            
            # Verificar nivel de acceso
            if token_level < expected_level:
                logger.warning(f"Nivel de acceso insuficiente: {token_level} < {expected_level}")
                return False
            
            # Verificar HMAC
            message = f"{token_service}:{token_level}".encode('utf-8')
            expected_hmac = hmac.new(
                self.secret_key.encode('utf-8'),
                message,
                hashlib.sha256
            ).hexdigest()
            
            if token_hmac != expected_hmac:
                logger.warning("HMAC inválido")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error en validación de acceso: {str(e)}")
            return False
    
    def create_token(self, service_id, level):
        """
        Crea un token de acceso para un servicio y nivel
        
        Args:
            service_id: ID del servicio ('*' para todos)
            level: Nivel de acceso (0-5)
            
        Returns:
            str: Token de acceso
        """
        try:
            message = f"{service_id}:{level}".encode('utf-8')
            signature = hmac.new(
                self.secret_key.encode('utf-8'),
                message,
                hashlib.sha256
            ).hexdigest()
            
            token = f"{service_id}:{level}:{signature}"
            return base64.b64encode(token.encode('utf-8')).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Error al crear token: {str(e)}")
            return None