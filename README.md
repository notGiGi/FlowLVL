# Sistema Predictivo de Mantenimiento para Sistemas Distribuidos

Este proyecto implementa un sistema avanzado de IA para la predicción, detección y mitigación proactiva de fallos en sistemas distribuidos, utilizando técnicas de machine learning y análisis de datos en tiempo real.

## Características Principales

- **Detección de Anomalías en Tiempo Real**: Identificación de comportamientos anormales mediante algoritmos de machine learning.
- **Predicción de Fallos**: Anticipa posibles fallos antes de que ocurran usando modelos LSTM y técnicas de aprendizaje profundo.
- **Recomendación de Acciones**: Sugiere o ejecuta automáticamente acciones correctivas para resolver problemas.
- **Monitoreo Centralizado**: Dashboard integrado para visualización y gestión del sistema distribuido.
- **Arquitectura Escalable**: Basada en microservicios con Docker para fácil despliegue y escalabilidad.

## Arquitectura del Sistema

![Arquitectura del Sistema](./docs/images/arquitectura.png)

El sistema está compuesto por los siguientes componentes principales:

1. **Recolector de datos**: Captura métricas, logs y eventos del sistema distribuido.
2. **Preprocesador de datos**: Limpia, normaliza y prepara los datos para el análisis.
3. **Detector de anomalías**: Identifica comportamientos inusuales en tiempo real.
4. **Motor predictivo**: Predice posibles fallos futuros basados en patrones históricos.
5. **Recomendador de acciones**: Sugiere o ejecuta automáticamente acciones correctivas.
6. **API REST**: Proporciona interfaces para la integración con otros sistemas.
7. **Dashboard de visualización**: Interfaz para monitorear y controlar el sistema.

## Requisitos

- Docker y Docker Compose
- Al menos 4GB de RAM disponible
- Al menos 20GB de espacio en disco
- Conexión a internet para la descarga de imágenes Docker

## Instalación y Despliegue

### Opción 1: Instalación Automática

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/predictive-maintenance.git
cd predictive-maintenance

# Ejecutar script de instalación
chmod +x setup.sh
./setup.sh
```

### Opción 2: Instalación Manual

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/tu-usuario/predictive-maintenance.git
   cd predictive-maintenance
   ```

2. **Configurar variables de entorno**:
   ```bash
   cp .env.example .env
   # Editar el archivo .env según tus necesidades
   ```

3. **Iniciar los servicios**:
   ```bash
   docker-compose up -d
   ```

4. **Verificar el estado**:
   ```bash
   docker-compose ps
   ```

## Acceso a Interfaces

- **Dashboard Web**: http://localhost:3001
- **API REST**: http://localhost:8000
- **Documentación de la API**: http://localhost:8000/docs
- **Grafana**: http://localhost:3000 (usuario: admin, contraseña: admin)
- **Prometheus**: http://localhost:9090

## Descripción de Componentes

### Recolector de Datos

El recolector de datos obtiene información de diversas fuentes:

- **Métricas de sistemas**: CPU, memoria, disco, red
- **Logs de aplicaciones**: Errores, advertencias, información
- **Eventos del sistema**: Inicios, paradas, cambios de configuración
- **Métricas de aplicaciones**: Latencia, throughput, tasa de errores

El componente soporta múltiples formas de recolección:

- Scraping de endpoints Prometheus
- Lectura de logs del sistema
- API REST para envío manual de métricas
- Integración con sistemas de monitoreo existentes

### Preprocesador de Datos

El preprocesador realiza las siguientes tareas:

- Limpieza de datos (eliminación de valores nulos, outliers)
- Normalización y estandarización
- Agregación de métricas
- Extracción de características
- Almacenamiento en TimescaleDB

### Detector de Anomalías

El detector de anomalías utiliza múltiples algoritmos:

- **Isolation Forest**: Detecta outliers y puntos aislados
- **Autoencoders**: Aprende patrones normales y detecta desviaciones
- **Statistical Process Control**: Monitorea variaciones estadísticas

El modelo combina las salidas de estos algoritmos para lograr mayor precisión y robustez.

### Motor Predictivo

El motor predictivo implementa modelos de aprendizaje profundo:

- **LSTM (Long Short-Term Memory)**: Captura dependencias temporales en secuencias de métricas
- **Gradient Boosting**: Clasifica patrones que preceden a fallos
- **Ensemble Methods**: Combina predicciones de múltiples modelos

El sistema mantiene modelos específicos por servicio y por tipo de fallo, que se reentrenan periódicamente.

### Recomendador de Acciones

Este componente:

- Mantiene un catálogo de acciones posibles por tipo de problema
- Evalúa la efectividad histórica de las acciones
- Utiliza algoritmos de reinforcement learning para mejorar recomendaciones
- Puede ejecutar acciones automáticamente según la configuración

## Guías de Uso

### Añadir un Nuevo Servicio para Monitoreo

1. Registrar el servicio a través de la API:
   ```bash
   curl -X POST http://localhost:8000/services \
     -H "Content-Type: application/json" \
     -d '{"service_id": "nuevo_servicio", "service_name": "Nuevo Servicio", "service_type": "web_app"}'
   ```

2. Configurar la recolección de métricas según el tipo de servicio.

3. Verificar en el dashboard que el servicio aparece y se están recolectando métricas.

### Configurar Políticas de Acciones

1. Navegar a la sección de "Acciones" en el dashboard.
2. Crear una nueva política para el servicio deseado.
3. Definir condiciones y acciones de remediación.
4. Guardar la política.

### Analizar Predicciones de Fallos

1. Acceder a la sección "Predicciones" del dashboard.
2. Filtrar por servicio si es necesario.
3. Revisar probabilidades y horizontes de tiempo.
4. Ver recomendaciones de acciones asociadas.

## Mantenimiento del Sistema

### Backup y Restauración

```bash
# Realizar copia de seguridad
./backup.sh

# Restaurar desde copia de seguridad
./restore.sh ./backups/backup_20250215_123045.tar.gz
```

### Verificación del Estado

```bash
./check_system.sh
```

### Actualización del Sistema

```bash
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

## Personalización y Extensión

El sistema es altamente personalizable:

- **Algoritmos de detección**: Modifica los modelos en `/anomaly_detector`
- **Modelos predictivos**: Ajusta los parámetros en `/predictive_engine`
- **Políticas de acción**: Edita los archivos YAML en `/action_recommender/policies`
- **Dashboard**: Personaliza la interfaz en `/dashboard`

## Tecnologías Utilizadas

- **Backend**: Python, FastAPI, Kafka, TimescaleDB
- **Machine Learning**: TensorFlow, PyTorch, scikit-learn
- **Frontend**: React, Recharts, Tailwind CSS
- **Monitoreo**: Prometheus, Grafana
- **Orquestación**: Docker, Docker Compose

## Solución de Problemas

### Problemas Comunes

1. **Los contenedores no inician correctamente**:
   - Verificar logs: `docker-compose logs [servicio]`
   - Asegurar que los puertos no estén en uso por otras aplicaciones
   - Verificar la conectividad entre contenedores

2. **No se recogen métricas**:
   - Verificar la configuración del recolector
   - Comprobar conexión a las fuentes de datos
   - Revisar logs del recolector

3. **Modelos no detectan anomalías**:
   - Verificar que hay suficientes datos de entrenamiento
   - Ajustar umbral de detección en la configuración
   - Reentrenar modelos manualmente

### Obteniendo Ayuda

- Crear un issue en el repositorio de GitHub
- Consultar la documentación completa en `/docs`
- Contactar al equipo de soporte

## Contribuir al Proyecto

1. Fork del repositorio
2. Crear una rama para tu característica (`git checkout -b feature/amazing-feature`)
3. Commit de tus cambios (`git commit -m 'Add some amazing feature'`)
4. Push a la rama (`git push origin feature/amazing-feature`)
5. Abrir un Pull Request

## Licencia

Este proyecto está licenciado bajo la licencia MIT - ver el archivo [LICENSE](LICENSE) para más detalles.

## Autores

- Tu Nombre - Trabajo Inicial - [tu-usuario](https://github.com/tu-usuario)

## Agradecimientos

- Menciona a cualquier persona que haya contribuido al proyecto
- Inspiraciones, recursos utilizados, etc.