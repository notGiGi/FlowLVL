﻿import json
import os

# Crear directorio si no existe
os.makedirs("data", exist_ok=True)

# Datos del escenario 3 (Redis)
scenario_data = {
  "service_id": "redis-cache-01",
  "timestamps": [
    "2025-04-09T08:00:17.182Z",
    "2025-04-10T08:00:24.791Z",
    "2025-04-11T08:00:12.347Z",
    "2025-04-12T08:00:18.682Z",
    "2025-04-13T08:00:15.429Z",
    "2025-04-13T15:30:24.762Z",
    "2025-04-13T15:40:18.274Z"
  ],
  "metrics": [
    {
      "cpu_usage": 18.2,
      "memory_usage": 42.6,
      "memory_fragmentation_ratio": 1.2,
      "hit_rate": 92.4
    },
    {
      "cpu_usage": 22.7,
      "memory_usage": 48.1,
      "memory_fragmentation_ratio": 1.8,
      "hit_rate": 90.8
    },
    {
      "cpu_usage": 24.3,
      "memory_usage": 52.5,
      "memory_fragmentation_ratio": 2.5,
      "hit_rate": 87.2
    },
    {
      "cpu_usage": 28.6,
      "memory_usage": 58.3,
      "memory_fragmentation_ratio": 3.1,
      "hit_rate": 82.4
    },
    {
      "cpu_usage": 32.8,
      "memory_usage": 64.7,
      "memory_fragmentation_ratio": 3.7,
      "hit_rate": 76.8
    },
    {
      "cpu_usage": 36.2,
      "memory_usage": 68.3,
      "memory_fragmentation_ratio": 4.2,
      "hit_rate": 71.5
    },
    {
      "cpu_usage": 28.4,
      "memory_usage": 62.1,
      "memory_fragmentation_ratio": 1.3,
      "hit_rate": 84.2
    }
  ]
}

# Guardar en archivo JSON
with open("data/test_scenario3.json", "w") as f:
    json.dump(scenario_data, f, indent=2)

print("Datos para escenario 3 creados en data/test_scenario3.json")
