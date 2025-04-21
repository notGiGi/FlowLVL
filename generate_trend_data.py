# -*- coding: utf-8 -*-
import os
import json
import random
from datetime import datetime, timedelta

# Crear datos para app-server con tendencia creciente
app_server_data = []
base_time = datetime.now() - timedelta(hours=12)

# Crear histórico con tendencia creciente
for i in range(12):
    ts = (base_time + timedelta(hours=i)).isoformat()
    # Valor base + tendencia lineal + componente cuadrático pequeño + ruido
    memory = 40 + i * 2 + (i**2 * 0.05) + random.uniform(-1, 1)
    cpu = 30 + i * 3 + (i**2 * 0.05) + random.uniform(-2, 2)
    response_time = 150 + i * 10 + random.uniform(-10, 10)
    error_rate = 0.5 + i * 0.2 + random.uniform(-0.1, 0.1)
    
    app_server_data.append({
        "service_id": "app-server",
        "timestamp": ts,
        "memory_usage": memory,
        "cpu_usage": cpu,
        "response_time_ms": response_time,
        "error_rate": error_rate
    })

# Guardar datos
with open("./data/app-server_data.json", "w", encoding="utf-8") as f:
    json.dump(app_server_data, f, indent=2)

# Datos para database con tendencia creciente diferente
database_data = []

for i in range(12):
    ts = (base_time + timedelta(hours=i)).isoformat()
    # Tendencia más pronunciada en active_connections
    memory = 35 + i * 1.5 + random.uniform(-1, 1)
    cpu = 25 + i * 2 + random.uniform(-1.5, 1.5)
    connections = 40 + i * 4 + (i**2 * 0.1) + random.uniform(-2, 2)
    query_time = 40 + i * 2 + random.uniform(-3, 3)
    
    database_data.append({
        "service_id": "database",
        "timestamp": ts,
        "memory_usage": memory,
        "cpu_usage": cpu,
        "active_connections": connections,
        "query_time_avg": query_time
    })

# Guardar datos
with open("./data/database_data.json", "w", encoding="utf-8") as f:
    json.dump(database_data, f, indent=2)

print("✅ Datos de prueba con tendencia creados")

# Configurar umbrales para detección
thresholds = {
    "default": {
        "memory_usage": 70,
        "cpu_usage": 80,
        "response_time_ms": 300,
        "error_rate": 5,
        "active_connections": 90,
        "query_time_avg": 100
    }
}

with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

print("✅ Umbrales configurados para detección proactiva")