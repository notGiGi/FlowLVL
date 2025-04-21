# -*- coding: utf-8 -*-
import os
import json
import random
from datetime import datetime, timedelta
import numpy as np

print("🔧 Mejorando el sistema de predicción...")

# 1. Generar mejores datos históricos con tendencias más realistas
print("Generando datos históricos de alta calidad...")

# Datos para app-server con tendencia realista
app_server_data = []
base_time = datetime.now() - timedelta(hours=24)  # 24 horas de datos históricos

# Función para generar valores con tendencia realista
def generate_trend_value(base, hour, growth_rate=0.5, noise=0.5, max_value=95):
    # Valor base + tendencia lineal + ruido aleatorio, limitado a max_value
    value = base + (hour * growth_rate) + random.uniform(-noise, noise)
    # Asegurar que el valor no exceda el máximo realista
    return min(value, max_value)

# Crear histórico con tendencia creciente controlada
for i in range(24):  # 24 horas de historia
    ts = (base_time + timedelta(hours=i)).isoformat()
    
    # Generar valores con diferentes tasas de crecimiento pero realistas
    memory = generate_trend_value(40, i, growth_rate=0.8, noise=0.5, max_value=90)
    cpu = generate_trend_value(30, i, growth_rate=1.2, noise=1.0, max_value=85)
    response_time = generate_trend_value(150, i, growth_rate=5, noise=5, max_value=500)
    error_rate = generate_trend_value(0.5, i, growth_rate=0.1, noise=0.05, max_value=5)
    
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

# Datos para database con tendencia creciente controlada
database_data = []

for i in range(24):
    ts = (base_time + timedelta(hours=i)).isoformat()
    
    # Tendencias más pronunciadas pero realistas para database
    memory = generate_trend_value(35, i, growth_rate=0.6, noise=0.5, max_value=85)
    cpu = generate_trend_value(25, i, growth_rate=1.0, noise=0.8, max_value=80)
    connections = generate_trend_value(40, i, growth_rate=1.8, noise=1.0, max_value=120)
    query_time = generate_trend_value(40, i, growth_rate=1.2, noise=1.5, max_value=150)
    
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

print("✅ Datos históricos mejorados creados")

# 2. Corregir el modelo de predicción avanzada para evitar valores extremos
def fix_advanced_predictor():
    file_path = "./predictor/advanced_predictor.py"
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Corregir el método predict_point para limitar valores
    predict_point_fix = """
    def predict_point(self, service_id, metric, hours_ahead):
        """Predice un valor futuro específico para una métrica"""
        try:
            if service_id not in self.models or metric not in self.models[service_id]:
                return None
            
            model_data = self.models[service_id][metric]
            model = model_data['model']
            base_time = model_data['base_time']
            
            # Preparar punto futuro para predicción
            future_time = datetime.now() + timedelta(hours=hours_ahead)
            
            # Crear características
            minutes = (future_time - base_time).total_seconds() / 60
            hour_of_day = future_time.hour / 24.0
            day_of_week = future_time.weekday() / 7.0
            
            # Hacer predicción
            X_future = np.array([[minutes, hour_of_day, day_of_week]])
            predicted_value = float(model.predict(X_future)[0])
            
            # Obtener el valor más reciente para esta métrica
            recent_value = None
            if service_id in self.thresholds:
                recent_value = self.thresholds[service_id].get(metric)
            
            # Limitar predicciones a rangos razonables según tipo de métrica
            if metric == 'cpu_usage':
                # CPU no puede superar 100% y generalmente no baja del 5%
                predicted_value = max(5, min(predicted_value, 95))
            elif metric == 'memory_usage':
                # Memoria similar a CPU
                predicted_value = max(10, min(predicted_value, 95))
            elif metric == 'response_time_ms':
                # Tiempos de respuesta no negativos y con límite superior razonable
                predicted_value = max(50, min(predicted_value, 1000))
            elif metric == 'error_rate':
                # Tasas de error no negativas y con límite superior
                predicted_value = max(0, min(predicted_value, 20))
            elif metric == 'active_connections':
                # Conexiones no negativas y con límite superior
                predicted_value = max(1, min(predicted_value, 200))
            elif metric == 'query_time_avg':
                # Tiempos de consulta no negativos
                predicted_value = max(10, min(predicted_value, 500))
            else:
                # Para otras métricas, asegurar que no sean negativas
                # y limitar crecimiento extreme
                if recent_value and isinstance(recent_value, (int, float)):
                    # Limitar cambio a máximo 200% del valor reciente
                    max_change = recent_value * 2
                    predicted_value = max(0, min(predicted_value, recent_value + max_change))
                else:
                    # Sin valor de referencia, limitar a rango genérico
                    predicted_value = max(0, min(predicted_value, 100))
            
            return predicted_value
            
        except Exception as e:
            logger.error(f"Error al predecir {service_id}:{metric} a {hours_ahead}h: {str(e)}")
            return None
    """
    
    # Reemplazar el método predict_point en el archivo
    import re
    pattern = r"def predict_point\(self, service_id, metric, hours_ahead\):.*?return None"
    content = re.sub(pattern, predict_point_fix.strip(), content, flags=re.DOTALL)
    
    # Guardar el archivo actualizado
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ Modelo de predicción mejorado para evitar valores extremos")

# Aplicar la corrección al predictor avanzado
fix_advanced_predictor()

# 3. Configurar umbrales más adecuados
print("Configurando umbrales óptimos...")
thresholds = {
    "default": {
        "memory_usage": 80,
        "cpu_usage": 85,
        "response_time_ms": 400,
        "error_rate": 5,
        "active_connections": 120,
        "query_time_avg": 150
    },
    "app-server": {
        "memory_usage": 85,
        "cpu_usage": 80,
        "response_time_ms": 350,
        "error_rate": 3
    },
    "database": {
        "memory_usage": 80,
        "cpu_usage": 75,
        "active_connections": 100,
        "query_time_avg": 120
    }
}

with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

print("✅ Umbrales actualizados para una detección más precisa")

# 4. Actualizar configuración del sistema
import yaml
system_config = {
    "anomaly_threshold": 0.4,
    "execution_mode": "simulation",
    "auto_remediation": False,
    "processing_interval": 15,
    "prediction_threshold": 0.4,
    "prediction_horizon": 24,
    "prediction_interval": 600  # Cada 10 minutos
}

with open("./config/system_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(system_config, f)

print("✅ Configuración del sistema actualizada")

print("\n🎉 Sistema de predicción mejorado con éxito!")
print("Para activar las mejoras:")
print("1. Reinicia el sistema:")
print("   Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force")
print("   python start.py")
print("2. Espera aproximadamente 30 segundos para que los modelos se entrenen")
print("3. Verifica la línea temporal para ver predicciones realistas")