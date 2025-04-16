from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Security, Request
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Union, Any
import os
import logging
from datetime import datetime
import json
import uuid

# Importar componentes del sistema
from anomaly_detector.improved_anomaly_detector import ImprovedAnomalyDetector
from action_recommender.improved_action_recommender import ImprovedActionRecommender
from monitoring.service_profiler import ServiceProfiler
from utils.metrics import MetricsCollector

# Configuración de logging
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger('api')

# Configuración
API_KEYS = os.environ.get("API_KEYS", "test_key").split(",")
api_key_header = APIKeyHeader(name="X-API-Key")

# Modelos de datos para la API
class MetricData(BaseModel):
    service_id: str
    timestamp: Optional[str] = None
    metrics: Dict[str, Union[float, int, str, bool]]
    
class AnomalyDetectionRequest(BaseModel):
    service_id: str
    metrics: Dict[str, Union[float, int, str, bool]]
    timestamp: Optional[str] = None

class ServiceRegistration(BaseModel):
    service_id: str
    service_name: str
    service_type: str
    description: Optional[str] = None
    labels: Optional[Dict[str, str]] = None

class ActionExecutionRequest(BaseModel):
    action_id: str
    service_id: str
    parameters: Optional[Dict[str, Any]] = None
    auth_token: Optional[str] = None

class ServiceStatusResponse(BaseModel):
    service_id: str
    status: str
    health_score: float = 1.0
    anomaly_score: Optional[float] = None
    last_updated: Optional[str] = None
    active_alerts: List[Dict[str, Any]] = Field(default_factory=list)

# Funciones de seguridad
async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key not in API_KEYS:
        raise HTTPException(
            status_code=403,
            detail="API key inválida"
        )
    return api_key

# Función para crear la aplicación FastAPI
def create_app(config=None):
    # Inicializar componentes
    anomaly_detector = ImprovedAnomalyDetector(config=config)
    action_recommender = ImprovedActionRecommender(config=config)
    service_profiler = ServiceProfiler(config=config)
    metrics_collector = MetricsCollector(config=config)
    
    # Crear aplicación FastAPI
    app = FastAPI(
        title="Predictive Maintenance API",
        description="API para sistema de mantenimiento predictivo",
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
    
    # Middleware para logging de solicitudes
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = str(uuid.uuid4())
        logger.info(f"[{request_id}] {request.method} {request.url.path}")
        
        try:
            start_time = datetime.now()
            response = await call_next(request)
            process_time = (datetime.now() - start_time).total_seconds() * 1000
            
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str(process_time)
            
            logger.info(f"[{request_id}] Completado en {process_time:.2f}ms - Status: {response.status_code}")
            return response
        except Exception as e:
            logger.error(f"[{request_id}] Error: {str(e)}")
            return JSONResponse(
                status_code=500,
                content={"message": "Error interno del servidor"}
            )
    
    # Rutas de la API
    @app.get("/health")
    async def health_check():
        """Verifica el estado de salud del API"""
        return {"status": "online", "timestamp": datetime.now().isoformat()}
    
    @app.post("/detect-anomaly")
    async def detect_anomaly(
        request: AnomalyDetectionRequest,
        background_tasks: BackgroundTasks,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Detecta anomalías en las métricas proporcionadas y opcionalmente recomienda acciones
        """
        try:
            if not request.timestamp:
                request.timestamp = datetime.now().isoformat()
            
            # Preparar datos
            data = {
                "service_id": request.service_id,
                "timestamp": request.timestamp,
                **request.metrics
            }
            
            # Detectar anomalías
            is_anomaly, anomaly_score, details = anomaly_detector.detect_anomalies(data)
            
            # Si hay anomalía, recomendar acción en segundo plano
            if is_anomaly:
                background_tasks.add_task(
                    process_anomaly_recommendation,
                    anomaly_data={
                        "service_id": request.service_id,
                        "anomaly_score": anomaly_score,
                        "details": details
                    },
                    action_recommender=action_recommender
                )
            
            return {
                "service_id": request.service_id,
                "timestamp": request.timestamp,
                "is_anomaly": is_anomaly,
                "anomaly_score": anomaly_score,
                "details": details
            }
            
        except Exception as e:
            logger.error(f"Error al detectar anomalía: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al procesar la solicitud: {str(e)}"
            )
    
    @app.post("/register-service")
    async def register_service(
        service: ServiceRegistration,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Registra un nuevo servicio para monitoreo
        """
        try:
            # En una implementación real, guardaríamos esto en base de datos
            # Para esta demo, simplemente devolvemos el servicio registrado
            return {
                "status": "success",
                "service": {
                    "service_id": service.service_id,
                    "service_name": service.service_name,
                    "service_type": service.service_type,
                    "registered_at": datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Error al registrar servicio: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al registrar servicio: {str(e)}"
            )
    
    @app.post("/submit-metrics")
    async def submit_metrics(
        metric_data: MetricData,
        background_tasks: BackgroundTasks,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Envía métricas para un servicio y opcionalmente detecta anomalías
        """
        try:
            if not metric_data.timestamp:
                metric_data.timestamp = datetime.now().isoformat()
            
            # Preparar datos
            data = {
                "service_id": metric_data.service_id,
                "timestamp": metric_data.timestamp,
                **metric_data.metrics
            }
            
            # Añadir datos al perfilador en segundo plano
            background_tasks.add_task(
                service_profiler.add_metrics_data,
                metric_data.service_id,
                metric_data.metrics,
                metric_data.timestamp
            )
            
            # Detectar anomalías en segundo plano
            background_tasks.add_task(
                process_background_detection,
                data=data,
                anomaly_detector=anomaly_detector,
                action_recommender=action_recommender
            )
            
            return {
                "status": "success",
                "message": "Métricas recibidas y procesamiento iniciado",
                "timestamp": metric_data.timestamp
            }
            
        except Exception as e:
            logger.error(f"Error al enviar métricas: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al procesar métricas: {str(e)}"
            )
    
    @app.get("/service-status/{service_id}")
    async def get_service_status(
        service_id: str,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Obtiene el estado actual de un servicio
        """
        try:
            # Obtener estado desde el detector de anomalías
            status = anomaly_detector.get_service_status(service_id)
            
            # Obtener perfil del servicio
            profile = service_profiler.get_service_profile(service_id)
            
            # Formatear respuesta
            response = ServiceStatusResponse(
                service_id=service_id,
                status=status.get("status", "unknown"),
                anomaly_score=status.get("anomaly_score"),
                last_updated=status.get("last_updated"),
                health_score=1.0 - (status.get("anomaly_score", 0) / 2),  # Convertir anomaly_score a health_score
                active_alerts=[]  # En una implementación real, obtendríamos alertas activas
            )
            
            # Añadir información del perfil si está disponible
            if profile:
                response_dict = response.dict()
                response_dict["profile"] = {
                    "last_updated": profile.get("last_updated"),
                    "metrics_available": profile.get("metrics", []),
                    "has_model": "model_path" in profile
                }
                return response_dict
            
            return response
            
        except Exception as e:
            logger.error(f"Error al obtener estado del servicio: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener estado: {str(e)}"
            )
    
    @app.post("/recommend-action")
    async def recommend_action(
        data: Dict[str, Any],
        api_key: str = Depends(verify_api_key)
    ):
        """
        Recomienda una acción basada en métricas o anomalía
        """
        try:
            # Determinar tipo de entrada
            if "anomaly_score" in data:
                recommendation = action_recommender.process_and_recommend(anomaly_data=data)
            elif "probability" in data:
                recommendation = action_recommender.process_and_recommend(prediction_data=data)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Datos no válidos para recomendación"
                )
            
            return recommendation
            
        except Exception as e:
            logger.error(f"Error al recomendar acción: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al recomendar acción: {str(e)}"
            )
    
    @app.post("/execute-action")
    async def execute_action(
        request: ActionExecutionRequest,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Ejecuta una acción correctiva
        """
        try:
            # Buscar acción en políticas
            service_id = request.service_id
            action_id = request.action_id
            
            if service_id not in action_recommender.action_policies:
                raise HTTPException(
                    status_code=404,
                    detail=f"Servicio {service_id} no encontrado"
                )
            
            service_policy = action_recommender.action_policies[service_id]
            if action_id not in service_policy.get("actions", {}):
                raise HTTPException(
                    status_code=404,
                    detail=f"Acción {action_id} no encontrada para servicio {service_id}"
                )
            
            # Obtener definición de acción
            action = service_policy["actions"][action_id].copy()
            action["action_id"] = action_id
            action["service_id"] = service_id
            
            # Añadir parámetros personalizados si se proporcionan
            if request.parameters:
                if "parameters" not in action:
                    action["parameters"] = {}
                action["parameters"].update(request.parameters)
            
            # Ejecutar acción
            success = action_recommender.execute_action(
                action=action,
                metrics={},  # En una implementación real, obtendríamos métricas actuales
                auth_token=request.auth_token
            )
            
            return {
                "status": "success" if success else "error",
                "message": "Acción encolada para ejecución" if success else "Error al ejecutar acción",
                "action_id": action_id,
                "service_id": service_id,
                "timestamp": datetime.now().isoformat()
            }
            
        except HTTPException as he:
            raise he
        except Exception as e:
            logger.error(f"Error al ejecutar acción: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al ejecutar acción: {str(e)}"
            )
    
    @app.get("/action-history/{service_id}")
    async def get_action_history(
        service_id: str,
        limit: int = 10,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Obtiene historial de acciones para un servicio
        """
        try:
            # Obtener historial desde el orquestador
            history = action_recommender.orchestrator.get_action_history(service_id, limit)
            
            return {
                "service_id": service_id,
                "count": len(history),
                "actions": history
            }
            
        except Exception as e:
            logger.error(f"Error al obtener historial: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener historial: {str(e)}"
            )
    
    @app.get("/service-recommendations/{service_id}")
    async def get_service_recommendations(
        service_id: str,
        api_key: str = Depends(verify_api_key)
    ):
        """
        Obtiene recomendaciones de umbral para un servicio
        """
        try:
            # Obtener recomendaciones desde el perfilador
            recommendations = service_profiler.get_threshold_recommendations(service_id)
            
            return {
                "service_id": service_id,
                "recommendations": recommendations,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error al obtener recomendaciones: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error al obtener recomendaciones: {str(e)}"
            )
    
    return app

# Funciones auxiliares para tareas en segundo plano
async def process_background_detection(data, anomaly_detector, action_recommender):
    """Procesa detección de anomalías en segundo plano"""
    try:
        # Detectar anomalías
        is_anomaly, anomaly_score, details = anomaly_detector.detect_anomalies(data)
        
        # Si hay anomalía, recomendar acción
        if is_anomaly:
            await process_anomaly_recommendation(
                anomaly_data={
                    "service_id": data["service_id"],
                    "anomaly_score": anomaly_score,
                    "details": details
                },
                action_recommender=action_recommender
            )
    except Exception as e:
        logger.error(f"Error en detección en segundo plano: {str(e)}")

async def process_anomaly_recommendation(anomaly_data, action_recommender):
    """Procesa recomendación de acción en segundo plano"""
    try:
        # Recomendar acción
        recommendation = action_recommender.process_and_recommend(anomaly_data=anomaly_data)
        
        # En una implementación real, podríamos enviar notificaciones,
        # almacenar en base de datos, etc.
        logger.info(f"Recomendación generada para {anomaly_data['service_id']}: "
                  f"{recommendation.get('recommended_action', {}).get('action_id', 'ninguna')}")
    except Exception as e:
        logger.error(f"Error en recomendación en segundo plano: {str(e)}")

# Punto de entrada para aplicación
def create_api_app(config=None):
    """Crea y devuelve la aplicación API"""
    return create_app(config)

# Para ejecutar en modo desarrollo
if __name__ == "__main__":
    import uvicorn
    
    # Configuración básica para desarrollo
    config = {
        "config_dir": "./config",
        "models_dir": "./models",
        "data_dir": "./data"
    }
    
    # Crear aplicación
    app = create_api_app(config)
    
    # Ejecutar servidor
    uvicorn.run(app, host="0.0.0.0", port=8000)