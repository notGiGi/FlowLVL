# Script para restaurar el sistema de mantenimiento predictivo desde un backup
# Uso: .\restore.ps1 [ruta_backup.zip]

param(
    [Parameter(Mandatory=$true)]
    [string]$BackupFile
)

# Colores para mensajes
$Green = 'Green'
$Blue = 'Cyan'
$Yellow = 'Yellow'
$Red = 'Red'

# Banner
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host "    Sistema de Mantenimiento Predictivo - Restauración    " -ForegroundColor $Blue
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host ""

# Verificar que el archivo de backup existe
if (!(Test-Path $BackupFile)) {
    Write-Host "✗ Archivo de backup no encontrado: $BackupFile" -ForegroundColor $Red
    exit 1
}

# Crear directorio temporal para restauración
$tempRestoreDir = ".\restore_temp"
if (Test-Path $tempRestoreDir) {
    Remove-Item -Path $tempRestoreDir -Recurse -Force
}
New-Item -ItemType Directory -Path $tempRestoreDir -Force | Out-Null

# Extraer archivo de backup
Write-Host "Extrayendo backup..." -ForegroundColor $Yellow
try {
    Expand-Archive -Path $BackupFile -DestinationPath $tempRestoreDir -Force
    Write-Host "✓ Backup extraído correctamente" -ForegroundColor $Green
}
catch {
    Write-Host "✗ Error al extraer backup: $_" -ForegroundColor $Red
    exit 1
}

# Verificar servicios en ejecución
Write-Host "Verificando estado de servicios..." -ForegroundColor $Yellow
$servicesRunning = $false
try {
    $runningServices = docker-compose ps --services --filter "status=running"
    if ($runningServices) {
        $servicesRunning = $true
        Write-Host "Los siguientes servicios están en ejecución:" -ForegroundColor $Yellow
        foreach ($service in $runningServices) {
            Write-Host "  - $service" -ForegroundColor $Yellow
        }
        
        $stopServices = Read-Host "¿Desea detener los servicios para la restauración? (s/n)"
        if ($stopServices -eq 's' -or $stopServices -eq 'S' -or $stopServices -eq 'y' -or $stopServices -eq 'Y') {
            Write-Host "Deteniendo servicios..." -ForegroundColor $Yellow
            docker-compose down
            Write-Host "✓ Servicios detenidos" -ForegroundColor $Green
            $servicesRunning = $false
        }
        else {
            Write-Host "⚠ Continuando con los servicios en ejecución" -ForegroundColor $Yellow
            Write-Host "  Nota: Algunos archivos pueden no restaurarse correctamente" -ForegroundColor $Yellow
        }
    }
    else {
        Write-Host "✓ No hay servicios en ejecución" -ForegroundColor $Green
    }
}
catch {
    Write-Host "✗ Error al verificar servicios: $_" -ForegroundColor $Red
}

# Función para restaurar directorios con robocopy
function Restore-Directory {
    param (
        [string]$source,
        [string]$destination,
        [string]$description
    )
    
    if (Test-Path $source) {
        Write-Host "Restaurando $description..." -ForegroundColor $Yellow
        
        # Crear directorio destino si no existe
        if (!(Test-Path $destination)) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
        }
        
        # Usar robocopy para la copia
        robocopy $source $destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
        
        if ($LASTEXITCODE -lt 8) {
            Write-Host "✓ Restauración de $description completada" -ForegroundColor $Green
            return $true
        }
        else {
            Write-Host "✗ Error en restauración de $description" -ForegroundColor $Red
            return $false
        }
    }
    else {
        Write-Host "⚠ Directorio $source no existe en el backup, saltando restauración de $description" -ForegroundColor $Yellow
        return $true
    }
}

# Restaurar archivos de configuración
$configSource = Join-Path $tempRestoreDir "config"
if (Test-Path $configSource) {
    Restore-Directory -source $configSource -destination ".\config" -description "configuración"
}

# Restaurar modelos
$modelsSource = Join-Path $tempRestoreDir "models"
if (Test-Path $modelsSource) {
    Restore-Directory -source $modelsSource -destination ".\models" -description "modelos"
}

# Restaurar datos
$dataSource = Join-Path $tempRestoreDir "data"
if (Test-Path $dataSource) {
    Restore-Directory -source $dataSource -destination ".\data" -description "datos"
}

# Restaurar archivos individuales
$filesToRestore = @(
    ".env",
    "docker-compose.yml",
    "docker-compose.override.yml"
)

foreach ($file in $filesToRestore) {
    $sourceFile = Join-Path $tempRestoreDir $file
    if (Test-Path $sourceFile) {
        Write-Host "Restaurando archivo $file..." -ForegroundColor $Yellow
        
        # Preguntar si se debe sobrescribir
        if (Test-Path ".\$file") {
            $overwrite = Read-Host "El archivo $file ya existe. ¿Desea sobrescribirlo? (s/n)"
            if ($overwrite -ne 's' -and $overwrite -ne 'S' -and $overwrite -ne 'y' -and $overwrite -ne 'Y') {
                Write-Host "⚠ Archivo $file no restaurado" -ForegroundColor $Yellow
                continue
            }
        }
        
        Copy-Item -Path $sourceFile -Destination ".\" -Force
        Write-Host "✓ Archivo $file restaurado" -ForegroundColor $Green
    }
}

# Restaurar base de datos si los servicios están detenidos
$dbBackupFile = Join-Path $tempRestoreDir "database\predictive_dump.sql"
if (Test-Path $dbBackupFile) {
    if (!$servicesRunning) {
        Write-Host "Restaurando base de datos..." -ForegroundColor $Yellow
        
        $restoreDb = Read-Host "¿Desea restaurar la base de datos? (s/n)"
        if ($restoreDb -eq 's' -or $restoreDb -eq 'S' -or $restoreDb -eq 'y' -or $restoreDb -eq 'Y') {
            # Iniciar solo TimescaleDB
            Write-Host "Iniciando TimescaleDB..." -ForegroundColor $Yellow
            docker-compose up -d timescaledb
            
            # Esperar a que esté listo
            Write-Host "Esperando a que TimescaleDB esté listo..." -ForegroundColor $Yellow
            Start-Sleep -Seconds 15
            
            # Obtener contraseña desde .env o usar predeterminada
            $dbPassword = "postgres"
            if (Test-Path ".\.env") {
                $envContent = Get-Content ".\.env" -Raw
                if ($envContent -match 'TIMESCALEDB_PASSWORD=(.*)') {
                    $dbPassword = $matches[1].Trim()
                }
            }
            
            # Establecer variables de entorno
            $env:PGPASSWORD = $dbPassword
            
            # Restaurar BD
            try {
                # Crear base de datos si no existe
                docker exec timescaledb psql -U postgres -c "CREATE DATABASE predictive WITH OWNER postgres;" 2>$null
                
                # Restaurar
                Get-Content $dbBackupFile | docker exec -i timescaledb psql -U postgres -d predictive
                Write-Host "✓ Base de datos restaurada correctamente" -ForegroundColor $Green
            }
            catch {
                Write-Host "✗ Error al restaurar base de datos: $_" -ForegroundColor $Red
            }
        }
    }
    else {
        Write-Host "⚠ No se puede restaurar la base de datos con los servicios en ejecución" -ForegroundColor $Yellow
        Write-Host "  Detenga los servicios primero y luego restaure manualmente la base de datos" -ForegroundColor $Yellow
    }
}

# Limpiar
Write-Host "Limpiando archivos temporales..." -ForegroundColor $Yellow
Remove-Item -Path $tempRestoreDir -Recurse -Force
Write-Host "✓ Limpieza completada" -ForegroundColor $Green

# Preguntar si iniciar servicios
if (!$servicesRunning) {
    $startServices = Read-Host "¿Desea iniciar los servicios ahora? (s/n)"
    if ($startServices -eq 's' -or $startServices -eq 'S' -or $startServices -eq 'y' -or $startServices -eq 'Y') {
        Write-Host "Iniciando servicios..." -ForegroundColor $Yellow
        docker-compose up -d
        Write-Host "✓ Servicios iniciados" -ForegroundColor $Green
    }
}

Write-Host ""
Write-Host "¡Restauración completada!" -ForegroundColor $Green
Write-Host "Si necesita iniciar o reiniciar los servicios, ejecute: docker-compose up -d" -ForegroundColor $Blue
Write-Host "Para verificar el estado del sistema, ejecute: .\check_system.ps1" -ForegroundColor $Blue