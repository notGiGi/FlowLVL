# -*- coding: utf-8 -*-
from flask import Flask, jsonify, request, render_template
import threading
import os
import yaml
import json
import logging
from datetime import datetime
import argparse

# Importar sistema principal
from main import PredictiveMaintenanceSystem

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("api_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('api_server')

# Crear aplicación Flask
app = Flask(__name__, template_folder='./templates')

# Instancia global del sistema
system = None

@app.route('/')
def home():
    """Página principal"""
    return render_template('index.html')

@app.route('/api/status')
def status():
    """Obtiene estado del sistema"""
    if system:
        return jsonify(system.get_system_status())
    else:
        return jsonify({'status': 'not_running'})

@app.route('/api/events')
def events():
    """Obtiene eventos del sistema"""
    if not system:
        return jsonify([])
    
    # Parsear parámetros
    limit = request.args.get('limit', default=50, type=int)
    event_type = request.args.get('type')
    service_id = request.args.get('service_id')
    
    events = system.get_events(limit, event_type, service_id)
    return jsonify(events)

@app.route('/api/services')
def services():
    """Obtiene servicios monitoreados"""
    if not system:
        return jsonify([])
    
    result = []
    for service_id, metrics_list in system.collector.metrics_history.items():
        if metrics_list:
            latest = metrics_list[-1]
            result.append({
                'service_id': service_id,
                'last_update': latest.get('timestamp'),
                'metrics': {k: v for k, v in latest.items() if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float))}
            })
    
    return jsonify(result)

@app.route('/api/service/<service_id>')
def service_detail(service_id):
    """Obtiene detalles de un servicio"""
    if not system:
        return jsonify({'error': 'System not running'})
    
    # Obtener métricas
    metrics_history = system.collector.metrics_history.get(service_id, [])
    
    if not metrics_history:
        return jsonify({'error': 'Service not found'})
    
    # Obtener eventos
    events = system.get_events(limit=50, service_id=service_id)
    
    # Obtener umbrales
    thresholds = {}
    for metric in metrics_history[-1]:
        if metric not in ['service_id', 'timestamp'] and isinstance(metrics_history[-1][metric], (int, float)):
            threshold = system.detector.get_threshold(service_id, metric)
            if threshold:
                thresholds[metric] = threshold
    
    return jsonify({
        'service_id': service_id,
        'last_update': metrics_history[-1].get('timestamp'),
        'metrics': {k: v for k, v in metrics_history[-1].items() if k not in ['service_id', 'timestamp'] and isinstance(v, (int, float))},
        'thresholds': thresholds,
        'events': events
    })

@app.route('/api/actions')
def actions():
    """Obtiene historial de acciones"""
    if not system:
        return jsonify([])
    
    service_id = request.args.get('service_id')
    limit = request.args.get('limit', default=10, type=int)
    
    return jsonify(system.recommender.get_action_history(service_id, limit))

@app.route('/api/threshold', methods=['POST'])
def set_threshold():
    """Establece umbral personalizado"""
    if not system:
        return jsonify({'error': 'System not running'})
    
    data = request.json
    if not data or 'service_id' not in data or 'metric' not in data or 'value' not in data:
        return jsonify({'error': 'Missing required fields'})
    
    service_id = data['service_id']
    metric = data['metric']
    value = float(data['value'])
    
    success = system.set_threshold(service_id, metric, value)
    
    return jsonify({'success': success})

@app.route('/api/mode', methods=['POST'])
def set_mode():
    """Cambia modo de ejecución"""
    if not system:
        return jsonify({'error': 'System not running'})
    
    data = request.json
    if not data or 'mode' not in data:
        return jsonify({'error': 'Missing mode'})
    
    mode = data['mode']
    if mode not in ['simulation', 'real']:
        return jsonify({'error': 'Invalid mode'})
    
    success = system.set_execution_mode(mode)
    
    return jsonify({'success': success})

@app.route('/api/predictions')
def get_predictions():
    """Obtiene predicciones de anomalías"""
    if not system:
        return jsonify([])
    
    # Parsear parámetros
    limit = request.args.get('limit', default=10, type=int)
    service_id = request.args.get('service_id')
    
    # Obtener predicciones
    result = system.predictor.get_prediction_history(service_id, limit)
    return jsonify(result)

@app.route('/api/predict/<service_id>')
def predict_service(service_id):
    """Realiza una predicción para un servicio específico"""
    if not system:
        return jsonify({'error': 'System not running'})
    
    # Obtener horas para predecir
    hours = request.args.get('hours', default=24, type=int)
    
    # Obtener métricas del servicio
    metrics_history = system.collector.metrics_history.get(service_id, [])
    
    if not metrics_history:
        return jsonify({'error': 'Service not found or no metrics available'})
    
    # Realizar predicción de línea temporal
    timeline = system.predictor.predict_timeline(service_id, metrics_history)
    
    if not timeline or not timeline.get('timeline'):
        return jsonify({'error': 'Could not generate prediction timeline'})
    
    return jsonify(timeline)

def run_server(config_path, host='0.0.0.0', port=5000):
    """Inicia servidor API"""
    global system
    
    # Cargar configuración
    config = {}
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    else:
        logger.warning(f"Archivo de configuración no encontrado: {config_path}")
        logger.warning("Usando configuración por defecto")
    
    # Inicializar sistema
    system = PredictiveMaintenanceSystem(config)
    
    # Iniciar sistema en thread separado
    system_thread = threading.Thread(target=system.start)
    system_thread.daemon = True
    system_thread.start()
    
    # Iniciar servidor Flask
    app.run(host=host, port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    # Parsear argumentos
    parser = argparse.ArgumentParser(description='API para Sistema de Mantenimiento Predictivo')
    parser.add_argument('--config', help='Ruta al archivo de configuración', default='./config/system_config.yaml')
    parser.add_argument('--host', help='Host para el servidor API', default='0.0.0.0')
    parser.add_argument('--port', help='Puerto para el servidor API', type=int, default=5000)
    
    args = parser.parse_args()
    
    # Iniciar servidor
    run_server(args.config, args.host, args.port)