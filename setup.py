# -*- coding: utf-8 -*-
import os
import json
import shutil
from datetime import datetime

print("Configurando el sistema de mantenimiento predictivo...")

# 1. Limpiar datos existentes para evitar problemas
data_dir = "./data"
if os.path.exists(data_dir):
    print("Limpiando directorio de datos...")
    for filename in os.listdir(data_dir):
        if filename.endswith(".json"):
            os.remove(os.path.join(data_dir, filename))
else:
    os.makedirs(data_dir)

# 2. Crear archivo de políticas de acción correcto
action_policies = {
    "web-service": {
        "description": "Políticas para servicios web",
        "actions": {
            "memory_leak_restart": {
                "description": "Reinicia el servicio para resolver fuga de memoria",
                "remediation": {
                    "type": "command",
                    "command": "echo Simulando reinicio para ${service_id}"
                },
                "conditions": {
                    "metrics": {
                        "memory_usage": "> 70",
                        "gc_collection_time": "> 300"
                    },
                    "anomaly_score": "> 0.6"
                },
                "priority": "high"
            }
        }
    },
    "generic_web_service": {
        "description": "Políticas genéricas para servicios web",
        "actions": {
            "memory_restart": {
                "description": "Reinicia el servicio para resolver problemas de memoria",
                "remediation": {
                    "type": "command",
                    "command": "echo Simulando reinicio para ${service_id}"
                },
                "conditions": {
                    "metrics": {
                        "memory_usage": "> 80"
                    },
                    "anomaly_score": "> 0.6"
                },
                "priority": "high"
            }
        }
    }
}

print("Creando archivo de políticas...")
with open("./config/action_policies.json", "w", encoding="utf-8") as f:
    json.dump(action_policies, f, indent=2)

# 3. Configurar el colector para usar archivos locales
collector_config = {
    "collection_interval": 60,
    "services": [
        {
            "service_id": "app-server",
            "endpoint_type": "file",
            "endpoint": "file://./data/app-server_data.json",
            "metrics_map": {
                "memory_usage": "memory_usage",
                "cpu_usage": "cpu_usage",
                "response_time_ms": "response_time_ms",
                "error_rate": "error_rate"
            }
        },
        {
            "service_id": "database",
            "endpoint_type": "file",
            "endpoint": "file://./data/database_data.json",
            "metrics_map": {
                "memory_usage": "memory_usage",
                "cpu_usage": "cpu_usage",
                "active_connections": "active_connections",
                "query_time_avg": "query_time_avg"
            }
        }
    ]
}

print("Creando configuración del colector...")
with open("./config/collector_config.yaml", "w", encoding="utf-8") as f:
    import yaml
    yaml.dump(collector_config, f)

# 4. Crear datos de ejemplo para app-server
app_server_data = []
base_timestamp = datetime.now()

# Crear puntos históricos normales
for i in range(15):
    hour = i
    timestamp = base_timestamp.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
    
    # Valores normales con pequeña tendencia creciente
    memory = 50 + (i * 0.5)
    cpu = 40 + (i * 0.3)
    response_time = 180 + (i * 2)
    error_rate = 0.5 + (i * 0.05)
    
    app_server_data.append({
        "service_id": "app-server",
        "timestamp": timestamp,
        "memory_usage": memory,
        "cpu_usage": cpu,
        "response_time_ms": response_time,
        "error_rate": error_rate
    })

# Añadir punto con anomalía
anomaly_timestamp = base_timestamp.replace(hour=16, minute=0, second=0, microsecond=0).isoformat()
app_server_data.append({
    "service_id": "app-server",
    "timestamp": anomaly_timestamp,
    "memory_usage": 90.5,
    "cpu_usage": 95.2,
    "response_time_ms": 750,
    "error_rate": 8.5
})

print("Creando datos de ejemplo para app-server...")
with open("./data/app-server_data.json", "w", encoding="utf-8") as f:
    json.dump(app_server_data, f, indent=2)

# 5. Crear datos de ejemplo para database
database_data = []

# Crear puntos históricos normales
for i in range(15):
    hour = i
    timestamp = base_timestamp.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
    
    # Valores normales con pequeña tendencia creciente
    memory = 45 + (i * 0.4)
    cpu = 35 + (i * 0.2)
    connections = 50 + (i * 1)
    query_time = 50 + (i * 0.5)
    
    database_data.append({
        "service_id": "database",
        "timestamp": timestamp,
        "memory_usage": memory,
        "cpu_usage": cpu,
        "active_connections": connections,
        "query_time_avg": query_time
    })

print("Creando datos de ejemplo para database...")
with open("./data/database_data.json", "w", encoding="utf-8") as f:
    json.dump(database_data, f, indent=2)

# 6. Crear umbrales
thresholds = {
    "default": {
        "memory_usage": 70,
        "cpu_usage": 80,
        "response_time_ms": 300,
        "error_rate": 3,
        "active_connections": 100,
        "query_time_avg": 100
    }
}

print("Creando umbrales predeterminados...")
with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

# 7. Modificar la configuración del sistema
system_config = {
    "anomaly_threshold": 0.6,
    "execution_mode": "simulation",
    "auto_remediation": False,
    "processing_interval": 10,
    "prediction_threshold": 0.6,
    "prediction_horizon": 8,
    "prediction_interval": 1800
}

print("Actualizando configuración del sistema...")
with open("./config/system_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(system_config, f)

# 8. Crear script de inicio simplificado
start_script = """# -*- coding: utf-8 -*-
import subprocess
import os
import time
import webbrowser
import sys

def run_command(command, wait=True):
    if wait:
        subprocess.call(command, shell=True)
    else:
        if os.name == 'nt':  # Windows
            subprocess.Popen(command, shell=True)
        else:  # Linux/Mac
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Iniciando sistema de mantenimiento predictivo...")

# Iniciar el sistema principal en segundo plano
print("Iniciando el motor principal...")
run_command("python main.py", wait=False)

# Esperar a que el sistema se inicie
print("Esperando a que el sistema se inicie...")
time.sleep(3)

# Iniciar el servidor web
print("Iniciando el servidor web...")
run_command("python api.py", wait=False)

# Esperar a que el servidor web se inicie
print("Esperando a que el servidor web se inicie...")
time.sleep(3)

# Abrir el navegador
print("Abriendo el navegador...")
try:
    webbrowser.open("http://localhost:5000")
    print("Interfaz web abierta en http://localhost:5000")
except:
    print("No se pudo abrir el navegador automáticamente")
    print("Por favor, abre manualmente http://localhost:5000")

print("\\nSistema iniciado correctamente!")
print("Presiona Ctrl+C para detener el sistema cuando hayas terminado")

try:
    # Mantener el script en ejecución
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\\nDeteniendo el sistema...")
    if os.name == 'nt':  # Windows
        run_command("taskkill /f /im python.exe", wait=True)
    else:
        run_command("pkill -f python", wait=True)
    print("Sistema detenido correctamente")
"""

print("Creando script de inicio...")
with open("start.py", "w", encoding="utf-8") as f:
    f.write(start_script)

print("\n¡Configuración completada correctamente!")
print("Para iniciar el sistema, ejecuta: python start.py")
print("O simplemente haz doble clic en start.py")