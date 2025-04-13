from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import json
import logging
import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, text
from kafka import KafkaProducer
import asyncio
import uvicorn
import time

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("api")

# Modelos de datos
class Metric(BaseModel):
    timestamp: str
    service_id: str
    metric_name: str
    metric_value: float
    node_id: Optional[str] = None
    
class Service(BaseModel):
    service_id: str
    service_name: str
    service_type: str
    first_seen: str
    last_seen: str
    metadata: Dict[str, Any] = {}
    
class Anomaly(BaseModel):
    timestamp: str
    service_id: str
    node_id: Optional[str] = None
    anomaly_score: float
    anomaly_details: Dict[str, Any] = {}
    
class Failure(BaseModel):
    timestamp: str
    service_id: str
    node_id: Optional[str] = None
    failure_type: str
    failure_description: str
    
class Prediction(BaseModel):
    timestamp: str
    service_id: str
    node_id: Optional[str] = None
    failure_probability: float
    prediction_horizon: int
    
class Action(BaseModel):
    timestamp: str
    service_id: str
    node_id: Optional[str] = None
    issue_type: str
    action_id: str
    executed: bool
    success: Optional[bool] = None
    
class ManualMetric(BaseModel):
    service_id: str
    node_id: Optional[str] = None
    metrics: Dict[str, float]
    
class ManualFailure(BaseModel):
    service_id: str
    node_id: Optional[str] = None
    failure_type: str
    failure_description: str
    
class ManualAction(BaseModel):
    action_id: str
    service_id: str
    node_id: Optional[str] = None
    parameters: Dict[str, Any] = {}
    
class TimeRange(BaseModel):
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    limit: int = 100
    
class HealthStatus(BaseModel):
    status: str
    version: str
    components: Dict[str, str]
    timestamp: str

# Crear aplicación FastAPI
app = FastAPI(
    title="Predictive Maintenance API",
    description="API para el sistema de mantenimiento predictivo de sistemas distribuidos",
    version="1.0.0"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de base de datos
def get_db_engine():
    """Crea la conexión a la base de datos"""
    db_host = os.environ.get('DB_HOST', 'timescaledb')
    db_port = os.environ.get('DB_PORT', '5432')
    db_user = os.environ.get('DB_USER', 'predictor')
    db_password = os.environ.get('DB_PASSWORD', 'predictor_password')
    db_name = os.environ.get('DB_NAME', 'metrics_db')
    
    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    engine = create_engine(db_url)
    return engine

# Configuración de Kafka
def get_kafka_producer():
    """Crea el productor de Kafka"""
    kafka_servers = os.environ.get('KAFKA_BOOTSTRAP_SERVERS', 'kafka:29092')
    producer = KafkaProducer(
        bootstrap_servers=kafka_servers,
        value_serializer=lambda x: json.dumps(x).encode('utf-8')
    )
    return producer

# Variable global para el productor Kafka
kafka_producer = None

@app.on_event("startup")
async def startup_event():
    """Inicializa recursos al iniciar la aplicación"""
    global kafka_producer
    
    # Inicializar productor Kafka
    kafka_producer = get_kafka_producer()
    
    # Inicializar conexión a base de datos
    engine = get_db_engine()
    
    # Verificar conexión a base de datos
    try:
        result = engine.execute(text("SELECT 1"))
        logger.info("Conexión a base de datos establecida correctamente")
    except Exception as e:
        logger.error(f"Error al conectar a la base de datos: {str(e)}")
    
    logger.info("API REST iniciada correctamente")

@app.on_event("shutdown")
async def shutdown_event():
    """Libera recursos al detener la aplicación"""
    global kafka_producer
    
    # Cerrar productor Kafka
    if kafka_producer:
        kafka_producer.close()
    
    logger.info("API REST detenida correctamente")

# Endpoints para información general
@app.get("/", tags=["General"])
async def root():
    """Información general sobre la API"""
    return {
        "name": "Predictive Maintenance API",
        "version": "1.0.0",
        "description": "API para el sistema de mantenimiento predictivo de sistemas distribuidos"
    }

@app.get("/health", tags=["General"], response_model=HealthStatus)
async def health_check():
    """Verificar el estado de salud del sistema"""
    components = {}
    
    # Verificar conexión a base de datos
    try:
        engine = get_db_engine()
        result = engine.execute(text("SELECT 1"))
        components["database"] = "healthy"
    except Exception as e:
        components["database"] = f"unhealthy: {str(e)}"
    
    # Verificar conexión a Kafka
    try:
        if kafka_producer:
            kafka_producer.metrics()
            components["kafka"] = "healthy"
        else:
            components["kafka"] = "unhealthy: not initialized"
    except Exception as e:
        components["kafka"] = f"unhealthy: {str(e)}"
    
    # Estado general
    if all(status == "healthy" for status in components.values()):
        status = "healthy"
    else:
        status = "degraded"
    
    return HealthStatus(
        status=status,
        version="1.0.0",
        components=components,
        timestamp=datetime.now().isoformat()
    )

# Endpoints para servicios
@app.get("/services", tags=["Services"], response_model=List[Service])
async def get_services():
    """Obtener lista de servicios monitoreados"""
    try:
        engine = get_db_engine()
        query = "SELECT * FROM services ORDER BY last_seen DESC"
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        services = []
        for _, row in df.iterrows():
            service = Service(
                service_id=row['service_id'],
                service_name=row['service_name'],
                service_type=row['service_type'],
                first_seen=row['first_seen'].isoformat(),
                last_seen=row['last_seen'].isoformat(),
                metadata=row['metadata'] if isinstance(row['metadata'], dict) else {}
            )
            services.append(service)
        
        return services
    
    except Exception as e:
        logger.error(f"Error al obtener servicios: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener servicios: {str(e)}")

@app.get("/services/{service_id}", tags=["Services"], response_model=Service)
async def get_service(service_id: str):
    """Obtener información de un servicio específico"""
    try:
        engine = get_db_engine()
        query = f"SELECT * FROM services WHERE service_id = '{service_id}'"
        df = pd.read_sql(query, engine)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Servicio {service_id} no encontrado")
        
        row = df.iloc[0]
        service = Service(
            service_id=row['service_id'],
            service_name=row['service_name'],
            service_type=row['service_type'],
            first_seen=row['first_seen'].isoformat(),
            last_seen=row['last_seen'].isoformat(),
            metadata=row['metadata'] if isinstance(row['metadata'], dict) else {}
        )
        
        return service
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener servicio {service_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener servicio: {str(e)}")

# Endpoints para métricas
@app.get("/metrics", tags=["Metrics"], response_model=List[Metric])
async def get_metrics(
    service_id: Optional[str] = None,
    metric_name: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Obtener métricas filtradas por diversos criterios"""
    try:
        engine = get_db_engine()
        
        # Construir consulta base
        query = "SELECT * FROM metrics WHERE 1=1"
        
        # Añadir filtros
        if service_id:
            query += f" AND service_id = '{service_id}'"
        
        if metric_name:
            query += f" AND metric_name = '{metric_name}'"
        
        if start_time:
            query += f" AND timestamp >= '{start_time}'"
        
        if end_time:
            query += f" AND timestamp <= '{end_time}'"
        
        # Añadir orden y límite
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        metrics = []
        for _, row in df.iterrows():
            metric = Metric(
                timestamp=row['timestamp'].isoformat(),
                service_id=row['service_id'],
                node_id=row['node_id'],
                metric_name=row['metric_name'],
                metric_value=float(row['metric_value'])
            )
            metrics.append(metric)
        
        return metrics
    
    except Exception as e:
        logger.error(f"Error al obtener métricas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener métricas: {str(e)}")

@app.post("/metrics", tags=["Metrics"])
async def add_metric(metric: ManualMetric, background_tasks: BackgroundTasks):
    """Añadir métricas manualmente"""
    try:
        # Validar que hay al menos una métrica
        if not metric.metrics:
            raise HTTPException(status_code=400, detail="No se especificaron métricas")
        
        # Crear mensaje para Kafka
        timestamp = datetime.now().isoformat()
        
        metrics_data = {
            'timestamp': timestamp,
            'service_id': metric.service_id,
            'node_id': metric.node_id if metric.node_id else 'manual',
            'collector_type': 'manual'
        }
        
        # Añadir métricas
        for key, value in metric.metrics.items():
            metrics_data[key] = value
        
        # Enviar a Kafka en background para no bloquear la respuesta
        background_tasks.add_task(kafka_producer.send, 'raw_metrics', metrics_data)
        
        return {
            "status": "success",
            "message": f"Métricas enviadas para servicio {metric.service_id}",
            "timestamp": timestamp
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al añadir métricas: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al añadir métricas: {str(e)}")

# Endpoints para anomalías
@app.get("/anomalies", tags=["Anomalies"], response_model=List[Anomaly])
async def get_anomalies(
    service_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    min_score: float = Query(0.5, ge=0, le=1),
    limit: int = Query(100, ge=1, le=1000)
):
    """Obtener anomalías detectadas"""
    try:
        engine = get_db_engine()
        
        # Construir consulta base
        query = f"SELECT * FROM anomalies WHERE anomaly_score >= {min_score}"
        
        # Añadir filtros
        if service_id:
            query += f" AND service_id = '{service_id}'"
        
        if start_time:
            query += f" AND timestamp >= '{start_time}'"
        
        if end_time:
            query += f" AND timestamp <= '{end_time}'"
        
        # Añadir orden y límite
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        anomalies = []
        for _, row in df.iterrows():
            anomaly_details = row['anomaly_details']
            if isinstance(anomaly_details, str):
                try:
                    anomaly_details = json.loads(anomaly_details)
                except:
                    anomaly_details = {}
            
            anomaly = Anomaly(
                timestamp=row['timestamp'].isoformat(),
                service_id=row['service_id'],
                node_id=row['node_id'],
                anomaly_score=float(row['anomaly_score']),
                anomaly_details=anomaly_details
            )
            anomalies.append(anomaly)
        
        return anomalies
    
    except Exception as e:
        logger.error(f"Error al obtener anomalías: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener anomalías: {str(e)}")

# Endpoints para fallos
@app.get("/failures", tags=["Failures"], response_model=List[Failure])
async def get_failures(
    service_id: Optional[str] = None,
    failure_type: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Obtener fallos registrados"""
    try:
        engine = get_db_engine()
        
        # Construir consulta base
        query = "SELECT * FROM failures WHERE 1=1"
        
        # Añadir filtros
        if service_id:
            query += f" AND service_id = '{service_id}'"
        
        if failure_type:
            query += f" AND failure_type = '{failure_type}'"
        
        if start_time:
            query += f" AND timestamp >= '{start_time}'"
        
        if end_time:
            query += f" AND timestamp <= '{end_time}'"
        
        # Añadir orden y límite
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        failures = []
        for _, row in df.iterrows():
            failure = Failure(
                timestamp=row['timestamp'].isoformat(),
                service_id=row['service_id'],
                node_id=row['node_id'],
                failure_type=row['failure_type'],
                failure_description=row['failure_description']
            )
            failures.append(failure)
        
        return failures
    
    except Exception as e:
        logger.error(f"Error al obtener fallos: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener fallos: {str(e)}")

@app.post("/failures", tags=["Failures"])
async def add_failure(failure: ManualFailure, background_tasks: BackgroundTasks):
    """Registrar un fallo manualmente"""
    try:
        # Crear mensaje para Kafka
        timestamp = datetime.now().isoformat()
        
        failure_data = {
            'timestamp': timestamp,
            'service_id': failure.service_id,
            'node_id': failure.node_id if failure.node_id else 'manual',
            'failure_type': failure.failure_type,
            'failure_description': failure.failure_description,
            'manual': True
        }
        
        # Enviar a Kafka en background para no bloquear la respuesta
        background_tasks.add_task(kafka_producer.send, 'failures', failure_data)
        
        # También insertar directamente en la base de datos
        engine = get_db_engine()
        failure_df = pd.DataFrame([{
            'timestamp': datetime.now(),
            'service_id': failure.service_id,
            'node_id': failure.node_id if failure.node_id else 'manual',
            'failure_type': failure.failure_type,
            'failure_description': failure.failure_description,
            'failure_data': json.dumps({'manual': True})
        }])
        
        failure_df.to_sql('failures', engine, if_exists='append', index=False)
        
        return {
            "status": "success",
            "message": f"Fallo registrado para servicio {failure.service_id}",
            "timestamp": timestamp
        }
    
    except Exception as e:
        logger.error(f"Error al registrar fallo: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al registrar fallo: {str(e)}")

# Endpoints para predicciones
@app.get("/predictions", tags=["Predictions"], response_model=List[Prediction])
async def get_predictions(
    service_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    min_probability: float = Query(0.5, ge=0, le=1),
    limit: int = Query(100, ge=1, le=1000)
):
    """Obtener predicciones de fallos"""
    try:
        engine = get_db_engine()
        
        # Construir consulta base
        query = f"SELECT * FROM failure_predictions WHERE failure_probability >= {min_probability}"
        
        # Añadir filtros
        if service_id:
            query += f" AND service_id = '{service_id}'"
        
        if start_time:
            query += f" AND timestamp >= '{start_time}'"
        
        if end_time:
            query += f" AND timestamp <= '{end_time}'"
        
        # Añadir orden y límite
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        predictions = []
        for _, row in df.iterrows():
            prediction = Prediction(
                timestamp=row['timestamp'].isoformat(),
                service_id=row['service_id'],
                node_id=row['node_id'],
                failure_probability=float(row['failure_probability']),
                prediction_horizon=int(row['prediction_horizon'])
            )
            predictions.append(prediction)
        
        return predictions
    
    except Exception as e:
        logger.error(f"Error al obtener predicciones: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener predicciones: {str(e)}")

# Endpoints para acciones
@app.get("/actions", tags=["Actions"], response_model=List[Action])
async def get_actions(
    service_id: Optional[str] = None,
    issue_type: Optional[str] = None,
    executed: Optional[bool] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000)
):
    """Obtener acciones recomendadas o ejecutadas"""
    try:
        engine = get_db_engine()
        
        # Construir consulta base
        query = "SELECT * FROM recommendations WHERE 1=1"
        
        # Añadir filtros
        if service_id:
            query += f" AND service_id = '{service_id}'"
        
        if issue_type:
            query += f" AND issue_type = '{issue_type}'"
        
        if executed is not None:
            query += f" AND executed = {executed}"
        
        if start_time:
            query += f" AND timestamp >= '{start_time}'"
        
        if end_time:
            query += f" AND timestamp <= '{end_time}'"
        
        # Añadir orden y límite
        query += f" ORDER BY timestamp DESC LIMIT {limit}"
        
        df = pd.read_sql(query, engine)
        
        if df.empty:
            return []
        
        # Convertir DataFrame a lista de diccionarios
        actions = []
        for _, row in df.iterrows():
            action = Action(
                timestamp=row['timestamp'].isoformat(),
                service_id=row['service_id'],
                node_id=row['node_id'],
                issue_type=row['issue_type'],
                action_id=row['action_id'],
                executed=bool(row['executed']),
                success=bool(row['success']) if row['success'] is not None else None
            )
            actions.append(action)
        
        return actions
    
    except Exception as e:
        logger.error(f"Error al obtener acciones: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener acciones: {str(e)}")

@app.post("/actions/execute", tags=["Actions"])
async def execute_action(action: ManualAction, background_tasks: BackgroundTasks):
    """Ejecutar una acción manualmente"""
    try:
        # Crear mensaje para Kafka
        timestamp = datetime.now().isoformat()
        
        action_data = {
            'timestamp': timestamp,
            'service_id': action.service_id,
            'node_id': action.node_id if action.node_id else 'manual',
            'action_id': action.action_id,
            'parameters': action.parameters,
            'manual': True,
            'execution_requested': True
        }
        
        # Enviar a Kafka en background para no bloquear la respuesta
        background_tasks.add_task(kafka_producer.send, 'action_requests', action_data)
        
        return {
            "status": "success",
            "message": f"Ejecución de acción solicitada: {action.action_id} para servicio {action.service_id}",
            "timestamp": timestamp
        }
    
    except Exception as e:
        logger.error(f"Error al ejecutar acción: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al ejecutar acción: {str(e)}")

# Endpoints para estadísticas
@app.get("/stats/overview", tags=["Statistics"])
async def get_overview_stats():
    """Obtener estadísticas generales del sistema"""
    try:
        engine = get_db_engine()
        
        stats = {}
        
        # Total de servicios monitoreados
        query = "SELECT COUNT(*) as count FROM services"
        df = pd.read_sql(query, engine)
        stats['total_services'] = int(df['count'].iloc[0])
        
        # Total de métricas recolectadas
        query = "SELECT COUNT(*) as count FROM metrics"
        df = pd.read_sql(query, engine)
        stats['total_metrics'] = int(df['count'].iloc[0])
        
        # Total de anomalías detectadas
        query = "SELECT COUNT(*) as count FROM anomalies"
        df = pd.read_sql(query, engine)
        stats['total_anomalies'] = int(df['count'].iloc[0])
        
        # Total de fallos registrados
        query = "SELECT COUNT(*) as count FROM failures"
        df = pd.read_sql(query, engine)
        stats['total_failures'] = int(df['count'].iloc[0])
        
        # Total de predicciones realizadas
        query = "SELECT COUNT(*) as count FROM failure_predictions"
        df = pd.read_sql(query, engine)
        stats['total_predictions'] = int(df['count'].iloc[0])
        
        # Total de acciones recomendadas
        query = "SELECT COUNT(*) as count FROM recommendations"
        df = pd.read_sql(query, engine)
        stats['total_actions'] = int(df['count'].iloc[0])
        
        # Anomalías en las últimas 24 horas
        query = "SELECT COUNT(*) as count FROM anomalies WHERE timestamp > NOW() - INTERVAL '24 hours'"
        df = pd.read_sql(query, engine)
        stats['anomalies_last_24h'] = int(df['count'].iloc[0])
        
        # Fallos en las últimas 24 horas
        query = "SELECT COUNT(*) as count FROM failures WHERE timestamp > NOW() - INTERVAL '24 hours'"
        df = pd.read_sql(query, engine)
        stats['failures_last_24h'] = int(df['count'].iloc[0])
        
        # Servicios con anomalías
        query = "SELECT COUNT(DISTINCT service_id) as count FROM anomalies"
        df = pd.read_sql(query, engine)
        stats['services_with_anomalies'] = int(df['count'].iloc[0])
        
        # Servicios con fallos
        query = "SELECT COUNT(DISTINCT service_id) as count FROM failures"
        df = pd.read_sql(query, engine)
        stats['services_with_failures'] = int(df['count'].iloc[0])
        
        # Tasa de éxito de acciones
        query = """
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN success IS TRUE THEN 1 ELSE 0 END) as successful
            FROM recommendations
            WHERE executed IS TRUE
        """
        df = pd.read_sql(query, engine)
        if df['total'].iloc[0] > 0:
            stats['action_success_rate'] = float(df['successful'].iloc[0] / df['total'].iloc[0])
        else:
            stats['action_success_rate'] = 0
        
        return stats
    
    except Exception as e:
        logger.error(f"Error al obtener estadísticas generales: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")

@app.get("/stats/service/{service_id}", tags=["Statistics"])
async def get_service_stats(
    service_id: str,
    days: int = Query(7, ge=1, le=90)
):
    """Obtener estadísticas para un servicio específico"""
    try:
        engine = get_db_engine()
        
        stats = {}
        
        # Verificar si el servicio existe
        query = f"SELECT * FROM services WHERE service_id = '{service_id}'"
        df = pd.read_sql(query, engine)
        
        if df.empty:
            raise HTTPException(status_code=404, detail=f"Servicio {service_id} no encontrado")
        
        # Información básica del servicio
        stats['service_id'] = service_id
        stats['service_name'] = df['service_name'].iloc[0]
        stats['service_type'] = df['service_type'].iloc[0]
        stats['first_seen'] = df['first_seen'].iloc[0].isoformat()
        stats['last_seen'] = df['last_seen'].iloc[0].isoformat()
        
        # Métricas disponibles
        query = f"""
            SELECT DISTINCT metric_name 
            FROM metrics 
            WHERE service_id = '{service_id}'
            ORDER BY metric_name
        """
        df = pd.read_sql(query, engine)
        stats['available_metrics'] = df['metric_name'].tolist()
        
        # Total de anomalías
        query = f"SELECT COUNT(*) as count FROM anomalies WHERE service_id = '{service_id}'"
        df = pd.read_sql(query, engine)
        stats['total_anomalies'] = int(df['count'].iloc[0])
        
        # Total de fallos
        query = f"SELECT COUNT(*) as count FROM failures WHERE service_id = '{service_id}'"
        df = pd.read_sql(query, engine)
        stats['total_failures'] = int(df['count'].iloc[0])
        
        # Anomalías por día (últimos N días)
        query = f"""
            SELECT 
                DATE_TRUNC('day', timestamp) as day,
                COUNT(*) as count
            FROM anomalies
            WHERE 
                service_id = '{service_id}' AND
                timestamp > NOW() - INTERVAL '{days} days'
            GROUP BY day
            ORDER BY day
        """
        df = pd.read_sql(query, engine)
        stats['anomalies_by_day'] = [
            {'day': row['day'].isoformat(), 'count': int(row['count'])}
            for _, row in df.iterrows()
        ]
        
        # Fallos por día (últimos N días)
        query = f"""
            SELECT 
                DATE_TRUNC('day', timestamp) as day,
                COUNT(*) as count
            FROM failures
            WHERE 
                service_id = '{service_id}' AND
                timestamp > NOW() - INTERVAL '{days} days'
            GROUP BY day
            ORDER BY day
        """
        df = pd.read_sql(query, engine)
        stats['failures_by_day'] = [
            {'day': row['day'].isoformat(), 'count': int(row['count'])}
            for _, row in df.iterrows()
        ]
        
        # Tipos de fallos
        query = f"""
            SELECT 
                failure_type,
                COUNT(*) as count
            FROM failures
            WHERE service_id = '{service_id}'
            GROUP BY failure_type
            ORDER BY count DESC
        """
        df = pd.read_sql(query, engine)
        stats['failure_types'] = [
            {'type': row['failure_type'], 'count': int(row['count'])}
            for _, row in df.iterrows()
        ]
        
        # Acciones recomendadas
        query = f"""
            SELECT 
                action_id,
                COUNT(*) as count,
                SUM(CASE WHEN executed IS TRUE THEN 1 ELSE 0 END) as executed,
                SUM(CASE WHEN success IS TRUE THEN 1 ELSE 0 END) as successful
            FROM recommendations
            WHERE service_id = '{service_id}'
            GROUP BY action_id
            ORDER BY count DESC
        """
        df = pd.read_sql(query, engine)
        stats['actions'] = [
            {
                'action_id': row['action_id'], 
                'count': int(row['count']),
                'executed': int(row['executed']),
                'successful': int(row['successful'])
            }
            for _, row in df.iterrows()
        ]
        
        return stats
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error al obtener estadísticas para servicio {service_id}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al obtener estadísticas: {str(e)}")

# Iniciar servidor
if __name__ == "__main__":
    # Esperar a que servicios dependientes estén disponibles
    time.sleep(15)
    
    # Iniciar servidor
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)