# verify-installation.ps1 - Script para verificar instalación en Windows PowerShell

Write-Host "Verificando la instalación del sistema predictivo..."

# Función para verificar archivo
function Check-File {
    param($path)
    if (Test-Path -Path $path -PathType Leaf) {
        Write-Host "✅ $path encontrado"
        return $true
    } else {
        Write-Host "❌ $path no encontrado"
        return $false
    }
}

# Función para verificar directorio
function Check-Directory {
    param($path)
    if (Test-Path -Path $path -PathType Container) {
        Write-Host "✅ $path encontrado"
        return $true
    } else {
        Write-Host "❌ $path no encontrado"
        return $false
    }
}

# Verificar archivos principales
Write-Host "Verificando archivos principales..."
$mainFiles = @("docker-compose.yml", ".env")
$mainOk = $true

foreach ($file in $mainFiles) {
    if (-not (Check-File $file)) {
        $mainOk = $false
    }
}

if ($mainOk) {
    Write-Host "✅ Archivos principales OK"
} else {
    Write-Host "❌ Faltan archivos principales"
}

# Verificar componentes
Write-Host ""
Write-Host "Verificando componentes..."
$components = @("collectors", "preprocessor", "anomaly_detector", "predictive_engine", "action_recommender", "api", "dashboard")
$componentsOk = $true

foreach ($component in $components) {
    if (-not (Check-Directory $component)) {
        $componentsOk = $false
        continue
    }
    
    # Verificar Dockerfile y requirements.txt (excepto dashboard)
    if ($component -ne "dashboard") {
        if (-not (Check-File "$component\Dockerfile")) {
            $componentsOk = $false
        }
        
        if (-not (Check-File "$component\requirements.txt")) {
            $componentsOk = $false
        }
    } else {
        # Verificar archivos específicos del dashboard
        if (-not (Check-File "$component\Dockerfile")) {
            $componentsOk = $false
        }
        
        if (-not (Check-File "$component\package.json")) {
            $componentsOk = $false
        }
        
        if (-not (Check-File "$component\nginx.conf")) {
            $componentsOk = $false
        }
    }
    
    # Verificar archivos de código específicos
    switch ($component) {
        "collectors" {
            Check-File "$component\collector.py" | Out-Null
            $componentsOk = $componentsOk -and $?
            Check-Directory "$component\config" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "preprocessor" {
            Check-File "$component\preprocessor.py" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "anomaly_detector" {
            Check-File "$component\anomaly_detector.py" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "predictive_engine" {
            Check-File "$component\predictive_engine.py" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "action_recommender" {
            Check-File "$component\action_recommender.py" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "api" {
            Check-File "$component\main.py" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
        "dashboard" {
            Check-Directory "$component\src" | Out-Null
            $componentsOk = $componentsOk -and $?
        }
    }
}

if ($componentsOk) {
    Write-Host "✅ Componentes OK"
} else {
    Write-Host "❌ Faltan archivos en algunos componentes"
}

# Verificar configuraciones adicionales
Write-Host ""
Write-Host "Verificando configuraciones adicionales..."
$configsOk = $true

# Verificar Prometheus
if (-not (Check-Directory "prometheus")) {
    $configsOk = $false
} else {
    $configsOk = $configsOk -and (Check-File "prometheus\prometheus.yml")
}

# Verificar Grafana
if (-not (Check-Directory "grafana")) {
    $configsOk = $false
} else {
    $configsOk = $configsOk -and (Check-Directory "grafana\provisioning")
    $configsOk = $configsOk -and (Check-Directory "grafana\provisioning\datasources")
    $configsOk = $configsOk -and (Check-Directory "grafana\provisioning\dashboards")
    $configsOk = $configsOk -and (Check-File "grafana\provisioning\datasources\datasource.yml")
    $configsOk = $configsOk -and (Check-File "grafana\provisioning\dashboards\dashboards.yml")
    $configsOk = $configsOk -and (Check-File "grafana\provisioning\dashboards\system_overview.json")
}

# Verificar inicialización de base de datos
if (-not (Check-Directory "db-init")) {
    $configsOk = $false
} else {
    $configsOk = $configsOk -and (Check-File "db-init\init-timescaledb.sh")
}

if ($configsOk) {
    Write-Host "✅ Configuraciones adicionales OK"
} else {
    Write-Host "❌ Faltan configuraciones adicionales"
}

# Resumen
Write-Host ""
Write-Host "Resumen de la verificación:"
if ($mainOk -and $componentsOk -and $configsOk) {
    Write-Host "✅ Todos los archivos necesarios están presentes"
    Write-Host "El sistema está listo para ser iniciado con: .\run.ps1"
} else {
    Write-Host "❌ Faltan algunos archivos necesarios"
    Write-Host "Por favor, complete la instalación antes de iniciar el sistema"
}