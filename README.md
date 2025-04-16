# Sistema Avanzado de Mantenimiento Predictivo para Sistemas Distribuidos

Este proyecto implementa una plataforma de IA para la predicción, detección y mitigación proactiva de fallos en sistemas distribuidos, utilizando técnicas avanzadas de machine learning y análisis de datos en tiempo real.

## Características Principales

- **Detección Adaptativa de Anomalías**: Algoritmo de detección basado en perfiles dinámicos de servicio que se adaptan automáticamente al comportamiento normal específico de cada sistema.
- **Predicción de Fallos**: Anticipa posibles problemas antes de que ocurran utilizando modelos LSTM, Gradient Boosting y técnicas de aprendizaje profundo.
- **Recomendación Inteligente de Acciones**: Sistema de recomendación basado en políticas que aprende de la efectividad histórica de las acciones.
- **Ejecución Segura de Acciones**: Orquestador de acciones con sistema de seguridad, validación y rollback automático.
- **Monitoreo Centralizado**: Dashboard integrado para visualización y gestión del sistema distribuido.
- **Sistema de Notificaciones**: Alertas y notificaciones configurables por múltiples canales (email, Slack, webhooks).
- **Arquitectura Escalable**: Diseño basado en microservicios con Docker y Kubernetes para fácil despliegue y escalabilidad.
- **Integración con Kubernetes**: Integración nativa para monitorear y ejecutar acciones correctivas en clusters de Kubernetes.

## Arquitectura del Sistema

![Arquitectura del Sistema](./docs/images/arquitectura.png)

### Componentes Principales

1. **Detector de Anomalías (anomaly_detector)**: Motor adaptativo de detección que utiliza perfiles específicos por servicio.
2. **Motor Predictivo (predictive_engine)**: Sistema de predicción de fallos basado en modelos de series temporales.
3. **Recomendador de Acciones (action_recommender)**: Recomienda acciones basadas en el contexto y aprendizaje continuo.
4. **Orquestador de Acciones (action_orchestrator)**: Ejecuta acciones correctivas de forma segura y controlada.
5. **Perfilador de Servicios (service_profiler)**: Aprende el comportamiento normal de cada servicio.
6. **API REST**: Proporciona interfaces para la integración con otros sistemas.
7. **Dashboard**: Interfaz web para monitorear y controlar el sistema.
8. **Servicio de Notificaciones**: Sistema de alertas por múltiples canales.

## Inicio Rápido con Docker Compose

La forma más sencilla de probar el sistema es utilizando Docker Compose:

```bash
# Clonar el repositorio
git clone https://github.com/your-user/predictive-maintenance.git
cd predictive-maintenance

# Configurar variables de entorno
cp .env.example .env
# Editar .env según sea necesario

# Iniciar los servicios
docker-compose up -d

# Verificar que todos los servicios estén en funcionamiento
docker-compose ps
```

### Acceso a las Interfaces

- **Dashboard Web**: http://localhost:3001
- **API REST**: http://localhost:8000
- **Documentación de la API**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000 (usuario: admin, contraseña: admin)
- **Prometheus**: http://localhost:9090

## Guía de Instalación en Kubernetes

Para despliegues en producción, se recomienda utilizar Kubernetes. Consulte nuestra [Guía de Despliegue](./docs/deployment-guide.md) para obtener instrucciones detalladas.

## Configuración

### Configuración de Servicios para Monitoreo

Para registrar un nuevo servicio a monitorear:

```bash
curl -X POST http://localhost:8000/register-service \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "my-web-service",
    "service_name": "My Web Service",
    "service_type": "web_service",
    "description": "Aplicación web principal"
  }'
```

### Configuración de Políticas de Acción

Las políticas de acción definen qué acciones se pueden tomar para resolver diferentes tipos de problemas:

1. Edite el archivo `config/action_policies.json`
2. Reinicie el servicio de recomendación de acciones: `docker-compose restart action-recommender`

Ejemplo de política:

```json
{
  "my-web-service": {
    "description": "Acciones para mi servicio web",
    "actions": {
      "scale_up": {
        "description": "Escala horizontalmente el servicio",
        "command": "kubectl scale deployment ${service_id} --replicas=$(kubectl get deployment ${service_id} -o=jsonpath='{.spec.replicas}'+1)",
        "conditions": {
          "metrics": {
            "cpu_usage": "> 80",
            "response_time_ms": "> 500"
          },
          "anomaly_score": "> 0.6"
        },
        "priority": "medium"
      }
    }
  }
}
```

## Envío de Métricas

### Usando la API REST

```bash
curl -X POST http://localhost:8000/submit-metrics \
  -H "X-API-Key: test_key" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "my-web-service",
    "metrics": {
      "cpu_usage": 82.5,
      "memory_usage": 65.3,
      "response_time_ms": 350,
      "error_rate": 0.2
    }
  }'
```

### Integración con Prometheus

El sistema puede configurarse para extraer métricas directamente de Prometheus. Consulte la [Guía de Integración con Prometheus](./docs/prometheus-integration.md).

## Desarrollo

### Requisitos para Desarrollo

- Python 3.9+
- Node.js 16+
- Docker y Docker Compose
- Kubernetes (opcional, para pruebas de integración completas)

### Configuración del Entorno de Desarrollo

```bash
# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# Instalar dependencias
pip install -r requirements-dev.txt

# Configurar pre-commit hooks
pre-commit install

# Iniciar servicios de desarrollo
docker-compose -f docker-compose.dev.yml up -d
```

### Ejecución de Pruebas

```bash
# Ejecutar todas las pruebas
pytest

# Ejecutar pruebas específicas
pytest tests/unit
pytest tests/integration_test_scenarios.py

# Ejecutar pruebas con cobertura
pytest --cov=.
```

## Casos de Uso

El sistema está diseñado para abordar diversos escenarios:

1. **Fugas de Memoria**: Detección temprana y reinicio automático de servicios.
2. **Sobrecarga de BD**: Ajuste automático de parámetros de conexión y recursos.
3. **Fragmentación de Memoria en Redis**: Purga automática cuando es necesario.
4. **Alta Latencia**: Escalado automático o reinicio de componentes lentos.
5. **Problemas de Disco**: Limpieza automática y generación de alertas.

## Documentación Adicional

- [Arquitectura Detallada](./docs/architecture.md)
- [API Reference](./docs/api-reference.md)
- [Guía de Configuración Avanzada](./docs/advanced-configuration.md)
- [Desarrollo de Nuevos Detectores](./docs/custom-detectors.md)
- [Integración con Sistemas Externos](./docs/integrations.md)

## Contribuir

Las contribuciones son bienvenidas. Por favor, lea [CONTRIBUTING.md](./CONTRIBUTING.md) para obtener detalles sobre nuestro código de conducta y el proceso para enviarnos pull requests.

## Licencia

Este proyecto está licenciado bajo la licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## Contacto

Si tiene preguntas o comentarios, por favor abra un issue en GitHub o contacte a los mantenedores del proyecto.