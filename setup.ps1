# Script simplificado de configuración para el Sistema de Mantenimiento Predictivo

# Banner
Write-Host "=========================================================="
Write-Host "    Sistema de Mantenimiento Predictivo - Instalación     "
Write-Host "=========================================================="
Write-Host ""

# Verificar Docker
Write-Host "Verificando Docker..."
try {
    docker --version
    Write-Host "Docker instalado correctamente."
}
catch {
    Write-Host "Error: Docker no está instalado o no está en ejecución."
    Write-Host "Por favor, instale Docker Desktop para Windows y asegúrese de que esté en ejecución."
    exit 1
}

# Verificar Docker Compose
Write-Host "Verificando Docker Compose..."
try {
    docker-compose --version
    Write-Host "Docker Compose instalado correctamente."
}
catch {
    Write-Host "Error: Docker Compose no está disponible."
    Write-Host "Asegúrese de que Docker Desktop esté correctamente instalado."
    exit 1
}

# Crear directorios
Write-Host "Creando estructura de directorios..."
$directories = @(
    "config\grafana",
    "config\prometheus",
    "data\profiles",
    "data\timeseries",
    "models\anomaly",
    "models\predictive",
    "models\profiles",
    "models\recommender",
    "logs"
)

foreach ($dir in $directories) {
    if (!(Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        Write-Host "Creado directorio: $dir"
    }
}

# Configurar .env
Write-Host "Configurando archivo .env..."
if (!(Test-Path '.env.example')) {
    Write-Host "Error: No se encuentra el archivo .env.example"
    exit 1
}

if (!(Test-Path '.env')) {
    Copy-Item '.env.example' '.env'
    Write-Host "Archivo .env creado desde ejemplo."
    
    # Generar claves
    $apiKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object { [char]$_ })
    $secretKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 64 | ForEach-Object { [char]$_ })
    
    # Añadir claves al archivo .env
    Add-Content '.env' "API_KEYS=$apiKey"
    Add-Content '.env' "SECRET_KEY=$secretKey"
    
    Write-Host "Claves generadas y añadidas al archivo .env"
}
else {
    Write-Host "Archivo .env ya existe, se conserva."
}

# Crear archivo de configuración de Prometheus
$prometheusConfigPath = "config\prometheus\prometheus.yml"
Write-Host "Creando configuración de Prometheus..."

# Contenido simplificado de prometheus.yml
$prometheusConfig = @"
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
    - targets: ['localhost:9090']

  - job_name: 'pushgateway'
    honor_labels: true
    static_configs:
    - targets: ['pushgateway:9091']

  - job_name: 'predictive-services'
    metrics_path: /metrics
    scrape_interval: 10s
    static_configs:
    - targets: ['api:8000', 'anomaly-detector:8080', 'predictive-engine:8080', 'action-recommender:8080', 'service-profiler:8080']
"@

# Crear directorio si no existe
$prometheusDir = Split-Path -Path $prometheusConfigPath -Parent
if (!(Test-Path $prometheusDir)) {
    New-Item -ItemType Directory -Path $prometheusDir -Force | Out-Null
}

# Escribir configuración
Set-Content -Path $prometheusConfigPath -Value $prometheusConfig
Write-Host "Configuración de Prometheus creada."

# Preguntar si iniciar servicios
$startServices = Read-Host "¿Desea iniciar los servicios ahora? (s/n)"

if ($startServices -eq 's' -or $startServices -eq 'S' -or $startServices -eq 'y' -or $startServices -eq 'Y') {
    Write-Host "Iniciando servicios..."
    
    # Comprobar si hay contenedores antiguos
    $existingContainers = docker ps -a | Select-String -Pattern 'predictive-maintenance'
    if ($existingContainers) {
        $removeContainers = Read-Host "Se han detectado contenedores previos. ¿Desea eliminarlos? (s/n)"
        
        if ($removeContainers -eq 's' -or $removeContainers -eq 'S' -or $removeContainers -eq 'y' -or $removeContainers -eq 'Y') {
            docker-compose down -v
            Write-Host "Contenedores antiguos eliminados."
        }
    }
    
    # Iniciar servicios
    docker-compose up -d
    
    Write-Host "Servicios iniciados. Acceda a las siguientes URLs:"
    Write-Host "- Dashboard: http://localhost:3001"
    Write-Host "- API: http://localhost:8000"
    Write-Host "- Documentación API: http://localhost:8000/docs"
    Write-Host "- Grafana: http://localhost:3000 (usuario: admin, contraseña: admin)"
    Write-Host "- Prometheus: http://localhost:9090"
}
else {
    Write-Host "Configuración completada. Para iniciar los servicios ejecute: docker-compose up -d"
}

Write-Host ""
Write-Host "¡Configuración completada!"