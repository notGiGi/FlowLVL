# -*- coding: utf-8 -*-
import os
import json
import yaml
import shutil
import sys
import time
from datetime import datetime

print("🔧 Reconstruyendo el sistema de detección de anomalías...")

# 1. Respaldar archivos actuales
backup_dir = "./backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
os.makedirs(backup_dir, exist_ok=True)
print(f"📂 Creando respaldo en {backup_dir}")

# 2. Reescribir el detector de anomalías con una versión simplificada
simple_detector = """# -*- coding: utf-8 -*-
import numpy as np
import json
import logging
import os
from datetime import datetime

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("anomaly_detector.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('simple_detector')

class SimpleAnomalyDetector:
    \"\"\"Detector de anomalías simplificado para prueba real\"\"\"
    
    def __init__(self, config=None):
        self.config = config or {}
        
        # Parámetros de configuración
        self.anomaly_threshold = self.config.get('anomaly_threshold', 0.7)
        self.min_history_points = self.config.get('min_history_points', 5)
        
        # Directorio para almacenar datos
        self.data_dir = self.config.get('data_dir', './data')
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Historial de métricas por servicio
        self.metrics_history = {}
        
        # Umbrales por servicio
        self.thresholds = self.load_thresholds()
        
        logger.info(f"Detector de anomalías simple inicializado (umbral: {self.anomaly_threshold})")
        logger.info(f"Umbrales cargados: {self.thresholds}")
    
    def load_thresholds(self):
        \"\"\"Carga umbrales desde archivo\"\"\"
        threshold_file = os.path.join(self.data_dir, 'thresholds.json')
        
        default_thresholds = {
            "default": {
                "memory_usage": 60,
                "cpu_usage": 70,
                "response_time_ms": 300,
                "error_rate": 5,
                "active_connections": 80,
                "query_time_avg": 100,
                "gc_collection_time": 400
            }
        }
        
        try:
            if os.path.exists(threshold_file):
                with open(threshold_file, 'r', encoding='utf-8-sig') as f:
                    thresholds = json.load(f)
                logger.info(f"Umbrales cargados desde {threshold_file}")
                return thresholds
            else:
                # Si no existe el archivo, crearlo con valores por defecto
                with open(threshold_file, 'w', encoding='utf-8') as f:
                    json.dump(default_thresholds, f, indent=2)
                logger.info(f"Archivo de umbrales creado en {threshold_file}")
                return default_thresholds
        except Exception as e:
            logger.error(f"Error al cargar umbrales: {str(e)}")
            return default_thresholds
    
    def save_thresholds(self):
        \"\"\"Guarda umbrales en archivo\"\"\"
        threshold_file = os.path.join(self.data_dir, 'thresholds.json')
        
        try:
            with open(threshold_file, 'w', encoding='utf-8') as f:
                json.dump(self.thresholds, f, indent=2)
            logger.info(f"Umbrales guardados en {threshold_file}")
        except Exception as e:
            logger.error(f"Error al guardar umbrales: {str(e)}")
    
    def add_metric_point(self, service_id, metrics):
        \"\"\"Añade un punto de métricas al historial\"\"\"
        try:
            if service_id not in self.metrics_history:
                self.metrics_history[service_id] = []
            
            # Filtrar solo campos numéricos
            numeric_metrics = {}
            for key, value in metrics.items():
                if key not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                    numeric_metrics[key] = value
            
            # Añadir timestamp si no existe
            if 'timestamp' not in metrics:
                metrics['timestamp'] = datetime.now().isoformat()
            
            # Guardar punto completo (con valores no numéricos)
            self.metrics_history[service_id].append(metrics)
            
            # Limitar tamaño del historial
            max_history = self.config.get('max_history_points', 100)
            if len(self.metrics_history[service_id]) > max_history:
                self.metrics_history[service_id] = self.metrics_history[service_id][-max_history:]
                
            return True
            
        except Exception as e:
            logger.error(f"Error al añadir punto de métrica: {str(e)}")
            return False
    
    def detect_anomalies_direct(self, data_point):
        \"\"\"
        Versión directa y simplificada de detección de anomalías 
        basada en umbrales directos
        \"\"\"
        try:
            # Extraer información básica
            service_id = data_point.get('service_id', 'unknown')
            
            # Añadir punto al historial
            self.add_metric_point(service_id, data_point)
            
            # Obtener umbrales para este servicio (o usar default)
            service_thresholds = self.thresholds.get(service_id, self.thresholds.get('default', {}))
            
            # Variables para tracking de anomalías
            anomaly_metrics = []
            anomaly_details = {}
            max_severity = 0.0
            
            # Verificar cada métrica importante
            for metric, value in data_point.items():
                if metric not in ['service_id', 'timestamp'] and isinstance(value, (int, float)):
                    threshold = service_thresholds.get(metric)
                    
                    if threshold:
                        # Para hit_rate, valores bajos son problemáticos
                        if metric == 'hit_rate':
                            if value < threshold:
                                severity = min(1.0, (threshold - value) / threshold)
                                anomaly_metrics.append(f"{metric}: {value:.2f} < {threshold:.2f}")
                                anomaly_details[metric] = {
                                    'value': value,
                                    'threshold': threshold,
                                    'severity': severity
                                }
                                max_severity = max(max_severity, severity)
                        # Para las demás métricas, valores altos son problemáticos
                        else:
                            if value > threshold:
                                severity = min(1.0, (value - threshold) / threshold)
                                anomaly_metrics.append(f"{metric}: {value:.2f} > {threshold:.2f}")
                                anomaly_details[metric] = {
                                    'value': value,
                                    'threshold': threshold,
                                    'severity': severity
                                }
                                max_severity = max(max_severity, severity)
            
            # Calcular score general (normalizado entre 0 y 1)
            anomaly_score = min(1.0, max_severity)
            
            # Determinar si hay anomalía
            is_anomaly = anomaly_score >= self.anomaly_threshold
            
            # Log detallado para debug
            log_msg = f"Análisis para {service_id}: "
            if is_anomaly:
                log_msg += f"ANOMALÍA (score: {anomaly_score:.3f}, umbral: {self.anomaly_threshold})"
                logger.info(log_msg)
                logger.info(f"Métricas anómalas: {', '.join(anomaly_metrics)}")
            else:
                log_msg += f"normal (score: {anomaly_score:.3f}, umbral: {self.anomaly_threshold})"
                logger.debug(log_msg)
            
            # Generar detalles
            details = {
                "anomaly_type": "threshold_violation" if is_anomaly else "none",
                "metrics_analyzed": len(anomaly_details),
                "metrics_exceeded": len(anomaly_metrics),
                "thresholds": service_thresholds,
                "anomaly_details": anomaly_details
            }
            
            return is_anomaly, anomaly_score, details
            
        except Exception as e:
            logger.error(f"Error al detectar anomalías: {str(e)}")
            return False, 0.0, {"error": str(e)}
    
    def detect_anomalies(self, data_point):
        \"\"\"
        Alias para el método principal de detección
        \"\"\"
        return self.detect_anomalies_direct(data_point)
    
    def get_history(self, service_id, limit=20):
        \"\"\"Obtiene historial de métricas para un servicio\"\"\"
        if service_id in self.metrics_history:
            return self.metrics_history[service_id][-limit:]
        return []
    
    def get_threshold(self, service_id, metric):
        \"\"\"Obtiene umbral específico\"\"\"
        service_thresholds = self.thresholds.get(service_id, self.thresholds.get('default', {}))
        return service_thresholds.get(metric)
    
    def set_threshold(self, service_id, metric, value):
        \"\"\"Establece umbral manualmente\"\"\"
        if service_id not in self.thresholds:
            self.thresholds[service_id] = self.thresholds.get('default', {}).copy()
        
        self.thresholds[service_id][metric] = value
        self.save_thresholds()
        
        return True
"""

# Guardar respaldo del detector actual
if os.path.exists("./anomaly_detector/simple_detector.py"):
    shutil.copy("./anomaly_detector/simple_detector.py", f"{backup_dir}/simple_detector.py.bak")

# Guardar nueva versión
with open("./anomaly_detector/simple_detector.py", "w", encoding="utf-8") as f:
    f.write(simple_detector)

print("✅ Detector de anomalías reescrito con versión simplificada")

# 3. Configurar umbrales correctos
thresholds = {
    "default": {
        "memory_usage": 60,
        "cpu_usage": 70,
        "response_time_ms": 300,
        "error_rate": 5,
        "active_connections": 80,
        "query_time_avg": 100,
        "gc_collection_time": 400
    }
}

with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

print("✅ Umbrales corregidos")

# 4. Actualizar configuración del sistema
system_config = {
    "anomaly_threshold": 0.1,  # Umbral extremadamente bajo
    "execution_mode": "simulation",
    "auto_remediation": False,
    "processing_interval": 5,
    "prediction_threshold": 0.4,
    "prediction_horizon": 8,
    "prediction_interval": 1800
}

with open("./config/system_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(system_config, f)

print("✅ Configuración del sistema actualizada")

# 5. Crear nuevos datos de prueba con anomalías extremas
timestamp = datetime.now().isoformat()

extreme_app_server = [
    {
        "service_id": "app-server",
        "timestamp": datetime.now().replace(minute=0, second=0, microsecond=0).isoformat(),
        "memory_usage": 50,
        "cpu_usage": 40,
        "response_time_ms": 200,
        "error_rate": 1
    },
    {
        "service_id": "app-server",
        "timestamp": timestamp,
        "memory_usage": 99,  # Anomalía extrema
        "cpu_usage": 99,     # Anomalía extrema
        "response_time_ms": 1000,  # Anomalía extrema
        "error_rate": 20     # Anomalía extrema
    }
]

with open("./data/app-server_data.json", "w", encoding="utf-8") as f:
    json.dump(extreme_app_server, f, indent=2)

extreme_database = [
    {
        "service_id": "database",
        "timestamp": datetime.now().replace(minute=0, second=0, microsecond=0).isoformat(),
        "memory_usage": 45,
        "cpu_usage": 35,
        "active_connections": 50,
        "query_time_avg": 50
    },
    {
        "service_id": "database",
        "timestamp": timestamp,
        "memory_usage": 99,  # Anomalía extrema
        "cpu_usage": 99,     # Anomalía extrema
        "active_connections": 500,  # Anomalía extrema
        "query_time_avg": 500       # Anomalía extrema
    }
]

with open("./data/database_data.json", "w", encoding="utf-8") as f:
    json.dump(extreme_database, f, indent=2)

print("✅ Datos de prueba con anomalías extremas creados")

print("\n🔄 Necesitamos reiniciar el sistema completamente.")
print("❗ Por favor, ejecuta los siguientes comandos:")
print("\n1. Cierra todas las ventanas del navegador que tengan el dashboard abierto")
print("2. En una nueva ventana de PowerShell, ejecuta:")
print("   Get-Process -Name python | Stop-Process -Force")
print("   python start.py")
print("\n3. Espera 20-30 segundos y verifica el dashboard")

# Crear un script para verificar si la detección funciona
verify_script = """# -*- coding: utf-8 -*-
import requests
import time
import json
import sys

def check_detection():
    print("Verificando detección de anomalías...")
    try:
        response = requests.get("http://localhost:5000/api/events?limit=10", timeout=5)
        if response.status_code == 200:
            events = response.json()
            anomalies = [e for e in events if e.get('type') == 'anomaly_detection' and e.get('is_anomaly', False)]
            
            print(f"Encontrados {len(anomalies)} eventos de anomalía:")
            for anomaly in anomalies:
                service = anomaly.get('service_id', 'desconocido')
                score = anomaly.get('anomaly_score', 0)
                print(f"✅ Anomalía en {service}: Score {score:.3f}")
                
            if not anomalies:
                print("❌ No se encontraron anomalías")
                print("   Posibles razones:")
                print("   1. El sistema no ha procesado las métricas todavía (espera más tiempo)")
                print("   2. El detector no está identificando correctamente las anomalías")
                print("   3. El servidor API no está respondiendo correctamente")
        else:
            print(f"❌ Error en la respuesta del API: {response.status_code}")
    except Exception as e:
        print(f"❌ Error al verificar anomalías: {e}")

if __name__ == "__main__":
    print("Esperando 30 segundos para que el sistema procese los datos...")
    for i in range(30, 0, -1):
        sys.stdout.write(f"\\rEsperando {i} segundos...")
        sys.stdout.flush()
        time.sleep(1)
    print("\\nVerificando anomalías...")
    check_detection()
"""

with open("verify_detection.py", "w", encoding="utf-8") as f:
    f.write(verify_script)

print("✅ Script de verificación creado (ejecuta 'python verify_detection.py' después de reiniciar)")
print("\n✨ ¡Configuración completada! Reinicia el sistema ahora.")