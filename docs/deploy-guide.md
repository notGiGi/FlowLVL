# Guía de Despliegue - Sistema de Mantenimiento Predictivo

Esta guía detalla los pasos para desplegar el sistema de mantenimiento predictivo en un clúster Kubernetes.

## Requisitos previos

- Kubernetes 1.19+
- Helm 3+
- Kubectl configurado para acceder al clúster
- Métricas del servidor Kubernetes instaladas
- Acceso a un registro de contenedores (Docker Hub, GCR, ECR, etc.)

## Arquitectura de despliegue

El sistema se despliega como un conjunto de microservicios en Kubernetes:

```
                                   ┌─────────────────┐
                                   │     Ingress     │
                                   └────────┬────────┘
                                            │
                                            ▼
┌─────────────────┐              ┌────────────────────┐
│  Prometheus &   │◄─────────────┤        API         │
│    Grafana      │              │    (FastAPI)       │
└─────────────────┘              └────────┬───────────┘
                                          │
                                          │
       ┌───────────────────────┬──────────┴───────────┬───────────────────────┐
       │                       │                      │                       │
       ▼                       ▼                      ▼                       ▼
┌─────────────┐        ┌───────────────┐      ┌─────────────┐         ┌─────────────┐
│  Anomaly    │        │  Predictive   │      │   Action    │         │  Service    │
│  Detector   │◄─────► │   Engine      │◄────►│ Recommender │◄────────┤  Profiler   │
└──────┬──────┘        └───────────────┘      └──────┬──────┘         └─────────────┘
       │                                             │
       │                                             │
       ▼                                             ▼
┌─────────────┐                            ┌─────────────────┐
│ TimescaleDB │                            │     Redis       │
└─────────────┘                            └─────────────────┘
```

## Pasos de despliegue

### 1. Configurar variables de entorno

Cree un archivo `.env` con las configuraciones necesarias:

```bash
# General
NAMESPACE=predictive-maintenance
ENV=production

# Docker registry
DOCKER_REGISTRY=your-registry.com/predictive-maintenance

# Database
TIMESCALEDB_PASSWORD=your-secure-password
REDIS_PASSWORD=your-secure-password

# API Security
API_KEY=your-api-key
SECRET_KEY=your-secret-key

# Kubernetes integration
ENABLE_K8S_INTEGRATION=true
```

### 2. Crear namespace

```bash
kubectl create namespace predictive-maintenance
```

### 3. Crear secrets

```bash
# Crear secret para la base de datos
kubectl create secret generic db-credentials \
  --namespace predictive-maintenance \
  --from-literal=timescaledb-password=$TIMESCALEDB_PASSWORD \
  --from-literal=redis-password=$REDIS_PASSWORD

# Crear secret para API
kubectl create secret generic api-credentials \
  --namespace predictive-maintenance \
  --from-literal=api-key=$API_KEY \
  --from-literal=secret-key=$SECRET_KEY
```

### 4. Desplegar infraestructura

```bash
# Aplicar configuraciones de Helm
helm repo add timescale https://charts.timescale.com
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update

# Instalar TimescaleDB
helm install timescaledb timescale/timescaledb-single \
  --namespace predictive-maintenance \
  --set credentials.postgres=$TIMESCALEDB_PASSWORD \
  --set persistence.size=10Gi

# Instalar Redis
helm install redis bitnami/redis \
  --namespace predictive-maintenance \
  --set auth.password=$REDIS_PASSWORD \
  --set persistence.size=5Gi
```

### 5. Desplegar componentes del sistema

```bash
# Aplicar manifiestos de Kubernetes
kubectl apply -f k8s/manifests/ --namespace predictive-maintenance
```

### 6. Verificar despliegue

```bash
# Verificar que los pods estén ejecutándose
kubectl get pods -n predictive-maintenance

# Verificar servicios
kubectl get services -n predictive-maintenance
```

## Configuración post-despliegue

### 1. Configuración de clientes supervisados

Deberá configurar los clientes que desea supervisar. Puede hacerlo a través de la API:

```bash
curl -X POST https://your-api-url/register-service \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "service_id": "example-service",
    "service_name": "Example Service",
    "service_type": "web_service",
    "description": "Example web service"
  }'
```

### 2. Configuración de políticas de acción

Configure las políticas de acción para definir qué acciones correctivas se pueden tomar:

```bash
# Aplique el ConfigMap que contiene las políticas
kubectl apply -f k8s/config/action-policies.yaml -n predictive-maintenance
```

### 3. Configuración de integración con Prometheus

Si está utilizando Prometheus para la recolección de métricas, configure ServiceMonitors:

```bash
kubectl apply -f k8s/monitoring/service-monitors.yaml -n predictive-maintenance
```

## Actualización del sistema

Para actualizar el sistema a una nueva versión:

```bash
# Actualizar imágenes en el registro
./scripts/build_and_push.sh $VERSION

# Actualizar manifiestos con la nueva versión
kubectl set image deployment/api api=$DOCKER_REGISTRY/api:$VERSION -n predictive-maintenance
kubectl set image deployment/anomaly-detector anomaly-detector=$DOCKER_REGISTRY/anomaly-detector:$VERSION -n predictive-maintenance
kubectl set image deployment/predictive-engine predictive-engine=$DOCKER_REGISTRY/predictive-engine:$VERSION -n predictive-maintenance
kubectl set image deployment/action-recommender action-recommender=$DOCKER_REGISTRY/action-recommender:$VERSION -n predictive-maintenance
kubectl set image deployment/service-profiler service-profiler=$DOCKER_REGISTRY/service-profiler:$VERSION -n predictive-maintenance
```

## Escalamiento

### Escalamiento horizontal

Los componentes pueden escalarse horizontalmente según sea necesario:

```bash
kubectl scale deployment api --replicas=3 -n predictive-maintenance
kubectl scale deployment anomaly-detector --replicas=2 -n predictive-maintenance
kubectl scale deployment predictive-engine --replicas=2 -n predictive-maintenance
```

### Escalamiento vertical

Para ajustar los recursos asignados a los componentes:

```bash
kubectl set resources deployment api -c api --limits=cpu=2,memory=2Gi --requests=cpu=500m,memory=1Gi -n predictive-maintenance
```

## Diagnóstico y solución de problemas

### Verificar logs

```bash
# Ver logs de un componente específico
kubectl logs -f deployment/api -n predictive-maintenance
kubectl logs -f deployment/anomaly-detector -n predictive-maintenance
```

### Verificar estado de salud

```bash
# Verificar endpoints de salud
kubectl port-forward service/api 8000:8000 -n predictive-maintenance
curl http://localhost:8000/health
```

### Problemas comunes

1. **Problemas de conexión a la base de datos**:
   - Verificar que TimescaleDB esté ejecutándose: `kubectl get pods -l app=timescaledb -n predictive-maintenance`
   - Verificar secrets: `kubectl describe secret db-credentials -n predictive-maintenance`

2. **API no responde**:
   - Verificar logs: `kubectl logs -f deployment/api -n predictive-maintenance`
   - Verificar recursos: `kubectl describe pod -l app=api -n predictive-maintenance`

3. **No se detectan anomalías**:
   - Verificar que las métricas estén llegando: revisar logs del detector de anomalías
   - Verificar perfiles de servicio: consultar API `/service-status/{service_id}`

## Respaldo y recuperación

### Respaldo de la base de datos

```bash
# Ejecutar backup de TimescaleDB
kubectl exec -it timescaledb-0 -n predictive-maintenance -- pg_dump -U postgres -d predictive > backup_$(date +%Y%m%d).sql
```

### Recuperación

```bash
# Restaurar desde backup
kubectl cp backup_20250101.sql timescaledb-0:/tmp/ -n predictive-maintenance
kubectl exec -it timescaledb-0 -n predictive-maintenance -- psql -U postgres -d predictive -f /tmp/backup_20250101.sql
```

## Monitoreo del sistema

Se recomienda configurar alertas en Prometheus para monitorear:

1. Uso de recursos (CPU/memoria) de cada componente
2. Latencia de la API
3. Tasa de detección de anomalías
4. Precisión de las predicciones

Ejemplos de reglas de alerta:

```yaml
groups:
- name: predictive-maintenance
  rules:
  - alert: HighCPUUsage
    expr: container_cpu_usage_seconds_total{namespace="predictive-maintenance"} > 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "High CPU usage on {{ $labels.pod }}"
      description: "Pod {{ $labels.pod }} has high CPU usage ({{ $value }})"
```

## Consideraciones de seguridad

1. **Acceso a la API**: Asegúrese de que la API solo sea accesible a través de HTTPS y esté protegida por API keys.
2. **RBAC**: Utilice roles y permisos adecuados para limitar el acceso de los componentes a los recursos de Kubernetes.
3. **Secretos**: Nunca almacene contraseñas o claves en archivos de configuración no encriptados.
4. **Acciones automatizadas**: Limite qué acciones pueden ejecutarse automáticamente y en qué servicios.

## Integración con CI/CD

Para integrar el sistema con su pipeline de CI/CD:

1. Añada pruebas automáticas en su pipeline:
   ```yaml
   # Ejemplo para GitHub Actions
   jobs:
     test:
       runs-on: ubuntu-latest
       steps:
       - uses: actions/checkout@v2
       - name: Run tests
         run: |
           docker-compose -f docker-compose.test.yml up --build --exit-code-from tests
   ```

2. Configure la implementación automática:
   ```yaml
   deploy:
     needs: test
     if: github.ref == 'refs/heads/main'
     runs-on: ubuntu-latest
     steps:
     - uses: actions/checkout@v2
     - name: Deploy to Kubernetes
       run: |
         ./scripts/deploy.sh
   ```

## Referencias adicionales

- [Documentación de la API](./api-reference.md)
- [Guía de configuración avanzada](./advanced-configuration.md)
- [Guía de troubleshooting](./troubleshooting-guide.md)