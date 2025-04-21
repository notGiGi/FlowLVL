# -*- coding: utf-8 -*-
import json
import os
import time
import requests

def check_anomalies():
    print("Verificando detección de anomalías...")
    
    try:
        # Intentar obtener eventos del API
        response = requests.get("http://localhost:5000/api/events?limit=10", timeout=2)
        if response.status_code == 200:
            events = response.json()
            
            anomalies_detected = 0
            for event in events:
                if event.get('type') == 'anomaly_detection' and event.get('is_anomaly', False):
                    anomalies_detected += 1
                    print(f"✅ Anomalía detectada en {event.get('service_id')} con score {event.get('anomaly_score', 0):.3f}")
            
            if anomalies_detected == 0:
                print("❌ No se detectaron anomalías en los eventos recientes")
                print("   Verificando umbrales y configuración...")
                
                # Verificar umbrales
                if os.path.exists('./data/thresholds.json'):
                    with open('./data/thresholds.json', 'r', encoding='utf-8') as f:
                        thresholds = json.load(f)
                    print(f"\nUmbrales actuales:")
                    print(json.dumps(thresholds, indent=2))
                
                # Verificar configuración
                if os.path.exists('./config/system_config.yaml'):
                    with open('./config/system_config.yaml', 'r', encoding='utf-8') as f:
                        import yaml
                        config = yaml.safe_load(f)
                    print(f"\nConfiguración del sistema:")
                    print(yaml.dump(config, default_flow_style=False))
                
                print("\n❓ Recomendación: Reinicia el sistema completo con:")
                print("   python start.py")
            else:
                print(f"\n✅ Total de anomalías detectadas: {anomalies_detected}")
                
        else:
            print(f"❌ Error al obtener eventos: {response.status_code}")
    except Exception as e:
        print(f"❌ Error al verificar anomalías: {e}")

if __name__ == "__main__":
    print("Esperando 30 segundos para que el sistema procese las anomalías...")
    time.sleep(30)
    check_anomalies()