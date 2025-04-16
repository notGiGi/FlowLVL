# tests/load_test.py
import time
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from anomaly_detector import AnomalyDetector

NUM_WORKERS = 20
NUM_REQUESTS = 100

def simulate_request(request_id):
    test_data = {
        "service_id": random.choice(["order-processing-service", "postgres-main", "redis-cache-01"]),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "memory_usage": random.uniform(50, 90),
        "gc_collection_time": random.uniform(200, 900),
        "active_connections": random.randint(60, 120),
        "connection_wait_time": random.uniform(80, 400),
        "memory_fragmentation_ratio": random.uniform(1.0, 4.5),
        "hit_rate": random.uniform(60, 100)
    }
    detector = AnomalyDetector(config={"anomaly_threshold": 0.5})
    is_anomaly, score, details = detector.detect_anomalies(test_data)
    return request_id, is_anomaly, score

def run_load_test():
    start_time = time.time()
    results = []
    with ThreadPoolExecutor(max_workers=NUM_WORKERS) as executor:
        future_to_req = {executor.submit(simulate_request, req_id): req_id for req_id in range(NUM_REQUESTS)}
        for future in as_completed(future_to_req):
            req_id = future_to_req[future]
            try:
                request_id, is_anomaly, score = future.result()
                results.append((request_id, is_anomaly, score))
            except Exception as e:
                print(f"Request {req_id} generó una excepción: {e}")
    total_time = time.time() - start_time
    print(f"\nCarga completada: {NUM_REQUESTS} solicitudes en {total_time:.2f} segundos.")
    for r in results[:5]:
        print(f"Request {r[0]}: Anomaly={r[1]}, Score={r[2]:.3f}")
    return results

if __name__ == "__main__":
    run_load_test()
