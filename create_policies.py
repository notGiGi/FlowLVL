﻿import json
import os

# Crear directorio si no existe
os.makedirs("config", exist_ok=True)

# Políticas de acción
policies = {
  "order-processing-service": {
    "description": "Acciones para el servicio de procesamiento de órdenes",
    "actions": {
      "memory_leak_restart": {
        "description": "Reinicia el servicio para resolver fuga de memoria",
        "command": "kubectl rollout restart deployment ${service_id}",
        "conditions": {
          "metrics": {
            "memory_usage": "> 70",
            "gc_collection_time": "> 500"
          },
          "anomaly_score": "> 0.6"
        },
        "priority": "high"
      }
    }
  },
  "postgres-main": {
    "description": "Acciones para servicios PostgreSQL",
    "actions": {
      "connection_pool_increase": {
        "description": "Aumenta el pool de conexiones",
        "command": "kubectl exec ${service_id}-0 -- psql -c \"ALTER SYSTEM SET max_connections = 200; SELECT pg_reload_conf();\"",
        "conditions": {
          "metrics": {
            "active_connections": "> 80",
            "connection_wait_time": "> 100"
          }
        },
        "priority": "high"
      }
    }
  },
  "redis-cache-01": {
    "description": "Acciones para servicios Redis",
    "actions": {
      "redis_memory_purge": {
        "description": "Purga de memoria de Redis",
        "command": "kubectl exec ${service_id}-0 -- redis-cli MEMORY PURGE",
        "conditions": {
          "metrics": {
            "memory_fragmentation_ratio": "> 2.0"
          }
        },
        "priority": "high"
      }
    }
  }
}

# Guardar en archivo JSON
with open("config/action_policies.json", "w") as f:
    json.dump(policies, f, indent=2)

print("Archivo de políticas creado en config/action_policies.json")
