﻿import json
import os

# Crear directorio si no existe
os.makedirs("data", exist_ok=True)

# Datos del escenario 2 (PostgreSQL)
scenario_data = {
  "service_id": "postgres-main",
  "timestamps": [
    "2025-04-13T16:00:12.814Z",
    "2025-04-13T16:15:27.482Z",
    "2025-04-13T16:30:42.168Z",
    "2025-04-13T16:45:08.127Z",
    "2025-04-13T17:00:03.127Z",
    "2025-04-13T17:10:42.793Z"
  ],
  "metrics": [
    {
      "cpu_usage": 76.8,
      "memory_usage": 62.4,
      "disk_usage_percent": 78.2,
      "active_connections": 75,
      "connection_wait_time": 120,
      "query_execution_time_avg": 425
    },
    {
      "cpu_usage": 82.3,
      "memory_usage": 64.1,
      "disk_usage_percent": 78.9,
      "active_connections": 85,
      "connection_wait_time": 180,
      "query_execution_time_avg": 580
    },
    {
      "cpu_usage": 89.6,
      "memory_usage": 68.2,
      "disk_usage_percent": 79.5,
      "active_connections": 95,
      "connection_wait_time": 250,
      "query_execution_time_avg": 720
    },
    {
      "cpu_usage": 92.4,
      "memory_usage": 72.3,
      "disk_usage_percent": 80.1,
      "active_connections": 98,
      "connection_wait_time": 320,
      "query_execution_time_avg": 830
    },
    {
      "cpu_usage": 94.7,
      "memory_usage": 76.5,
      "disk_usage_percent": 80.8,
      "active_connections": 100,
      "connection_wait_time": 380,
      "query_execution_time_avg": 920
    },
    {
      "cpu_usage": 72.4,
      "memory_usage": 72.8,
      "disk_usage_percent": 80.8,
      "active_connections": 102,
      "connection_wait_time": 45,
      "query_execution_time_avg": 520
    }
  ]
}

# Guardar en archivo JSON
with open("data/test_scenario2.json", "w") as f:
    json.dump(scenario_data, f, indent=2)

print("Datos para escenario 2 creados en data/test_scenario2.json")
