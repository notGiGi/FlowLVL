# tests/test_integration.py
import unittest
import json
from datetime import datetime
from anomaly_detector import AnomalyDetector
from predictive_engine import PredictiveEngine
from action_recommender import ActionRecommender

class TestIntegration(unittest.TestCase):
    def setUp(self):
        anomaly_config = {"anomaly_threshold": 0.5}
        predictive_config = {"prediction_threshold": 0.6, "sequence_length": 5}
        action_config = {"config_dir": "./config"}
        self.anomaly_detector = AnomalyDetector(config=anomaly_config)
        self.predictive_engine = PredictiveEngine(config=predictive_config)
        self.action_recommender = ActionRecommender(config=action_config)

    def test_memory_leak_scenario(self):
        service_id = "order-processing-service"
        test_data = {
            "service_id": service_id,
            "timestamp": datetime.now().isoformat(),
            "memory_usage": 85.0,          # Valor alto para provocar fuga
            "gc_collection_time": 700      # Tiempo alto de GC
        }
        is_anomaly, score, details = self.anomaly_detector.detect_anomalies(test_data)
        print("\n[Test] Memory Leak Scenario:")
        print("Anomaly:", is_anomaly, "Score:", score)
        self.assertTrue(is_anomaly, "Se esperaba detectar una anomalía en fuga de memoria")
        predictions = self.predictive_engine.predict_failures(service_id, [test_data])
        print("Prediction:", predictions)
        recommendation = self.action_recommender.process_and_recommend(anomaly_data={
            "service_id": service_id,
            "anomaly_score": score,
            "details": {"metrics": test_data}
        })
        print("Recommendation:", json.dumps(recommendation, indent=2))
        self.assertIsNotNone(recommendation, "Se esperaba obtener una recomendación de acción")

    def test_db_overload_scenario(self):
        service_id = "postgres-main"
        test_data = {
            "service_id": service_id,
            "timestamp": datetime.now().isoformat(),
            "active_connections": 110,     # Valor significativamente alto
            "connection_wait_time": 350    # Tiempo de espera elevado
        }
        is_anomaly, score, details = self.anomaly_detector.detect_anomalies(test_data)
        print("\n[Test] DB Overload Scenario:")
        print("Anomaly:", is_anomaly, "Score:", score)
        self.assertTrue(is_anomaly, "Se esperaba detectar una anomalía de sobrecarga en BD")
        recommendation = self.action_recommender.process_and_recommend(anomaly_data={
            "service_id": service_id,
            "anomaly_score": score,
            "details": {"metrics": test_data}
        })
        print("Recommendation:", json.dumps(recommendation, indent=2))
        self.assertIsNotNone(recommendation, "Se esperaba obtener una recomendación de acción")

    def test_redis_fragmentation_scenario(self):
        service_id = "redis-cache-01"
        test_data = {
            "service_id": service_id,
            "timestamp": datetime.now().isoformat(),
            "memory_fragmentation_ratio": 3.5,  # Valor alto (por encima de base 2.0)
            "hit_rate": 75.0                   # Valor bajo para el hit rate
        }
        is_anomaly, score, details = self.anomaly_detector.detect_anomalies(test_data)
        print("\n[Test] Redis Fragmentation Scenario:")
        print("Anomaly:", is_anomaly, "Score:", score)
        self.assertTrue(is_anomaly, "Se esperaba detectar una anomalía de fragmentación en Redis")
        recommendation = self.action_recommender.process_and_recommend(anomaly_data={
            "service_id": service_id,
            "anomaly_score": score,
            "details": {"metrics": test_data}
        })
        print("Recommendation:", json.dumps(recommendation, indent=2))
        self.assertIsNotNone(recommendation, "Se esperaba obtener una recomendación de acción")

if __name__ == "__main__":
    unittest.main()
