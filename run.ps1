# run.ps1 - Script para ejecutar el sistema en Windows PowerShell

# Función para mostrar mensajes
function Log {
    param($message)
    Write-Host "`e[1;34m[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]`e[0m $message"
}

# Función para verificar requisitos
function Check-Requirements {
    Log "Verificando requisitos..."
    
    # Verificar Docker
    try {
        $dockerVersion = docker --version
        Log "Docker detectado: $dockerVersion"
    } catch {
        Log "`e[1;31mError: Docker no está instalado o no se encuentra en el PATH.`e[0m"
        Log "Por favor, instale Docker Desktop para Windows antes de continuar."
        exit 1
    }
    
    # Verificar Docker Compose
    try {
        $composeVersion = docker-compose --version
        Log "Docker Compose detectado: $composeVersion"
    } catch {
        Log "`e[1;31mError: Docker Compose no está instalado o no se encuentra en el PATH.`e[0m"
        Log "Docker Compose generalmente viene incluido con Docker Desktop para Windows."
        exit 1
    }
    
    # Verificar espacio libre
    $disk = Get-CimInstance -ClassName Win32_LogicalDisk -Filter "DeviceID='C:'"
    $freeSpaceGB = [math]::Round($disk.FreeSpace / 1GB, 2)
    Log "Espacio libre en disco C: $freeSpaceGB GB"
    
    # Verificar memoria total
    $computerSystem = Get-CimInstance -ClassName Win32_ComputerSystem
    $totalMemoryGB = [math]::Round($computerSystem.TotalPhysicalMemory / 1GB, 2)
    Log "Memoria total: $totalMemoryGB GB"
    
    Log "Requisitos verificados correctamente."
}

# Función para verificar y crear directorios
function Check-Directories {
    Log "Verificando y creando directorios..."
    
    # Comprobar si estamos en el directorio correcto (con docker-compose.yml)
    if (-not (Test-Path "docker-compose.yml")) {
        Log "`e[1;31mError: No se encontró el archivo docker-compose.yml en el directorio actual.`e[0m"
        Log "Asegúrese de ejecutar este script desde el directorio raíz del proyecto."
        exit 1
    }
    
    # Crear directorio para modelos si no existe
    if (-not (Test-Path "models")) {
        Log "Creando directorio para modelos..."
        New-Item -Path "models" -ItemType Directory | Out-Null
    }
    
    # Crear directorios para componentes si no existen
    $components = @(
        "collectors/config", 
        "preprocessor", 
        "anomaly_detector", 
        "predictive_engine", 
        "action_recommender", 
        "api", 
        "dashboard", 
        "prometheus", 
        "grafana/provisioning/datasources", 
        "grafana/provisioning/dashboards", 
        "db-init"
    )
    
    foreach ($dir in $components) {
        if (-not (Test-Path $dir)) {
            Log "Creando directorio: $dir"
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
        }
    }
    
    Log "Directorios verificados correctamente."
}

# Función para configurar archivos iniciales
function Setup-InitialConfigs {
    Log "Configurando archivos iniciales..."
    
    # Comprobar si existe el archivo .env
    if (-not (Test-Path ".env")) {
        if (Test-Path ".env.example") {
            Log "Creando archivo .env a partir de .env.example..."
            Copy-Item ".env.example" ".env"
            Log "`e[1;33mAtención: Se ha creado un archivo .env con valores predeterminados.`e[0m"
            Log "`e[1;33mSe recomienda revisar y ajustar las variables de entorno en el archivo .env antes de continuar.`e[0m"
        } else {
            Log "`e[1;31mError: No se encontró el archivo .env.example.`e[0m"
            exit 1
        }
    }
    
    # Comprobar si existe la configuración de Prometheus
    if (-not (Test-Path "prometheus/prometheus.yml")) {
        Log "`e[1;31mError: No se encontró el archivo prometheus.yml.`e[0m"
        Log "Por favor, asegúrese de que exista el archivo prometheus/prometheus.yml antes de continuar."
        exit 1
    }
    
    Log "Archivos iniciales configurados correctamente."
}

# Función para iniciar los servicios
function Start-Services {
    Log "Iniciando servicios..."
    
    # Construir las imágenes Docker
    Log "Construyendo imágenes Docker..."
    docker-compose build
    
    # Iniciar servicios
    Log "Iniciando contenedores..."
    docker-compose up -d
    
    # Esperar a que los servicios estén disponibles
    Log "Esperando a que los servicios estén disponibles..."
    Start-Sleep -Seconds 30
    
    # Verificar el estado de los servicios
    Log "Verificando el estado de los servicios..."
    docker-compose ps
    
    Log "`e[1;32mServicios iniciados correctamente.`e[0m"
}

# Función para verificar el acceso a los servicios
function Check-Services {
    Log "Verificando acceso a los servicios..."
    
    # Verificar API
    Log "Verificando API REST..."
    try {
        $response = Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get -TimeoutSec 5
        Log "`e[1;32mAPI REST accesible: http://localhost:8000`e[0m"
    } catch {
        Log "`e[1;33mADVERTENCIA: API REST no responde correctamente`e[0m"
    }
    
    # Mostrar enlaces a las interfaces
    Log "`e[1;32mEnlaces a las interfaces:`e[0m"
    Log "  - Dashboard Web: `e[1;36mhttp://localhost:3001`e[0m"
    Log "  - API REST: `e[1;36mhttp://localhost:8000`e[0m"
    Log "  - Documentación de la API: `e[1;36mhttp://localhost:8000/docs`e[0m"
    Log "  - Grafana: `e[1;36mhttp://localhost:3000`e[0m (usuario: admin, contraseña: admin)"
    Log "  - Prometheus: `e[1;36mhttp://localhost:9090`e[0m"
}

# Función principal
function Main {
    Log "`e[1;32m============================================`e[0m"
    Log "`e[1;32m  Sistema Predictivo de Mantenimiento       `e[0m"
    Log "`e[1;32m============================================`e[0m"
    
    # Verificar requisitos
    Check-Requirements
    
    # Verificar y crear directorios
    Check-Directories
    
    # Configurar archivos iniciales
    Setup-InitialConfigs
    
    # Preguntar al usuario si desea continuar
    $confirmacion = Read-Host "¿Desea iniciar los servicios ahora? (s/n)"
    if ($confirmacion -ne "s") {
        Log "Operación cancelada por el usuario."
        exit 0
    }
    
    # Iniciar servicios
    Start-Services
    
    # Verificar servicios
    Check-Services
    
    Log "`e[1;32m============================================`e[0m"
    Log "`e[1;32m  Sistema iniciado correctamente            `e[0m"
    Log "`e[1;32m============================================`e[0m"
}

# Ejecutar función principal
Main