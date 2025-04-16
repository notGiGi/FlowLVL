import numpy as np
import pandas as pd
import json
import os
import logging
from datetime import datetime, timedelta
from sklearn.ensemble import IsolationForest
from sklearn.cluster import DBSCAN
from sklearn.preprocessing import StandardScaler
import joblib

logger = logging.getLogger('service_profiler')

class ServiceProfiler:
    """
    Perfilador dinámico de servicios que aprende automáticamente el comportamiento normal
    y genera modelos de detección personalizados para cada servicio.
    """
    
    def __init__(self, config=None):
        self.config = config or {}
        self.models_dir = self.config.get('models_dir', './models/profiles')
        self.profiles_dir = self.config.get('profiles_dir', './data/profiles')
        self.training_window = self.config.get('training_window_days', 7)  # 1 semana
        self.min_samples = self.config.get('min_samples', 50)  # Mínimo para entrenar
        self.retrain_frequency = self.config.get('retrain_frequency_hours', 24)
        self.outlier_fraction = self.config.get('outlier_fraction', 0.05)  # 5% considerados anómalos
        
        # Asegurar que existan directorios
        os.makedirs(self.models_dir, exist_ok=True)
        os.makedirs(self.profiles_dir, exist_ok=True)
        
        # Perfiles de servicio - estructura:
        # {
        #   "service_id": {
        #     "metrics": ["mem_usage", "cpu_usage", ...],
        #     "bounds": {
        #       "mem_usage": {"lower": 10, "upper": 80, "baseline": 45},
        #       ...
        #     },
        #     "correlations": {
        #       "mem_usage_cpu_usage": 0.75,
        #       ...
        #     },
        #     "last_updated": "2025-04-15T10:30:00Z",
        #     "model_path": "path/to/model.joblib"
        #   },
        #   ...
        # }
        self.service_profiles = {}
        
        # Histórico de métricas por servicio
        self.metrics_history = {}
        
        # Última actualización de modelos por servicio
        self.last_model_update = {}
        
        # Cargar perfiles existentes
        self.load_profiles()
    
    def load_profiles(self):
        """Carga perfiles de servicio desde archivos"""
        profile_file = os.path.join(self.profiles_dir, 'service_profiles.json')
        
        if os.path.exists(profile_file):
            try:
                with open(profile_file, 'r') as f:
                    self.service_profiles = json.load(f)
                logger.info(f"Perfiles de servicio cargados: {len(self.service_profiles)} servicios")
            except Exception as e:
                logger.error(f"Error al cargar perfiles: {str(e)}")
    
    def save_profiles(self):
        """Guarda perfiles de servicio en archivo"""
        profile_file = os.path.join(self.profiles_dir, 'service_profiles.json')
        
        try:
            with open(profile_file, 'w') as f:
                json.dump(self.service_profiles, f, indent=2)
            logger.info("Perfiles de servicio guardados")
        except Exception as e:
            logger.error(f"Error al guardar perfiles: {str(e)}")
    
    def add_metrics_data(self, service_id, metrics, timestamp=None):
        """
        Añade datos de métricas para un servicio
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario de métricas {nombre: valor}
            timestamp: Timestamp (opcional)
        """
        if not timestamp:
            timestamp = datetime.now().isoformat()
            
        try:
            # Inicializar estructura si no existe
            if service_id not in self.metrics_history:
                self.metrics_history[service_id] = []
            
            # Añadir registro con timestamp
            metrics_copy = metrics.copy()
            metrics_copy['timestamp'] = timestamp
            self.metrics_history[service_id].append(metrics_copy)
            
            # Comprobar si es necesario actualizar perfil
            self.check_profile_update(service_id)
            
        except Exception as e:
            logger.error(f"Error al añadir datos de métricas: {str(e)}")
    
    def check_profile_update(self, service_id):
        """
        Comprueba si es necesario actualizar el perfil de un servicio
        """
        # Verificar si hay suficientes datos
        if service_id not in self.metrics_history or len(self.metrics_history[service_id]) < self.min_samples:
            return
        
        # Verificar si es hora de actualizar (o si es la primera vez)
        last_update = self.last_model_update.get(service_id)
        if last_update is None or (datetime.now() - datetime.fromisoformat(last_update)).total_seconds() / 3600 >= self.retrain_frequency:
            # Actualizar perfil
            self.update_service_profile(service_id)
            self.last_model_update[service_id] = datetime.now().isoformat()
    
    def update_service_profile(self, service_id):
        """
        Actualiza el perfil de un servicio con datos recientes
        """
        logger.info(f"Actualizando perfil para servicio: {service_id}")
        
        try:
            # Convertir a DataFrame para análisis
            df = pd.DataFrame(self.metrics_history[service_id])
            
            # Convertir timestamp a datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            
            # Filtrar datos dentro de la ventana de entrenamiento
            cutoff_date = datetime.now() - timedelta(days=self.training_window)
            df = df[df['timestamp'] >= pd.to_datetime(cutoff_date)]
            
            if len(df) < self.min_samples:
                logger.warning(f"Datos insuficientes para actualizar perfil de {service_id}: {len(df)} < {self.min_samples}")
                return
            
            # Obtener lista de métricas (excluyendo timestamp y service_id)
            metrics = [col for col in df.columns if col not in ['timestamp', 'service_id']]
            
            # Crear perfil inicial si no existe
            if service_id not in self.service_profiles:
                self.service_profiles[service_id] = {
                    "metrics": metrics,
                    "bounds": {},
                    "correlations": {},
                    "last_updated": datetime.now().isoformat()
                }
            
            # Actualizar métricas disponibles
            self.service_profiles[service_id]["metrics"] = metrics
            
            # Calcular límites para cada métrica
            for metric in metrics:
                # Verificar que la columna tiene datos numéricos
                if pd.api.types.is_numeric_dtype(df[metric]):
                    # Calcular estadísticas
                    q1 = df[metric].quantile(0.25)
                    q3 = df[metric].quantile(0.75)
                    iqr = q3 - q1
                    
                    # Límites basados en IQR
                    lower_bound = max(0, q1 - 1.5 * iqr)
                    upper_bound = q3 + 1.5 * iqr
                    
                    # Valor típico (mediana)
                    baseline = df[metric].median()
                    
                    # Guardar límites
                    self.service_profiles[service_id]["bounds"][metric] = {
                        "lower": float(lower_bound),
                        "upper": float(upper_bound),
                        "baseline": float(baseline),
                        "q1": float(q1),
                        "q3": float(q3)
                    }
            
            # Calcular correlaciones entre métricas
            if len(metrics) > 1:
                corr_matrix = df[metrics].corr()
                
                # Guardar correlaciones significativas (>0.5 o <-0.5)
                for i, metric1 in enumerate(metrics):
                    for j, metric2 in enumerate(metrics):
                        if i < j:  # Evitar duplicados
                            corr = corr_matrix.loc[metric1, metric2]
                            if abs(corr) >= 0.5:
                                corr_key = f"{metric1}_{metric2}"
                                self.service_profiles[service_id]["correlations"][corr_key] = float(corr)
            
            # Entrenar modelo de detección de anomalías
            self.train_anomaly_model(service_id, df, metrics)
            
            # Actualizar timestamp
            self.service_profiles[service_id]["last_updated"] = datetime.now().isoformat()
            
            # Guardar perfiles actualizados
            self.save_profiles()
            
        except Exception as e:
            logger.error(f"Error al actualizar perfil de servicio {service_id}: {str(e)}")
    
    def train_anomaly_model(self, service_id, df, metrics):
        """
        Entrena un modelo de detección de anomalías para un servicio
        
        Args:
            service_id: ID del servicio
            df: DataFrame con datos de métricas
            metrics: Lista de métricas a utilizar
        """
        try:
            # Preparar datos para entrenamiento (solo columnas numéricas)
            numeric_metrics = [m for m in metrics if pd.api.types.is_numeric_dtype(df[m])]
            if not numeric_metrics:
                logger.warning(f"No hay métricas numéricas para entrenar modelo de {service_id}")
                return
                
            X = df[numeric_metrics].copy()
            
            # Normalizar datos
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            
            # Entrenar modelo de Isolation Forest
            model = IsolationForest(
                contamination=self.outlier_fraction,
                random_state=42,
                n_jobs=-1
            )
            model.fit(X_scaled)
            
            # También entrenar un modelo DBSCAN para detección basada en densidad
            dbscan = DBSCAN(
                eps=0.5,
                min_samples=5
            )
            dbscan.fit(X_scaled)
            
            # Crear directorio para el servicio si no existe
            service_dir = os.path.join(self.models_dir, service_id)
            os.makedirs(service_dir, exist_ok=True)
            
            # Guardar modelos y scaler
            model_path = os.path.join(service_dir, 'isolation_forest.joblib')
            scaler_path = os.path.join(service_dir, 'scaler.joblib')
            dbscan_path = os.path.join(service_dir, 'dbscan.joblib')
            
            joblib.dump(model, model_path)
            joblib.dump(scaler, scaler_path)
            joblib.dump(dbscan, dbscan_path)
            
            # Guardar métricas utilizadas
            metrics_path = os.path.join(service_dir, 'metrics.json')
            with open(metrics_path, 'w') as f:
                json.dump(numeric_metrics, f)
            
            # Actualizar ruta del modelo en el perfil
            self.service_profiles[service_id]["model_path"] = model_path
            self.service_profiles[service_id]["scaler_path"] = scaler_path
            self.service_profiles[service_id]["dbscan_path"] = dbscan_path
            self.service_profiles[service_id]["metrics_path"] = metrics_path
            
            logger.info(f"Modelo de anomalías entrenado para {service_id} con {len(X)} muestras y {len(numeric_metrics)} métricas")
            
        except Exception as e:
            logger.error(f"Error al entrenar modelo para {service_id}: {str(e)}")
    
    def detect_anomaly(self, service_id, metrics):
        """
        Detecta anomalías basadas en el perfil y modelo del servicio
        
        Args:
            service_id: ID del servicio
            metrics: Diccionario de métricas actuales
            
        Returns:
            Tuple (is_anomaly, anomaly_score, details)
        """
        # Verificar si existe perfil para el servicio
        if service_id not in self.service_profiles:
            logger.warning(f"No hay perfil para servicio {service_id}, registrando datos para crear perfil")
            self.add_metrics_data(service_id, metrics)
            return False, 0.0, {"reason": "No profile available"}
        
        # Guardar métricas para futuro entrenamiento
        self.add_metrics_data(service_id, metrics)
        
        # Comprobar anomalías por límites
        bounds_score = self._check_bounds_anomaly(service_id, metrics)
        
        # Comprobar anomalías por correlaciones
        correlation_score = self._check_correlation_anomaly(service_id, metrics)
        
        # Comprobar anomalías por modelo (si existe)
        model_score = self._check_model_anomaly(service_id, metrics)
        
        # Combinar scores (dando más peso al modelo)
        if model_score is not None:
            anomaly_score = 0.5 * model_score + 0.3 * bounds_score + 0.2 * correlation_score
        else:
            anomaly_score = 0.7 * bounds_score + 0.3 * correlation_score
        
        # Determinar si es anomalía (umbral puede ajustarse)
        anomaly_threshold = self.config.get('anomaly_threshold', 0.6)
        is_anomaly = anomaly_score >= anomaly_threshold
        
        # Construir detalles
        details = {
            "bounds_score": bounds_score,
            "correlation_score": correlation_score,
            "model_score": model_score,
            "combined_score": anomaly_score,
            "threshold": anomaly_threshold
        }
        
        return is_anomaly, anomaly_score, details
    
    def _check_bounds_anomaly(self, service_id, metrics):
        """Comprueba anomalías basadas en límites de métricas"""
        profile = self.service_profiles[service_id]
        bounds = profile.get("bounds", {})
        
        anomalous_metrics = 0
        total_metrics = 0
        anomaly_severity = 0
        
        for metric, value in metrics.items():
            if metric in bounds and isinstance(value, (int, float)):
                total_metrics += 1
                metric_bounds = bounds[metric]
                
                # Comprobar si está fuera de límites
                if value < metric_bounds["lower"] or value > metric_bounds["upper"]:
                    anomalous_metrics += 1
                    
                    # Calcular severidad (qué tan lejos está del límite)
                    if value < metric_bounds["lower"]:
                        distance = (metric_bounds["lower"] - value) / max(1, (metric_bounds["baseline"] - metric_bounds["lower"]))
                    else:
                        distance = (value - metric_bounds["upper"]) / max(1, (metric_bounds["upper"] - metric_bounds["baseline"]))
                    
                    # Limitar severidad a un rango razonable
                    severity = min(1.0, distance)
                    anomaly_severity += severity
        
        # Calcular score final
        if total_metrics > 0:
            # Componente por proporción de métricas anómalas
            proportion_score = anomalous_metrics / total_metrics
            
            # Componente por severidad media
            severity_score = anomaly_severity / total_metrics
            
            # Combinar ambos (dando más peso a severidad)
            return 0.4 * proportion_score + 0.6 * severity_score
        
        return 0.0
    
    def _check_correlation_anomaly(self, service_id, metrics):
        """Comprueba anomalías basadas en correlaciones entre métricas"""
        profile = self.service_profiles[service_id]
        correlations = profile.get("correlations", {})
        bounds = profile.get("bounds", {})
        
        if not correlations or len(metrics) < 2:
            return 0.0
        
        correlation_violations = 0
        total_correlations = 0
        violation_severity = 0
        
        for corr_key, corr_value in correlations.items():
            # Separar las dos métricas
            metric1, metric2 = corr_key.split('_')
            
            if metric1 in metrics and metric2 in metrics and metric1 in bounds and metric2 in bounds:
                total_correlations += 1
                
                # Obtener valores actuales y líneas base
                value1 = metrics[metric1]
                value2 = metrics[metric2]
                baseline1 = bounds[metric1]["baseline"]
                baseline2 = bounds[metric2]["baseline"]
                
                # Calcular cambios relativos desde línea base
                change1 = (value1 - baseline1) / max(1, baseline1)
                change2 = (value2 - baseline2) / max(1, baseline2)
                
                # Si hay correlación positiva fuerte, los cambios deberían ir en la misma dirección
                # Si hay correlación negativa fuerte, los cambios deberían ir en direcciones opuestas
                expected_correlation = change1 * change2 * np.sign(corr_value)
                
                # Si el signo no coincide con la correlación esperada
                if expected_correlation < 0 and abs(change1) > 0.1 and abs(change2) > 0.1:
                    correlation_violations += 1
                    
                    # Calcular severidad de la violación
                    severity = min(1.0, (abs(change1) + abs(change2)) / 2)
                    violation_severity += severity
        
        # Calcular score final
        if total_correlations > 0:
            proportion_score = correlation_violations / total_correlations
            severity_score = violation_severity / total_correlations
            
            return 0.5 * proportion_score + 0.5 * severity_score
        
        return 0.0
    
    def _check_model_anomaly(self, service_id, metrics):
        """Comprueba anomalías basadas en modelo de ML"""
        profile = self.service_profiles[service_id]
        
        # Verificar si hay modelo
        model_path = profile.get("model_path")
        scaler_path = profile.get("scaler_path")
        metrics_path = profile.get("metrics_path")
        
        if not model_path or not os.path.exists(model_path):
            return None
        
        try:
            # Cargar modelo, scaler y métricas
            model = joblib.load(model_path)
            scaler = joblib.load(scaler_path)
            
            with open(metrics_path, 'r') as f:
                model_metrics = json.load(f)
            
            # Preparar datos para predicción
            X = []
            for metric in model_metrics:
                if metric in metrics:
                    X.append(metrics[metric])
                else:
                    return None  # Faltan métricas requeridas
            
            X = np.array(X).reshape(1, -1)
            
            # Normalizar datos
            X_scaled = scaler.transform(X)
            
            # Obtener score de anomalía
            # Para Isolation Forest: valores menores indican anomalías
            raw_score = model.decision_function(X_scaled)[0]
            
            # Convertir a formato donde mayor score = más anómalo
            anomaly_score = 1.0 - ((raw_score + 1.0) / 2.0)
            
            return anomaly_score
            
        except Exception as e:
            logger.error(f"Error al evaluar modelo para {service_id}: {str(e)}")
            return None
    
    def get_service_profile(self, service_id):
        """Obtiene el perfil de un servicio"""
        return self.service_profiles.get(service_id, None)
    
    def get_threshold_recommendations(self, service_id):
        """
        Genera recomendaciones de umbrales basadas en el perfil del servicio
        
        Returns:
            Dict de umbrales recomendados por métrica
        """
        if service_id not in self.service_profiles:
            return {}
        
        profile = self.service_profiles[service_id]
        bounds = profile.get("bounds", {})
        
        recommendations = {}
        
        for metric, bound_info in bounds.items():
            # Usar upper bound como umbral para métricas donde valores altos son problemáticos
            # Para algunas métricas específicas, usamos lower bound (ej: hit_rate)
            if metric in ["hit_rate", "success_rate", "availability"]:
                # Para estas métricas, valores bajos son problemáticos
                recommendations[metric] = bound_info["lower"]
            else:
                # Para la mayoría, valores altos son problemáticos
                recommendations[metric] = bound_info["upper"]
        
        return recommendations