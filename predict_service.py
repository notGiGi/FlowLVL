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