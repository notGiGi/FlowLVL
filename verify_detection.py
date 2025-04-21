# -*- coding: utf-8 -*-
import requests
import time
import json
import sys

def check_detection():
    print("Verificando detección de anomalías...")
    try:
        response = requests.get("http://localhost:5000/api/events?limit=10", timeout=5)
        if response.status_code == 200:
            events = response.json()
            anomalies = [e for e in events if e.get('type') == 'anomaly_detection' and e.get('is_anomaly', False)]
            
            print(f"Encontrados {len(anomalies)} eventos de anomalía:")
            for anomaly in anomalies:
                service = anomaly.get('service_id', 'desconocido')
                score = anomaly.get('anomaly_score', 0)
                print(f"✅ Anomalía en {service}: Score {score:.3f}")
                
            if not anomalies:
                print("❌ No se encontraron anomalías")
                print("   Posibles razones:")
                print("   1. El sistema no ha procesado las métricas todavía (espera más tiempo)")
                print("   2. El detector no está identificando correctamente las anomalías")
                print("   3. El servidor API no está respondiendo correctamente")
        else:
            print(f"❌ Error en la respuesta del API: {response.status_code}")
    except Exception as e:
        print(f"❌ Error al verificar anomalías: {e}")

if __name__ == "__main__":
    print("Esperando 30 segundos para que el sistema procese los datos...")
    for i in range(30, 0, -1):
        sys.stdout.write(f"\rEsperando {i} segundos...")
        sys.stdout.flush()
        time.sleep(1)
    print("\nVerificando anomalías...")
    check_detection()
