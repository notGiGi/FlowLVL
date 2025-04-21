# -*- coding: utf-8 -*-
import os
import json
import time
from datetime import datetime
import argparse

def force_anomaly(service_id, severity="high"):
    """
    Inserta una anomalía para un servicio específico
    
    Args:
        service_id: ID del servicio (app-server o database)
        severity: Nivel de severidad (medium, high, critical)
    """
    # Directorio donde se guardan los datos
    data_dir = "./data"
    
    # Timestamp actual
    timestamp = datetime.now().isoformat()
    
    # Definir métricas según servicio y severidad
    if service_id == "app-server":
        # Valores base
        memory_usage = 70
        cpu_usage = 75
        response_time_ms = 400
        error_rate = 5
        
        # Ajustar según severidad
        if severity == "medium":
            pass  # Usar valores base
        elif severity == "high":
            memory_usage = 85
            cpu_usage = 90
            response_time_ms = 650
            error_rate = 8
        elif severity == "critical":
            memory_usage = 95
            cpu_usage = 98
            response_time_ms = 900
            error_rate = 15
        
        metrics = {
            "service_id": service_id,
            "timestamp": timestamp,
            "memory_usage": memory_usage,
            "cpu_usage": cpu_usage,
            "response_time_ms": response_time_ms,
            "error_rate": error_rate
        }
        
    elif service_id == "database":
        # Valores base
        memory_usage = 70
        cpu_usage = 75
        active_connections = 90
        query_time_avg = 80
        
        # Ajustar según severidad
        if severity == "medium":
            pass  # Usar valores base
        elif severity == "high":
            memory_usage = 85
            cpu_usage = 90
            active_connections = 120
            query_time_avg = 130
        elif severity == "critical":
            memory_usage = 95
            cpu_usage = 98
            active_connections = 200
            query_time_avg = 250
        
        metrics = {
            "service_id": service_id,
            "timestamp": timestamp,
            "memory_usage": memory_usage,
            "cpu_usage": cpu_usage,
            "active_connections": active_connections,
            "query_time_avg": query_time_avg
        }
    else:
        print(f"Error: Servicio '{service_id}' no reconocido")
        print("Servicios disponibles: app-server, database")
        return

    # Guardar las métricas en un archivo
    filename = f"{service_id}_{datetime.now().strftime('%Y%m%d')}.json"
    filepath = os.path.join(data_dir, filename)
    
    # Leer archivo existente si existe
    data = []
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            print(f"Error al leer archivo {filepath}. Creando nuevo archivo.")
    
    # Añadir nuevas métricas
    data.append(metrics)
    
    # Guardar archivo
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    
    print(f"✅ Se ha insertado una anomalía {severity} para el servicio {service_id}")
    print(f"📊 Métricas: {metrics}")
    print(f"💾 Guardado en: {filepath}")
    print("⏱️ Espera aproximadamente 30-60 segundos para que el sistema la procese")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Insertar anomalías en el sistema')
    parser.add_argument('service', choices=['app-server', 'database'], 
                      help='Servicio donde insertar la anomalía')
    parser.add_argument('--severity', '-s', choices=['medium', 'high', 'critical'],
                      default='high', help='Severidad de la anomalía (default: high)')
    
    args = parser.parse_args()
    force_anomaly(args.service, args.severity)