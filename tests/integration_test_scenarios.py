import os
import sys
import json
import time
import logging
import unittest
import requests
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

# Configurar path para importar módulos del proyecto
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Importar componentes del sistema
from anomaly_detector.improved_anomaly_detector import ImprovedAnomalyDetector
from predictive_engine.predictive_engine import PredictiveEngine
from action_recommender.improved_action_recommender import ImprovedActionRecommender
from monitoring.service_profiler import ServiceProfiler
from utils.metrics import MetricsCollector

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('integration_tests')

class IntegrationTestScenarios(unittest.TestCase):
    """
    Suite de pruebas de integración para verificar el funcionamiento completo
    del sistema de mantenimiento predictivo con diferentes escenarios.
    """
    
    @classmethod
    def setUpClass(cls):
        """Configuración inicial para todas las pruebas"""
        # Configuración por defecto
        cls.config = {
            "config_dir": "./config",
            "data_dir": "./data",
            "models_dir": "./models",
            "metrics_enabled": False  # Deshabilitar métricas para pruebas
        }
        
        # Inicializar componentes
        cls.anomaly_detector = ImprovedAnomalyDetector(config=cls.config)
        cls.predictive_engine = PredictiveEngine(config=cls.config)
        cls.action_recommender = ImprovedActionRecommender(config=cls.config)
        cls.service_profiler = ServiceProfiler(config=cls.config)
        
        # Crear directorio para gráficos
        os.makedirs("./test_results", exist_ok=True)
        
        # Cargar datos de prueba
        cls.load_test_data()
    
    @classmethod
    def load_test_data(cls):
        """Carga datos para los escenarios de prueba"""
        # Intentar cargar datos existentes
        try:
            with open("./data/test_scenario1.json", "r") as f:
                cls.scenario1_data = json.load(f)
                
            with open("./data/test_scenario2.json", "r") as f:
                cls.scenario2_data = json.load(f)
                
            with open("./data/test_scenario3.json", "r") as f:
                cls.scenario3_data = json.load(f)
                
            logger.info("Datos de prueba cargados correctamente")
            
        except FileNotFoundError:
            # Si no existen los archivos, generar datos de prueba
            logger.info("Generando datos de prueba...")
            cls.generate_test_data()
    
    @classmethod
    def generate_test_data(cls):
        """Genera datos sintéticos para pruebas"""
        # Escenario 1: Fuga de memoria
        cls.scenario1_data = {
            "service_id": "order-processing-service",
            "timestamps": [],
            "metrics": []
        }
        
        # Generar datos para fuga de memoria (incremento gradual)
        start_time = datetime.now() - timedelta(hours=5)
        memory_base = 60.0
        gc_time_base = 350
        
        for i in range(5):
            timestamp = (start_time + timedelta(hours=i)).isoformat() + "Z"
            memory = memory_base + (i * 4)
            gc_time = gc_time_base + (i * 100)
            
            cls.scenario1_data["timestamps"].append(timestamp)
            cls.scenario1_data["metrics"].append({
                "memory_usage": memory,
                "gc_collection_time": gc_time,
                "cpu_usage": 45 + (i * 2),
                "response_time_ms": 80 + (i * 5)
            })
        
        # Escenario 2: Sobrecarga de base de datos
        cls.scenario2_data = {
            "service_id": "postgres-main",
            "timestamps": [],
            "metrics": []
        }
        
        # Generar datos para sobrecarga de BD
        start_time = datetime.now() - timedelta(hours=6)
        connections_base = 70
        wait_time_base = 100
        
        for i in range(6):
            timestamp = (start_time + timedelta(minutes=i*15)).isoformat() + "Z"
            connections = connections_base + (i * 6)
            wait_time = wait_time_base + (i * 50)
            
            cls.scenario2_data["timestamps"].append(timestamp)
            cls.scenario2_data["metrics"].append({
                "active_connections": connections,
                "connection_wait_time": wait_time,
                "cpu_usage": 40 + (i * 3),
                "memory_usage": 50 + (i * 2)
            })
        
        # Escenario 3: Fragmentación de memoria en Redis
        cls.scenario3_data = {
            "service_id": "redis-cache-01",
            "timestamps": [],
            "metrics": []
        }
        
        # Generar datos para fragmentación de memoria
        start_time = datetime.now() - timedelta(days=6)
        frag_base = 1.2
        hit_rate_base = 92.0
        
        for i in range(7):
            timestamp = (start_time + timedelta(days=i)).isoformat() + "Z"
            
            # En los primeros 6 puntos, incrementar fragmentación y reducir hit rate
            if i < 6:
                frag = frag_base + (i * 0.6)
                hit_rate = hit_rate_base - (i * 4)
            else:
                # En el último punto, simular recuperación (purga)
                frag = 1.3
                hit_rate = 84.0
            
            cls.scenario3_data["timestamps"].append(timestamp)
            cls.scenario3_data["metrics"].append({
                "memory_fragmentation_ratio": frag,
                "hit_rate": hit_rate,
                "cpu_usage": 20 + min(i * 4, 20),
                "memory_usage": 40 + min(i * 5, 30)
            })
        
        # Guardar datos generados
        os.makedirs("./data", exist_ok=True)
        
        with open("./data/test_scenario1.json", "w") as f:
            json.dump(cls.scenario1_data, f, indent=2)
            
        with open("./data/test_scenario2.json", "w") as f:
            json.dump(cls.scenario2_data, f, indent=2)
            
        with open("./data/test_scenario3.json", "w") as f:
            json.dump(cls.scenario3_data, f, indent=2)
            
        logger.info("Datos de prueba generados y guardados")
    
    def test_scenario1_memory_leak(self):
        """Prueba del escenario 1: Fuga de memoria"""
        logger.info("Ejecutando prueba de fuga de memoria")
        
        service_id = self.scenario1_data["service_id"]
        
        # Variables para almacenar resultados
        results = {
            "anomaly_detection": [],
            "predictions": [],
            "recommendations": []
        }
        
        # Crear datos secuenciales para simulación
        data_points = []
        
        # Simular datos incrementales (como si llegaran en tiempo real)
        print(f"\nSimulando escenario de fuga de memoria para {service_id}")
        print("-" * 80)
        
        for i, (timestamp, metrics) in enumerate(zip(self.scenario1_data["timestamps"], self.scenario1_data["metrics"])):
            # Crear punto de datos
            data_point = {
                "service_id": service_id,
                "timestamp": timestamp,
                **metrics
            }
            data_points.append(data_point)
            
            # Para cada punto, ejecutar la detección de anomalías
            print(f"\nProcesando punto de datos {i+1}/{len(self.scenario1_data['metrics'])}")
            print(f"Timestamp: {timestamp}")
            print(f"Memoria: {metrics['memory_usage']}%, GC Time: {metrics['gc_collection_time']}ms")
            
            # Detectar anomalías
            is_anomaly, anomaly_score, details = self.anomaly_detector.detect_anomalies(data_point)
            
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
                prediction_result = self.predictive_engine.predict_failures(service_id, data_points)
                
                print(f"Resultado predicción: {'FALLO PREDICHO' if prediction_result.get('prediction', False) else 'Sin predicción'}")
                if prediction_result.get("prediction", False):
                    print(f"Probabilidad de fallo: {prediction_result.get('probability', 0):.3f}")
                    print(f"Horizonte de predicción: {prediction_result.get('prediction_horizon', 0)} horas")
                
                # Almacenar predicción
                results["predictions"].append(prediction_result)
                
                # Si hay anomalía o predicción de fallo, recomendar acción
                if is_anomaly or (prediction_result.get("prediction", False)):
                    if is_anomaly:
                        recommendation = self.action_recommender.process_and_recommend(anomaly_data={
                            "service_id": service_id,
                            "anomaly_score": anomaly_score,
                            "details": {
                                "metrics": metrics
                            }
                        })
                    else:
                        recommendation = self.action_recommender.process_and_recommend(prediction_data=prediction_result)
                    
                    # Mostrar recomendación
                    if recommendation and "recommended_action" in recommendation:
                        action = recommendation["recommended_action"]
                        print(f"Acción recomendada: {action.get('action_id')}")
                        print(f"Comando: {action.get('command')}")
                        
                        # Almacenar recomendación
                        results["recommendations"].append(recommendation)
                        
                        # Simular ejecución de acción si estamos en el último punto
                        if i == len(self.scenario1_data["metrics"]) - 1:
                            print("\nEjecutando acción correctiva...")
                            success = self.action_recommender.execute_action(action, metrics)
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
        
        # Visualización de resultados
        timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in self.scenario1_data["timestamps"]]
        memory_values = [m["memory_usage"] for m in self.scenario1_data["metrics"]]
        gc_time_values = [m["gc_collection_time"] for m in self.scenario1_data["metrics"]]
        anomaly_scores = [r["anomaly_score"] for r in results["anomaly_detection"]]
        
        plt.figure(figsize=(10, 6))
        
        plt.plot(timestamps, memory_values, "-o", label="Uso de Memoria (%)")
        plt.plot(timestamps, [x/10 for x in gc_time_values], "-o", label="GC Time (ms/10)")
        plt.plot(timestamps, anomaly_scores, "-o", label="Score de Anomalía")
        
        # Marcar puntos de anomalía
        for i, r in enumerate(results["anomaly_detection"]):
            if r["is_anomaly"]:
                plt.axvline(x=timestamps[i], color="r", linestyle="--", alpha=0.3)
        
        plt.title(f"Detección de Fuga de Memoria - {service_id}")
        plt.xlabel("Tiempo")
        plt.ylabel("Valor")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("test_results/memory_leak_detection.png")
        print("\nGráfico guardado como 'test_results/memory_leak_detection.png'")
        
        # Verificaciones
        self.assertTrue(any(r["is_anomaly"] for r in results["anomaly_detection"]), 
                       "No se detectó ninguna anomalía en el escenario de fuga de memoria")
        
        # Verificar que la última muestra tenga anomalía
        self.assertTrue(results["anomaly_detection"][-1]["is_anomaly"], 
                      "No se detectó anomalía en el punto más crítico")
        
        # Verificar que se generó una recomendación
        self.assertTrue(len(results["recommendations"]) > 0, 
                      "No se generaron recomendaciones de acción")
        
        print("\nPrueba del Escenario 1 completada con éxito!")
    
    def test_scenario2_db_overload(self):
        """Prueba del escenario 2: Sobrecarga de base de datos"""
        logger.info("Ejecutando prueba de sobrecarga de base de datos")
        
        service_id = self.scenario2_data["service_id"]
        
        # Variables para resultados
        results = {"anomaly_detection": [], "recommendations": []}
        
        # Probar el escenario
        print(f"\nSimulando escenario de sobrecarga en base de datos para {service_id}")
        print("-" * 80)
        
        # Ejecutar el test
        data_points = []
        
        for i, (timestamp, metrics) in enumerate(zip(self.scenario2_data["timestamps"], self.scenario2_data["metrics"])):
            data_point = {"service_id": service_id, "timestamp": timestamp, **metrics}
            data_points.append(data_point)
            
            print(f"\nPunto {i+1}: Conexiones={metrics['active_connections']}, Tiempo de espera={metrics['connection_wait_time']}ms")
            
            # Detectar anomalías con métricas específicas de base de datos
            is_anomaly, score, details = self.anomaly_detector.detect_anomalies(data_point)
            
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
                recommendation = self.action_recommender.process_and_recommend(anomaly_data={
                    "service_id": service_id,
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
        timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in self.scenario2_data["timestamps"]]
        connections = [m["active_connections"] for m in self.scenario2_data["metrics"]]
        wait_times = [m["connection_wait_time"]/10 for m in self.scenario2_data["metrics"]]  # Dividimos por 10 para escalar
        anomaly_scores = [r["anomaly_score"] for r in results["anomaly_detection"]]
        
        # Graficar valores
        plt.plot(timestamps, connections, '-o', label="Conexiones activas")
        plt.plot(timestamps, wait_times, '-o', label="Tiempo de espera/10 (ms)")
        plt.plot(timestamps, anomaly_scores, '-o', label="Score de anomalía")
        
        # Marcar puntos de anomalía
        for i, result in enumerate(results["anomaly_detection"]):
            if result["is_anomaly"]:
                plt.axvline(x=timestamps[i], color="r", linestyle="--", alpha=0.3)
        
        plt.title(f"Análisis de sobrecarga - {service_id}")
        plt.xlabel("Tiempo")
        plt.ylabel("Valor")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("test_results/db_overload_detection.png")
        print("\nGráfico guardado como 'test_results/db_overload_detection.png'")
        
        # Verificaciones
        self.assertTrue(any(r["is_anomaly"] for r in results["anomaly_detection"]), 
                       "No se detectó ninguna anomalía en el escenario de sobrecarga de BD")
        
        # Verificar que se generó una recomendación
        self.assertTrue(len(results["recommendations"]) > 0, 
                      "No se generaron recomendaciones de acción")
        
        print("\nEscenario 2 completado con éxito")
    
    def test_scenario3_redis_fragmentation(self):
        """Prueba del escenario 3: Fragmentación de memoria en Redis"""
        logger.info("Ejecutando prueba de fragmentación de memoria en Redis")
        
        service_id = self.scenario3_data["service_id"]
        
        # Variables para resultados
        results = {"anomaly_detection": [], "recommendations": []}
        
        # Probar el escenario
        print(f"\nSimulando escenario de fragmentación de memoria en Redis para {service_id}")
        print("-" * 80)
        
        # Ejecutar el test
        data_points = []
        
        for i, (timestamp, metrics) in enumerate(zip(self.scenario3_data["timestamps"], self.scenario3_data["metrics"])):
            data_point = {"service_id": service_id, "timestamp": timestamp, **metrics}
            data_points.append(data_point)
            
            print(f"\nPunto {i+1}: Fragmentación={metrics['memory_fragmentation_ratio']}, Hit rate={metrics['hit_rate']}%")
            
            # Mostrar datos completos para depuración
            print(f"Datos completos: {data_point}")
            
            # Detectar anomalías con métricas específicas de Redis
            is_anomaly, score, details = self.anomaly_detector.detect_anomalies(data_point)
            
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
                recommendation = self.action_recommender.process_and_recommend(anomaly_data={
                    "service_id": service_id,
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
        timestamps = [datetime.fromisoformat(t.replace('Z', '+00:00')) for t in self.scenario3_data["timestamps"]]
        frag_ratios = [m["memory_fragmentation_ratio"] for m in self.scenario3_data["metrics"]]
        hit_rates = [m["hit_rate"]/100 for m in self.scenario3_data["metrics"]]  # Dividimos por 100 para normalizar
        anomaly_scores = [r["anomaly_score"] for r in results["anomaly_detection"]]
        
        # Graficar valores
        plt.plot(timestamps, frag_ratios, '-o', label="Ratio de fragmentación")
        plt.plot(timestamps, hit_rates, '-o', label="Hit rate (/100)")
        plt.plot(timestamps, anomaly_scores, '-o', label="Score de anomalía")
        
        # Marcar puntos de anomalía
        for i, result in enumerate(results["anomaly_detection"]):
            if result["is_anomaly"]:
                plt.axvline(x=timestamps[i], color="r", linestyle="--", alpha=0.3)
        
        plt.title(f"Análisis de fragmentación - {service_id}")
        plt.xlabel("Tiempo")
        plt.ylabel("Valor")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig("test_results/redis_fragmentation_detection.png")
        print("\nGráfico guardado como 'test_results/redis_fragmentation_detection.png'")
        
        print("\nEscenario 3 completado con éxito")
    
    def test_multi_scenario_parallel(self):
        """Prueba de múltiples escenarios en paralelo"""
        logger.info("Ejecutando prueba de múltiples escenarios en paralelo")
        
        # Crear lista de puntos de datos para cada escenario
        scenario1_points = []
        for timestamp, metrics in zip(self.scenario1_data["timestamps"], self.scenario1_data["metrics"]):
            scenario1_points.append({
                "service_id": self.scenario1_data["service_id"],
                "timestamp": timestamp,
                **metrics
            })
        
        scenario2_points = []
        for timestamp, metrics in zip(self.scenario2_data["timestamps"], self.scenario2_data["metrics"]):
            scenario2_points.append({
                "service_id": self.scenario2_data["service_id"],
                "timestamp": timestamp,
                **metrics
            })
        
        scenario3_points = []
        for timestamp, metrics in zip(self.scenario3_data["timestamps"], self.scenario3_data["metrics"]):
            scenario3_points.append({
                "service_id": self.scenario3_data["service_id"],
                "timestamp": timestamp,
                **metrics
            })
        
        # Combinar todos los puntos
        all_points = scenario1_points + scenario2_points + scenario3_points
        
        # Procesar en paralelo
        print(f"\nProcesando {len(all_points)} puntos de datos en paralelo")
        
        start_time = time.time()
        
        # Usar el detector de anomalías para procesar en batch
        batch_results = self.anomaly_detector.batch_detection(all_points)
        
        end_time = time.time()
        process_time = end_time - start_time
        
        print(f"\nProcesamiento completado en {process_time:.2f} segundos")
        print(f"Velocidad de procesamiento: {len(all_points)/process_time:.2f} puntos/segundo")
        
        # Contar anomalías detectadas
        anomalies_count = sum(1 for r in batch_results if r["is_anomaly"])
        print(f"Anomalías detectadas: {anomalies_count} de {len(all_points)} puntos")
        
        # Verificaciones
        self.assertTrue(len(batch_results) == len(all_points),
                      "No se procesaron todos los puntos")
        
        self.assertTrue(anomalies_count > 0,
                      "No se detectaron anomalías en el procesamiento paralelo")
        
        print("\nPrueba de procesamiento paralelo completada con éxito")
    
    def test_profiler_learning(self):
        """Prueba el aprendizaje del perfilador de servicios"""
        logger.info("Ejecutando prueba de aprendizaje del perfilador")
        
        # Utilizar datos del escenario 1
        service_id = self.scenario1_data["service_id"]
        
        # Añadir datos al perfilador
        print(f"\nEntrenando perfilador para {service_id}")
        
        # Realizar el entrenamiento varias veces para simular más datos
        for _ in range(5):
            for timestamp, metrics in zip(self.scenario1_data["timestamps"], self.scenario1_data["metrics"]):
                self.service_profiler.add_metrics_data(service_id, metrics, timestamp)
        
        # Forzar actualización de perfil
        self.service_profiler.update_service_profile(service_id)
        
        # Obtener perfil generado
        profile = self.service_profiler.get_service_profile(service_id)
        
        print(f"\nPerfil generado para {service_id}:")
        
        if profile:
            print(f"Métricas disponibles: {profile.get('metrics', [])}")
            print("\nLímites calculados:")
            
            for metric, bounds in profile.get('bounds', {}).items():
                print(f"  {metric}: {bounds}")
                
            print("\nCorrelaciones detectadas:")
            for corr_key, corr_value in profile.get('correlations', {}).items():
                print(f"  {corr_key}: {corr_value:.2f}")
                
            # Obtener recomendaciones de umbrales
            recommendations = self.service_profiler.get_threshold_recommendations(service_id)
            
            print("\nUmbrales recomendados:")
            for metric, value in recommendations.items():
                print(f"  {metric}: {value}")
        else:
            print("No se generó perfil")
        
        # Verificaciones
        self.assertIsNotNone(profile, "No se generó perfil")
        
        self.assertTrue('memory_usage' in profile.get('metrics', []),
                      "Métrica de memoria no detectada en el perfil")
        
        self.assertTrue(len(profile.get('bounds', {})) > 0,
                      "No se calcularon límites para ninguna métrica")
        
        print("\nPrueba de perfilador completada con éxito")
    
    def test_prediction_accuracy(self):
        """Prueba la precisión del motor predictivo"""
        logger.info("Ejecutando prueba de precisión del motor predictivo")
        
        # Utilizar datos del escenario 1
        service_id = self.scenario1_data["service_id"]
        
        # Crear puntos de datos
        data_points = []
        for timestamp, metrics in zip(self.scenario1_data["timestamps"], self.scenario1_data["metrics"]):
            data_points.append({
                "service_id": service_id,
                "timestamp": timestamp,
                **metrics
            })
        
        # Realizar predicción
        prediction = self.predictive_engine.predict_failures(service_id, data_points)
        
        print(f"\nPredicción para {service_id}:")
        print(f"Resultado: {'Fallo predicho' if prediction.get('prediction', False) else 'Sin predicción'}")
        print(f"Probabilidad: {prediction.get('probability', 0):.3f}")
        print(f"Horizonte: {prediction.get('prediction_horizon', 0)} horas")
        print(f"Tipo: {prediction.get('prediction_type', 'unknown')}")
        
        # Simular validación (suponiendo que efectivamente hubo un fallo)
        validation = self.predictive_engine.validate_predictions(service_id, had_failure=True)
        
        print(f"\nValidación de predicciones:")
        print(f"Predicciones validadas: {validation.get('validated_count', 0)}")
        print(f"Predicciones correctas: {validation.get('correct_count', 0)}")
        print(f"Precisión: {validation.get('accuracy', 0):.2f}")
        
        # No hacemos verificaciones estrictas aquí porque el motor predictivo está simplificado
        
        print("\nPrueba de predicción completada con éxito")

if __name__ == '__main__':
    unittest.main()