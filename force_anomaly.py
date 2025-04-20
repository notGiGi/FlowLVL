# -*- coding: utf-8 -*-
import os
import json
import time
from datetime import datetime

# Directorio donde se guardan los datos
data_dir = "./data"

# Crear un servicio con anomalia clara
service_id = "test-service"
timestamp = datetime.now().isoformat()

# Metricas con valores claramente anomalos
metrics = {
    "service_id": service_id,
    "timestamp": timestamp,
    "memory_usage": 90.5,       # Valor muy alto
    "cpu_usage": 95.2,          # Valor muy alto
    "gc_collection_time": 850,  # Valor muy alto
    "response_time_ms": 750,    # Valor muy alto
    "error_rate": 8.5           # Valor muy alto
}

# Guardar las metricas en un archivo
filename = f"{service_id}_{datetime.now().strftime('%Y%m%d')}.json"
filepath = os.path.join(data_dir, filename)

# Leer archivo existente si existe
data = []
if os.path.exists(filepath):
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except:
        pass

# Añadir nuevas metricas
data.append(metrics)

# Guardar archivo
with open(filepath, 'w') as f:
    json.dump(data, f, indent=2)

print(f"Se ha insertado una anomalia simulada para el servicio {service_id}")
print(f"Metricas guardadas en {filepath}")
print("Espera aproximadamente 1-2 minutos para que el sistema la procese")
