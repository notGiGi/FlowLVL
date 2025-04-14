import os
import sys
import json
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt

# Añadir directorio padre al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomaly_detector import AnomalyDetector
from predictive_engine import PredictiveEngine
from action_recommender import ActionRecommender

# Cargar datos de prueba
with open("data/test_scenario3.json", "r") as f:
    scenario_data = json.load(f)

# Inicializar componentes
anomaly_detector = AnomalyDetector(config={
    "anomaly_threshold": 0.6,
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

# Probar el escenario
print(f"Simulando escenario de fragmentación de memoria en Redis para {scenario_data['service_id']}")
print("-" * 80)

# Ejecutar el test (código simplificado)
data_points = []
results = {"anomaly_detection": []}

for i, (timestamp, metrics) in enumerate(zip(scenario_data["timestamps"], scenario_data["metrics"])):
    data_point = {"service_id": scenario_data["service_id"], "timestamp": timestamp, **metrics}
    data_points.append(data_point)
    
    print(f"\nPunto {i+1}: Fragmentación={metrics['memory_fragmentation_ratio']}, Hit rate={metrics['hit_rate']}%")
    
    is_anomaly, score, _ = anomaly_detector.detect_anomalies(data_point)
    print(f"Anomalía: {'SÍ' if is_anomaly else 'NO'}, Score: {score:.2f}")
    
    results["anomaly_detection"].append({"timestamp": timestamp, "is_anomaly": is_anomaly, "anomaly_score": score})

# Visualizar resultados
plt.figure(figsize=(10, 6))
plt.plot([m["memory_fragmentation_ratio"] for m in scenario_data["metrics"]], label="Ratio de fragmentación")
plt.plot([m["hit_rate"]/100 for m in scenario_data["metrics"]], label="Hit rate (/100)")
plt.plot([r["anomaly_score"] for r in results["anomaly_detection"]], label="Score de anomalía")
plt.title(f"Análisis de fragmentación - {scenario_data['service_id']}")
plt.legend()
plt.grid(True)
plt.savefig("redis_fragmentation.png")
print("\nGráfico guardado como 'redis_fragmentation.png'")
print("\nEscenario 3 completado con éxito")
