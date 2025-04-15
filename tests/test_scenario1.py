import os
import sys
import json
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# Añadir directorio padre al path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from anomaly_detector import AnomalyDetector, AdaptiveEnsembleDetector
from predictive_engine import PredictiveEngine
from action_recommender import ActionRecommender

# Cargar datos de prueba
with open("data/test_scenario1.json", "r") as f:
    scenario_data = json.load(f)

# Crear instancias de los componentes
anomaly_detector = AnomalyDetector(config={
    "anomaly_threshold": 0.65,  # Umbral reducido para mayor sensibilidad
    "models_dir": "./models/anomaly"
})

predictive_engine = PredictiveEngine(config={
    "models_dir": "./models/predictive",
    "sequence_length": 5,  # Para pruebas usamos secuencia corta
    "prediction_threshold": 0.6  # Umbral reducido para predicciones
})

action_recommender = ActionRecommender(config={
    "config_dir": "./config",
    "models_dir": "./models/recommender"
})

# Variables para almacenar resultados
results = {
    "anomaly_detection": [],
    "predictions": [],
    "recommendations": []
}

# Crear datos secuenciales para simulación
data_points = []
service_id = scenario_data["service_id"]

# Simular datos incrementales (como si llegaran en tiempo real)
print(f"Simulando escenario de fuga de memoria para {service_id}")
print("-" * 80)

for i, (timestamp, metrics) in enumerate(zip(scenario_data["timestamps"], scenario_data["metrics"])):
    # Crear punto de datos
    data_point = {
        "service_id": service_id,
        "timestamp": timestamp,
        **metrics
    }
    data_points.append(data_point)
    
    # Para cada punto, ejecutar la detección de anomalías
    print(f"\nProcesando punto de datos {i+1}/{len(scenario_data['metrics'])}")
    print(f"Timestamp: {timestamp}")
    print(f"Memoria: {metrics['memory_usage']}%, GC Time: {metrics['gc_collection_time']}ms")
    
    # Detectar anomalías
    is_anomaly, anomaly_score, details = anomaly_detector.detect_anomalies(data_point)
    
    print(f"Resultado detección de anomalías: {'ANOMALÍA DETECTADA' if is_anomaly else 'Normal'}")
    print(f"Score de anomalía: {anomaly_score:.3f}")
    
    # Almacenar resultado
    results["anomaly_detection"].append({
        "timestamp": timestamp,
        "is_anomaly": is_anomaly,
        "anomaly_score": anomaly_score,
        "details": details
    })
    
    # Si tenemos suficientes puntos, realizar predicción
    if len(data_points) >= 3:
        # Predecir fallos
        prediction_result = predictive_engine.predict_failures(service_id, data_points)
        
        print(f"Resultado predicción: {'FALLO PREDICHO' if prediction_result.get('prediction', False) else 'Sin predicción'}")
        if prediction_result.get("prediction", False):
            print(f"Probabilidad de fallo: {prediction_result.get('probability', 0):.3f}")
            print(f"Horizonte de predicción: {prediction_result.get('prediction_horizon', 0)} horas")
        
        # Almacenar predicción
        results["predictions"].append(prediction_result)
        
        # Si hay anomalía o predicción de fallo, recomendar acción
        if is_anomaly or (prediction_result.get("prediction", False)):
            if is_anomaly:
                recommendation = action_recommender.process_and_recommend(anomaly_data={
                    "service_id": service_id,
                    "anomaly_score": anomaly_score,
                    "details": {
                        "metrics": metrics
                    }
                })
            else:
                recommendation = action_recommender.process_and_recommend(prediction_data=prediction_result)
            
            # Mostrar recomendación
            if recommendation and "recommended_action" in recommendation:
                action = recommendation["recommended_action"]
                print(f"Acción recomendada: {action.get('action_id')}")
                print(f"Comando: {action.get('command')}")
                
                # Almacenar recomendación
                results["recommendations"].append(recommendation)
                
                # Simular ejecución de acción si estamos en el último punto
                if i == len(scenario_data["metrics"]) - 1:
                    print("\nEjecutando acción correctiva...")
                    success = action_recommender.execute_action(action, metrics)
                    print(f"Resultado de la acción: {'Éxito' if success else 'Fallo'}")
                    
                    # Simular métricas después de la acción
                    post_action_metrics = metrics.copy()
                    post_action_metrics["memory_usage"] = 45.3
                    post_action_metrics["gc_collection_time"] = 80
                    post_action_metrics["response_time_ms"] = 65.7
                    
                    print("\nMétricas después de la acción:")
                    print(f"Memoria: {post_action_metrics['memory_usage']}% (antes: {metrics['memory_usage']}%)")
                    print(f"GC Time: {post_action_metrics['gc_collection_time']}ms (antes: {metrics['gc_collection_time']}ms)")
                    print(f"Response Time: {post_action_metrics['response_time_ms']}ms (antes: {metrics['response_time_ms']}ms)")

# Visualización de resultados mejorada
# Convertir timestamps a objetos datetime para graficar
timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in scenario_data["timestamps"]]
memory_values = [m["memory_usage"] for m in scenario_data["metrics"]]
gc_time_values = [m["gc_collection_time"] for m in scenario_data["metrics"]]
anomaly_scores = [r["anomaly_score"] for r in results["anomaly_detection"]]

plt.figure(figsize=(10, 6))

# Usar valores numéricos para el eje X en lugar de timestamps directamente
x_values = list(range(len(timestamps)))

plt.plot(x_values, memory_values, "-o", label="Uso de Memoria (%)")
plt.plot(x_values, [x/10 for x in gc_time_values], "-o", label="GC Time (ms/10)")
plt.plot(x_values, anomaly_scores, "-o", label="Score de Anomalía")

# Marcar puntos de anomalía
for i, r in enumerate(results["anomaly_detection"]):
    if r["is_anomaly"]:
        plt.axvline(x=i, color="r", linestyle="--", alpha=0.3)

# Configurar etiquetas de tiempo para el eje X
plt.xticks(x_values, [t.strftime('%H:%M') for t in timestamps], rotation=45)

plt.title(f"Detección de Fuga de Memoria - {service_id}")
plt.xlabel("Tiempo")
plt.ylabel("Valor")
plt.legend()
plt.grid(True)
plt.tight_layout()
plt.savefig("memory_leak_detection.png")
print("\nGráfico guardado como 'memory_leak_detection.png'")

print("\nPrueba del Escenario 1 completada con éxito!")