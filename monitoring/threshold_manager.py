import numpy as np
import json
import os
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('threshold_manager')

class AdaptiveThresholdManager:
    """
    Gestor de umbrales adaptativos que se ajustan según el comportamiento histórico
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.data_dir = self.config.get('data_dir', './data/thresholds')
        self.history_window = self.config.get('history_window_days', 14)  # 2 semanas
        self.min_samples = self.config.get('min_samples', 100)
        self.adjustment_frequency = self.config.get('adjustment_frequency_hours', 24)
        self.sensitivity = self.config.get('sensitivity', 3.0)  # 3 desviaciones estándar
        
        # Crear directorio si no existe
        os.makedirs(self.data_dir, exist_ok=True)
        
        # Umbrales por defecto
        self.default_thresholds = {
            "memory_usage": 65.0,
            "gc_collection_time": 400.0,
            "active_connections": 85.0,
            "connection_wait_time": 150.0,
            "memory_fragmentation_ratio": 2.0,
            "hit_rate": 85.0,
            "cpu_usage": 80.0,
            "response_time_ms": 500.0,
            "error_rate": 5.0
        }
        
        # Umbrales actuales (inicializar con valores por defecto)
        self.current_thresholds = self.default_thresholds.copy()
        
        # Histórico de métricas por servicio
        self.metrics_history = {}
        
        # Cargar histórico y umbrales
        self.load_thresholds()
        self.load_history()
        
        # Última actualización
        self.last_adjustment = datetime.now()
    
    def load_thresholds(self):
        """Carga umbrales personalizados desde archivo"""
        threshold_file = os.path.join(self.data_dir, 'current_thresholds.json')
        
        if os.path.exists(threshold_file):
            try:
                with open(threshold_file, 'r') as f:
                    self.current_thresholds = json.load(f)
                logger.info("Umbrales cargados desde archivo")
            except Exception as e:
                logger.error(f"Error al cargar umbrales: {str(e)}")
    
    def save_thresholds(self):
        """Guarda umbrales actuales en archivo"""
        threshold_file = os.path.join(self.data_dir, 'current_thresholds.json')
        
        try:
            with open(threshold_file, 'w') as f:
                json.dump(self.current_thresholds, f, indent=2)
            logger.info("Umbrales guardados en archivo")
        except Exception as e:
            logger.error(f"Error al guardar umbrales: {str(e)}")
    
    def load_history(self):
        """Carga histórico de métricas desde archivo"""
        history_file = os.path.join(self.data_dir, 'metrics_history.json')
        
        if os.path.exists(history_file):
            try:
                with open(history_file, 'r') as f:
                    self.metrics_history = json.load(f)
                logger.info("Histórico de métricas cargado desde archivo")
            except Exception as e:
                logger.error(f"Error al cargar histórico: {str(e)}")
    
    def save_history(self):
        """Guarda histórico de métricas en archivo"""
        history_file = os.path.join(self.data_dir, 'metrics_history.json')
        
        try:
            # Limitar tamaño de histórico para evitar crecimiento excesivo
            for service_id in self.metrics_history:
                for metric in self.metrics_history[service_id]:
                    # Mantener solo datos dentro de la ventana
                    cutoff_date = (datetime.now() - timedelta(days=self.history_window)).isoformat()
                    self.metrics_history[service_id][metric] = [
                        entry for entry in self.metrics_history[service_id][metric]
                        if entry['timestamp'] >= cutoff_date
                    ]
            
            with open(history_file, 'w') as f:
                json.dump(self.metrics_history, f)
            logger.info("Histórico de métricas guardado en archivo")
        except Exception as e:
            logger.error(f"Error al guardar histórico: {str(e)}")
    
    def record_metric(self, service_id, metric_name, value, timestamp=None):
        """
        Registra un valor de métrica en el histórico
        
        Args:
            service_id: ID del servicio
            metric_name: Nombre de la métrica
            value: Valor de la métrica
            timestamp: Timestamp (opcional, usa actual si no se proporciona)
        """
        if not timestamp:
            timestamp = datetime.now().isoformat()
        
        try:
            # Inicializar estructura si no existe
            if service_id not in self.metrics_history:
                self.metrics_history[service_id] = {}
            
            if metric_name not in self.metrics_history[service_id]:
                self.metrics_history[service_id][metric_name] = []
            
            # Añadir entrada
            self.metrics_history[service_id][metric_name].append({
                'timestamp': timestamp,
                'value': value
            })
            
            # Comprobar si es momento de ajustar umbrales
            time_since_adjustment = (datetime.now() - self.last_adjustment).total_seconds() / 3600
            if time_since_adjustment >= self.adjustment_frequency:
                self.adjust_thresholds()
                self.last_adjustment = datetime.now()
                
        except Exception as e:
            logger.error(f"Error al registrar métrica: {str(e)}")
    
    def adjust_thresholds(self):
        """Ajusta umbrales basados en datos históricos"""
        logger.info("Ajustando umbrales basados en datos históricos")
        
        metrics_to_adjust = set()
        
        # Recopilar todas las métricas disponibles
        for service_id in self.metrics_history:
            for metric_name in self.metrics_history[service_id]:
                metrics_to_adjust.add(metric_name)
        
        # Ajustar cada métrica
        for metric_name in metrics_to_adjust:
            if metric_name not in self.current_thresholds:
                continue
                
            # Recopilar todos los valores para esta métrica
            all_values = []
            for service_id in self.metrics_history:
                if metric_name in self.metrics_history[service_id]:
                    # Obtener valores dentro de la ventana de tiempo
                    cutoff_date = (datetime.now() - timedelta(days=self.history_window)).isoformat()
                    recent_entries = [
                        entry for entry in self.metrics_history[service_id][metric_name]
                        if entry['timestamp'] >= cutoff_date
                    ]
                    
                    values = [entry['value'] for entry in recent_entries]
                    all_values.extend(values)
            
            # Si hay suficientes datos, calcular nuevo umbral
            if len(all_values) >= self.min_samples:
                # Calcular estadísticas
                mean_value = np.mean(all_values)
                std_value = np.std(all_values)
                
                # Calcular nuevo umbral (media + N desviaciones estándar)
                # Para métricas donde valores altos son problemáticos
                if metric_name != 'hit_rate':  # Caso especial
                    new_threshold = mean_value + (std_value * self.sensitivity)
                    
                    # Casos especiales para cada métrica
                    if metric_name == 'memory_usage':
                        # Limitar entre 60% y 90%
                        new_threshold = max(60, min(90, new_threshold))
                    elif metric_name == 'gc_collection_time':
                        # Limitar entre 300ms y 1000ms
                        new_threshold = max(300, min(1000, new_threshold))
                else:
                    # Para hit_rate, valores bajos son problemáticos
                    new_threshold = mean_value - (std_value * self.sensitivity)
                    # Limitar entre 70% y 99%
                    new_threshold = max(70, min(99, new_threshold))
                
                # Actualizar umbral
                self.current_thresholds[metric_name] = round(new_threshold, 1)
                logger.info(f"Umbral ajustado para {metric_name}: {self.current_thresholds[metric_name]}")
        
        # Guardar umbrales actualizados
        self.save_thresholds()
        self.save_history()
    
    def get_threshold(self, metric_name):
        """Obtiene el umbral actual para una métrica"""
        return self.current_thresholds.get(metric_name, self.default_thresholds.get(metric_name, 0))
    
    def reset_to_defaults(self):
        """Restablece todos los umbrales a valores por defecto"""
        self.current_thresholds = self.default_thresholds.copy()
        self.save_thresholds()
        logger.info("Umbrales restablecidos a valores por defecto")