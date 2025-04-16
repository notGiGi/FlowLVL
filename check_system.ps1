# Script para verificar el estado del sistema de mantenimiento predictivo
# Ejecutar en PowerShell para diagnosticar el estado de los servicios

# Colores para mensajes
$Green = 'Green'
$Blue = 'Cyan'
$Yellow = 'Yellow'
$Red = 'Red'

# Banner
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host "    Sistema de Mantenimiento Predictivo - Diagnóstico     " -ForegroundColor $Blue
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host ""

# Verificar que Docker está en ejecución
Write-Host "Verificando Docker..." -ForegroundColor $Yellow
try {
    $dockerStatus = docker info 2>$null
    if ($dockerStatus) {
        Write-Host "✓ Docker está en ejecución" -ForegroundColor $Green
    }
}
catch {
    Write-Host "✗ Docker no está en ejecución. Por favor, inicie Docker Desktop." -ForegroundColor $Red
    exit 1
}

# Verificar servicios en ejecución
Write-Host "Verificando servicios..." -ForegroundColor $Yellow
try {
    $services = docker-compose ps --services
    $runningCount = 0
    $totalCount = 0
    
    foreach ($service in $services) {
        $totalCount++
        $serviceStatus = docker-compose ps $service | Select-String -Pattern "Up"
        
        if ($serviceStatus) {
            $runningCount++
            Write-Host "✓ $service En ejecución" -ForegroundColor $Green
        }
        else {
            Write-Host "✗ $service Detenido" -ForegroundColor $Red
        }
    }
    
    Write-Host ""
    if ($runningCount -eq $totalCount) {
        Write-Host "✓ Todos los servicios ($runningCount/$totalCount) están en ejecución" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Solo $runningCount de $totalCount servicios están en ejecución" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Error al verificar servicios: $_" -ForegroundColor $Red
}

# Verificar API
Write-Host "Verificando API..." -ForegroundColor $Yellow
try {
    $apiResponse = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 5
    if ($apiResponse.status -eq "online") {
        Write-Host "✓ API: Operativa" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ API: No operativa" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ API: No accesible" -ForegroundColor $Red
}

# Verificar Dashboard
Write-Host "Verificando Dashboard..." -ForegroundColor $Yellow
try {
    $dashboardResponse = Invoke-WebRequest -Uri "http://localhost:3001" -TimeoutSec 5
    if ($dashboardResponse.StatusCode -eq 200) {
        Write-Host "✓ Dashboard: Accesible" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Dashboard: No accesible" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Dashboard: No accesible" -ForegroundColor $Red
}

# Verificar Grafana
Write-Host "Verificando Grafana..." -ForegroundColor $Yellow
try {
    $grafanaResponse = Invoke-WebRequest -Uri "http://localhost:3000" -TimeoutSec 5
    if ($grafanaResponse.StatusCode -eq 200) {
        Write-Host "✓ Grafana: Accesible" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Grafana: No accesible" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Grafana: No accesible" -ForegroundColor $Red
}

# Verificar Prometheus
Write-Host "Verificando Prometheus..." -ForegroundColor $Yellow
try {
    $prometheusResponse = Invoke-WebRequest -Uri "http://localhost:9090" -TimeoutSec 5
    if ($prometheusResponse.StatusCode -eq 200) {
        Write-Host "✓ Prometheus: Accesible" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Prometheus: No accesible" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Prometheus: No accesible" -ForegroundColor $Red
}

# Verificar TimescaleDB
Write-Host "Verificando TimescaleDB..." -ForegroundColor $Yellow
try {
    $dbContainer = docker-compose exec -T timescaledb pg_isready -U postgres 2>$null
    if ($dbContainer -match "accepting connections") {
        Write-Host "✓ TimescaleDB: Aceptando conexiones" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ TimescaleDB: No está listo" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ TimescaleDB: No accesible" -ForegroundColor $Red
}

# Verificar Redis
Write-Host "Verificando Redis..." -ForegroundColor $Yellow
try {
    $redisCommand = "docker-compose exec -T redis redis-cli -a `$env:REDIS_PASSWORD ping"
    $redisResponse = Invoke-Expression $redisCommand 2>$null
    if ($redisResponse -match "PONG") {
        Write-Host "✓ Redis: Responde" -ForegroundColor $Green
    }
    else {
        Write-Host "✗ Redis: No responde" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Redis: No accesible" -ForegroundColor $Red
}

# Verificar uso de recursos
Write-Host "Verificando uso de recursos..." -ForegroundColor $Yellow
try {
    $resourceInfo = docker stats --no-stream --format "{{.Name}}: CPU {{.CPUPerc}}, Mem {{.MemPerc}}"
    Write-Host $resourceInfo
}
catch {
    Write-Host "✗ No se pudo obtener información de recursos: $_" -ForegroundColor $Red
}

# Verificar logs recientes para errores
Write-Host "Verificando logs recientes para errores..." -ForegroundColor $Yellow
try {
    $errorLogs = docker-compose logs --tail=50 | Select-String -Pattern "ERROR|Error|error|Exception|exception"
    
    if ($errorLogs) {
        Write-Host "⚠ Se encontraron errores recientes en los logs:" -ForegroundColor $Yellow
        foreach ($log in $errorLogs) {
            Write-Host "  $log" -ForegroundColor $Red
        }
    }
    else {
        Write-Host "✓ No se encontraron errores recientes en los logs" -ForegroundColor $Green
    }
}
catch {
    Write-Host "✗ No se pudieron verificar los logs: $_" -ForegroundColor $Red
}

Write-Host ""
Write-Host "Diagnóstico completo. Use 'docker-compose logs [servicio]' para ver logs detallados." -ForegroundColor $Blue
Write-Host "Para reiniciar todos los servicios, use: docker-compose restart" -ForegroundColor $Blue
Write-Host "Para reiniciar un servicio específico, use: docker-compose restart [servicio]" -ForegroundColor $Blue