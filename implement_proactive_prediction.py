# -*- coding: utf-8 -*-
import os
import shutil
import sys
import re
import time
import subprocess
from datetime import datetime

print("🚀 Implementando sistema avanzado de predicción proactiva...")

# 1. Comprobar archivos necesarios
if not os.path.exists("predictor_integration.txt"):
    print("❌ Error: No se encuentra el archivo predictor_integration.txt")
    sys.exit(1)

if not os.path.exists("timeline_template.html"):
    print("❌ Error: No se encuentra el archivo timeline_template.html")
    sys.exit(1)

# 2. Realizar copia de seguridad
backup_dir = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
os.makedirs(backup_dir, exist_ok=True)

# Copiar archivos importantes
if os.path.exists("main.py"):
    shutil.copy("main.py", f"{backup_dir}/main.py")
print(f"✅ Copia de seguridad creada en {backup_dir}")

# 3. Leer archivo main.py actual
main_content = ""
with open("main.py", "r", encoding="utf-8") as f:
    main_content = f.read()

# 4. Leer cambios a integrar
with open("predictor_integration.txt", "r", encoding="utf-8") as f:
    integration_content = f.read()

# 5. Aplicar cambios al main.py
if "from predictor.simple_predictor import SimplePredictor" in main_content:
    # Reemplazar importación
    main_content = main_content.replace(
        "from predictor.simple_predictor import SimplePredictor",
        "from predictor.advanced_predictor import AdvancedPredictor"
    )
else:
    # Añadir importación si no existe
    import_line = "from predictor.advanced_predictor import AdvancedPredictor"
    main_content = re.sub(r'(# Importar componentes.*?)\n', f'\\1\n{import_line}\n', main_content, flags=re.DOTALL)

# Reemplazar inicialización del predictor
predictor_init_pattern = r"predictor_config = \{.*?self\.predictor\.load_prediction_models\(\)"
replacement = """predictor_config = {
            'prediction_threshold': self.config.get('prediction_threshold', 0.3),
            'min_history_points': 5,
            'max_prediction_hours': 24,
            'time_intervals': [1, 2, 4, 8, 12, 24],
            'data_dir': self.data_dir
        }
        self.predictor = AdvancedPredictor(predictor_config)
        self.predictor.load_prediction_models()"""

main_content = re.sub(predictor_init_pattern, replacement, main_content, flags=re.DOTALL)

# Reemplazar método de predicción
main_content = main_content.replace(
    "prediction = self.predictor.get_failure_prediction(service_id, metrics_list)",
    "prediction = self.predictor.get_failure_prediction_timeline(service_id, metrics_list)"
)

# Guardar main.py modificado
with open("main.py", "w", encoding="utf-8") as f:
    f.write(main_content)

print("✅ Archivo main.py actualizado")

# 6. Modificar la interfaz web para mostrar la línea temporal
# Encontrar la ubicación para insertar el template
if os.path.exists("templates/index.html"):
    with open("templates/index.html", "r", encoding="utf-8") as f:
        index_content = f.read()
    
    # Leer el template de línea temporal
    with open("timeline_template.html", "r", encoding="utf-8") as f:
        timeline_template = f.read()
    
    # Buscar el lugar para insertar (después del div de predicciones actual)
    if "id=\"predictionsHistory\"" in index_content:
        # Hacer una copia de seguridad
        shutil.copy("templates/index.html", f"{backup_dir}/index.html")
        
        # Insertar el template después del div de predictionsHistory
        index_content = index_content.replace(
            "<div id=\"predictionsHistory\">",
            "<div id=\"predictionsHistory\" style=\"display:none;\">"
        )
        
        index_content = index_content.replace(
            "</div>\n        </div>",
            "</div>\n        " + timeline_template + "\n        </div>",
            1
        )
        
        # Guardar el archivo modificado
        with open("templates/index.html", "w", encoding="utf-8") as f:
            f.write(index_content)
        
        print("✅ Interfaz web actualizada con línea temporal de predicciones")
    else:
        print("⚠️ No se pudo encontrar la ubicación para insertar la línea temporal")

# 7. Añadir endpoint de API para obtener línea temporal de predicciones
if os.path.exists("api.py"):
    with open("api.py", "r", encoding="utf-8") as f:
        api_content = f.read()
    
    # Hacer copia de seguridad
    shutil.copy("api.py", f"{backup_dir}/api.py")
    
    # Comprobar si ya existe el endpoint
    if "def predict_service(service_id):" in api_content:
        # Reemplazar el endpoint existente
        predict_pattern = r"@app\.route\('/api/predict/<service_id>'\).*?return jsonify\(prediction\)"
        replacement = """@app.route('/api/predict/<service_id>')
def predict_service(service_id):
    """Realiza una predicción para un servicio específico"""
    if not system:
        return jsonify({'error': 'System not running'})
    
    # Obtener horas para predecir
    hours = request.args.get('hours', default=system.predictor.max_prediction_hours, type=int)
    
    # Obtener métricas del servicio
    metrics_history = system.collector.metrics_history.get(service_id, [])
    
    if not metrics_history:
        return jsonify({'error': 'Service not found or no metrics available'})
    
    # Realizar predicción de línea temporal
    timeline = system.predictor.predict_timeline(service_id, metrics_history)
    
    if not timeline or not timeline.get('timeline'):
        return jsonify({'error': 'Could not generate prediction timeline'})
    
    return jsonify(timeline)"""
        
        api_content = re.sub(predict_pattern, replacement, api_content, flags=re.DOTALL)
        
        # Guardar el archivo modificado
        with open("api.py", "w", encoding="utf-8") as f:
            f.write(api_content)
        
        print("✅ API actualizado con endpoint de línea temporal")
    else:
        print("⚠️ No se pudo encontrar el endpoint para predicciones en api.py")

# 8. Crear datos de prueba con tendencia para demostrar predicción proactiva
print("Creando datos de prueba con tendencia para demostración...")

# Datos para app-server con tendencia creciente
from datetime import datetime, timedelta
import json
import random

app_server_data = []
base_time = datetime.now() - timedelta(hours=12)

# Crear histórico con tendencia creciente
for i in range(12):
    ts = (base_time + timedelta(hours=i)).isoformat()
    # Valor base + tendencia lineal + componente cuadrático pequeño + ruido
    memory = 40 + i * 2 + (i**2 * 0.05) + random.uniform(-1, 1)
    cpu = 30 + i * 3 + (i**2 * 0.05) + random.uniform(-2, 2)
    response_time = 150 + i * 10 + random.uniform(-10, 10)
    error_rate = 0.5 + i * 0.2 + random.uniform(-0.1, 0.1)
    
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

# Datos para database con tendencia creciente diferente
database_data = []

for i in range(12):
    ts = (base_time + timedelta(hours=i)).isoformat()
    # Tendencia más pronunciada en active_connections
    memory = 35 + i * 1.5 + random.uniform(-1, 1)
    cpu = 25 + i * 2 + random.uniform(-1.5, 1.5)
    connections = 40 + i * 4 + (i**2 * 0.1) + random.uniform(-2, 2)
    query_time = 40 + i * 2 + random.uniform(-3, 3)
    
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

print("✅ Datos de prueba con tendencia creados")

# 9. Configurar umbrales para detección
thresholds = {
    "default": {
        "memory_usage": 70,
        "cpu_usage": 80,
        "response_time_ms": 300,
        "error_rate": 5,
        "active_connections": 90,
        "query_time_avg": 100
    }
}

with open("./data/thresholds.json", "w", encoding="utf-8") as f:
    json.dump(thresholds, f, indent=2)

print("✅ Umbrales configurados para detección proactiva")

# 10. Actualizar configuración del sistema
import yaml
system_config = {
    "anomaly_threshold": 0.4,
    "execution_mode": "simulation",
    "auto_remediation": False,
    "processing_interval": 10,
    "prediction_threshold": 0.3,
    "prediction_horizon": 24,
    "prediction_interval": 600  # Reducir a 10 minutos para demostración
}

with open("./config/system_config.yaml", "w", encoding="utf-8") as f:
    yaml.dump(system_config, f)

print("✅ Configuración del sistema actualizada")

print("\n🎉 ¡Sistema de predicción proactiva implementado con éxito!")
print("\nPara activar el nuevo sistema:")
print("1. Cierra todas las ventanas del navegador con el dashboard")
print("2. Ejecuta estos comandos para reiniciar:")
print("   Get-Process -Name python -ErrorAction SilentlyContinue | Stop-Process -Force")
print("   python start.py")
print("3. Espera 30 segundos y navega a http://localhost:5000")
print("4. Explora la nueva vista de predicción con línea temporal")