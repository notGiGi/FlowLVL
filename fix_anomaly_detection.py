# -*- coding: utf-8 -*-
import os
import json
import time
from datetime import datetime
import sys

print("Ajustando umbrales y forzando detección de anomalías...")

# 1. Ajustar umbrales para que sean más estrictos
thresholds = {
    "default": {
        "memory_usage": 60,
        "cpu_usage": 70,
        "response_time_ms": 300,
        "error_rate": 2,
        "active_connections": 85,
        "query_time_avg": 70
    },
    "app-server": {
        "memory_usage": 60,
        "cpu_usage": 70,
        "response_time_ms": 300,
        "error_rate": 2
    },
    "database": {
        "memory_usage": 60,
        "cpu_usage": 70,
        "active_connections": 85,
        "query_time_avg": 70
    }
}

print("Estableciendo umbrales más estrictos...")
with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

# 2. Crear anomalía extrema para app-server
timestamp = datetime.now().isoformat()
extreme_app_metrics = {
    "service_id": "app-server",
    "timestamp": timestamp,
    "memory_usage": 99.9,
    "cpu_usage": 99.9,
    "response_time_ms": 1500,
    "error_rate": 25
}

print("Creando anomalía extrema para app-server...")
app_filename = f"app-server_{datetime.now().strftime('%Y%m%d')}.json"
app_filepath = os.path.join("./data", app_filename)

# Leer archivo existente
app_data = []
if os.path.exists(app_filepath):
    try:
        with open(app_filepath, 'r', encoding='utf-8') as f:
            app_data = json.load(f)
    except:
        print(f"Error al leer {app_filepath}, creando nuevo archivo")

# Añadir anomalía extrema
app_data.append(extreme_app_metrics)

# Guardar archivo
with open(app_filepath, 'w', encoding='utf-8') as f:
    json.dump(app_data, f, indent=2)

# 3. Crear anomalía extrema para database
extreme_db_metrics = {
    "service_id": "database",
    "timestamp": timestamp,
    "memory_usage": 99.9,
    "cpu_usage": 99.9,
    "active_connections": 500,
    "query_time_avg": 600
}

print("Creando anomalía extrema para database...")
db_filename = f"database_{datetime.now().strftime('%Y%m%d')}.json"
db_filepath = os.path.join("./data", db_filename)

# Leer archivo existente
db_data = []
if os.path.exists(db_filepath):
    try:
        with open(db_filepath, 'r', encoding='utf-8') as f:
            db_data = json.load(f)
    except:
        print(f"Error al leer {db_filepath}, creando nuevo archivo")

# Añadir anomalía extrema
db_data.append(extreme_db_metrics)

# Guardar archivo
with open(db_filepath, 'w', encoding='utf-8') as f:
    json.dump(db_data, f, indent=2)

# 4. Actualizar configuración de sistema
system_config = {
    "anomaly_threshold": 0.3,  # Reducir umbral de anomalía a 0.3 (era 0.6)
    "execution_mode": "simulation",
    "auto_remediation": False,
    "processing_interval": 5,  # Reducir intervalo a 5 segundos
    "prediction_threshold": 0.4,  # Reducir umbral de predicción
    "prediction_horizon": 8,
    "prediction_interval": 1800
}

print("Actualizando configuración del sistema...")
import yaml
with open("./config/system_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(system_config, f)

print("\n✅ ¡Ajustes completados!")
print("💡 Espera 30-60 segundos y luego actualiza la página")
print("📊 También puedes verificar eventos en la pestaña 'Eventos'")