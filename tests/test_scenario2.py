import os
import sys
import json
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import logging

# Configurar logging para ver mensajes de depuración
logging.basicConfig(level=logging.DEBUG, 
                   format='[%(asctime)s] %(levelname)s: %(message)s')

# Añadir directorio padre al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomaly_detector import AnomalyDetector
from predictive_engine import PredictiveEngine
from action_recommender import ActionRecommender

# Cargar datos de prueba
with open("data/test_scenario2.json", "r") as f:
    scenario_data = json.load(f)

# Inicializar componentes con umbrales más bajos
anomaly_detector = AnomalyDetector(config={
    "anomaly_threshold": 0.3,  # Umbral reducido para mayor sensibilidad
    "models_dir": "./models/anomaly"
})

predictive_engine = PredictiveEngine(config={
    "models_dir": "./models/predictive",
    "sequence_length": 5,
    "prediction_threshold": 0.6
})

action_recommender = ActionRecommender(config={
    "config_dir": "./config",
    "models_dir": "./models/recommender"
})

# Verificar políticas cargadas
print("Políticas de acción cargadas:", json.dumps(action_recommender.action_policies, indent=2))

# Probar el escenario
print(f"\nSimulando escenario de sobrecarga en base de datos para {scenario_data['service_id']}")
print("-" * 80)

# Ejecutar el test
data_points = []
results = {"anomaly_detection": [], "recommendations": []}

for i, (timestamp, metrics) in enumerate(zip(scenario_data["timestamps"], scenario_data["metrics"])):
    data_point = {"service_id": scenario_data["service_id"], "timestamp": timestamp, **metrics}
    data_points.append(data_point)
    
    print(f"\nPunto {i+1}: Conexiones={metrics['active_connections']}, Tiempo de espera={metrics['connection_wait_time']}ms")
    
    # Detectar anomalías - usar las métricas específicas de base de datos
    is_anomaly, score, details = anomaly_detector.detect_anomalies(data_point)
    
    # Mostrar información detallada
    anomaly_type = details.get('anomaly_type', 'desconocido')
    print(f"Anomalía: {'SÍ' if is_anomaly else 'NO'}, Score: {score:.2f}, Tipo: {anomaly_type}")
    
    # Si hay análisis de métricas, mostrar detalles
    if 'metrics_analysis' in details:
        for metric, analysis in details['metrics_analysis'].items():
            if analysis.get('status', '') != 'normal':
                print(f"  - {metric}: {analysis.get('value')} ({analysis.get('status')})")
    
    results["anomaly_detection"].append({
        "timestamp": timestamp, 
        "is_anomaly": is_anomaly, 
        "anomaly_score": score,
        "type": anomaly_type
    })
    
    if is_anomaly:
        recommendation = action_recommender.process_and_recommend(anomaly_data={
            "service_id": scenario_data["service_id"],
            "anomaly_score": score,
            "details": {
                "metrics": metrics
            }
        })
        
        if recommendation and "recommended_action" in recommendation:
            action = recommendation["recommended_action"]
            print(f"Acción recomendada: {action.get('action_id')}")
            print(f"Comando: {action.get('command')}")
            results["recommendations"].append(recommendation)
        else:
            print("No se pudo determinar una acción recomendada")

# Visualizar resultados
plt.figure(figsize=(10, 6))

# Datos a graficar
timestamps = list(range(len(scenario_data["timestamps"])))
connections = [m["active_connections"] for m in scenario_data["metrics"]]
wait_times = [m["connection_wait_time"]/10 for m in scenario_data["metrics"]]  # Dividimos por 10 para escalar
anomaly_scores = [r["anomaly_score"] for r in results["anomaly_detection"]]

# Graficar valores
plt.plot(timestamps, connections, '-o', label="Conexiones activas")
plt.plot(timestamps, wait_times, '-o', label="Tiempo de espera/10 (ms)")
plt.plot(timestamps, anomaly_scores, '-o', label="Score de anomalía")

# Marcar puntos de anomalía
for i, result in enumerate(results["anomaly_detection"]):
    if result["is_anomaly"]:
        plt.axvline(x=i, color="r", linestyle="--", alpha=0.3)

# Marcar umbrales
plt.axhline(y=70, color="orange", linestyle="--", label="Umbral conexiones (70)")
plt.axhline(y=0.3, color="red", linestyle="--", label="Umbral anomalía (0.3)")

plt.title(f"Análisis de sobrecarga - {scenario_data['service_id']}")
plt.xlabel("Punto de tiempo")
plt.ylabel("Valor")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("db_overload_detection.png")
print("\nGráfico guardado como 'db_overload_detection.png'")
print("\nEscenario 2 completado con éxito")