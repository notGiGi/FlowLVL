# Script para realizar copias de seguridad del sistema de mantenimiento predictivo
# Este script realiza backup de datos, configuraciones y modelos

# Colores para mensajes
$Green = 'Green'
$Blue = 'Cyan'
$Yellow = 'Yellow'
$Red = 'Red'

# Banner
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host "    Sistema de Mantenimiento Predictivo - Backup     " -ForegroundColor $Blue
Write-Host "==========================================================" -ForegroundColor $Blue
Write-Host ""

# Crear directorio para backups si no existe
$backupDir = ".\backups"
if (!(Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
    Write-Host "✓ Directorio de backups creado" -ForegroundColor $Green
}

# Obtener timestamp para el nombre del backup
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupName = "backup_$timestamp"
$backupPath = Join-Path $backupDir $backupName

# Crear directorio para el backup actual
New-Item -ItemType Directory -Path $backupPath -Force | Out-Null
Write-Host "Creando backup en: $backupPath" -ForegroundColor $Yellow

# Crear directorios para organizar el backup
$backupDataDir = Join-Path $backupPath "data"
$backupConfigDir = Join-Path $backupPath "config"
$backupModelsDir = Join-Path $backupPath "models"

New-Item -ItemType Directory -Path $backupDataDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupConfigDir -Force | Out-Null
New-Item -ItemType Directory -Path $backupModelsDir -Force | Out-Null

# Función para copiar directorios con robocopy
function Backup-Directory {
    param (
        [string]$source,
        [string]$destination,
        [string]$description
    )
    
    if (Test-Path $source) {
        Write-Host "Copiando $description..." -ForegroundColor $Yellow
        
        # Crear directorio destino si no existe
        if (!(Test-Path $destination)) {
            New-Item -ItemType Directory -Path $destination -Force | Out-Null
        }
        
        # Usar robocopy para la copia
        robocopy $source $destination /E /R:1 /W:1 /NFL /NDL /NJH /NJS /NC /NS /NP | Out-Null
        
        if ($LASTEXITCODE -lt 8) {
            Write-Host "✓ Backup de $description completado" -ForegroundColor $Green
            return $true
        }
        else {
            Write-Host "✗ Error en backup de $description" -ForegroundColor $Red
            return $false
        }
    }
    else {
        Write-Host "⚠ Directorio $source no existe, saltando backup de $description" -ForegroundColor $Yellow
        return $true
    }
}

# Backup de datos
Backup-Directory -source ".\data" -destination $backupDataDir -description "datos"

# Backup de configuración
Backup-Directory -source ".\config" -destination $backupConfigDir -description "configuración"

# Backup de modelos
Backup-Directory -source ".\models" -destination $backupModelsDir -description "modelos"

# Backup de archivos individuales importantes
$filesToBackup = @(
    ".\.env",
    ".\docker-compose.yml",
    ".\docker-compose.override.yml"
)

foreach ($file in $filesToBackup) {
    if (Test-Path $file) {
        Write-Host "Copiando archivo $file..." -ForegroundColor $Yellow
        Copy-Item -Path $file -Destination $backupPath -Force
        Write-Host "✓ Archivo copiado" -ForegroundColor $Green
    }
}

# Backup de base de datos TimescaleDB
Write-Host "Realizando backup de base de datos TimescaleDB..." -ForegroundColor $Yellow
try {
    # Crear directorio para backup de BD
    $backupDbDir = Join-Path $backupPath "database"
    New-Item -ItemType Directory -Path $backupDbDir -Force | Out-Null
    
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
    
    # Verificar que el contenedor está en ejecución
    $containerStatus = docker ps | Select-String -Pattern "timescaledb"
    if ($containerStatus) {
        # Ejecutar pg_dump dentro del contenedor
        $dumpFile = Join-Path $backupDbDir "predictive_dump.sql"
        docker exec timescaledb pg_dump -U postgres -d predictive > $dumpFile
        
        if (Test-Path $dumpFile) {
            Write-Host "✓ Backup de base de datos completado" -ForegroundColor $Green
        }
        else {
            Write-Host "✗ Error en backup de base de datos" -ForegroundColor $Red
        }
    }
    else {
        Write-Host "✗ Contenedor de TimescaleDB no está en ejecución" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Error en backup de base de datos: $_" -ForegroundColor $Red
}

# Comprimir backup
Write-Host "Comprimiendo backup..." -ForegroundColor $Yellow
try {
    $backupZip = "$backupPath.zip"
    Compress-Archive -Path $backupPath\* -DestinationPath $backupZip -Force
    
    if (Test-Path $backupZip) {
        Write-Host "✓ Backup comprimido correctamente en: $backupZip" -ForegroundColor $Green
        
        # Eliminar directorio temporal
        Remove-Item -Path $backupPath -Recurse -Force
    }
    else {
        Write-Host "✗ Error al comprimir backup" -ForegroundColor $Red
    }
}
catch {
    Write-Host "✗ Error al comprimir backup: $_" -ForegroundColor $Red
}

# Limpiar backups antiguos (mantener solo los 5 más recientes)
try {
    $backupFiles = Get-ChildItem -Path $backupDir -Filter "backup_*.zip" | Sort-Object -Property LastWriteTime -Descending
    
    if ($backupFiles.Count -gt 5) {
        Write-Host "Eliminando backups antiguos..." -ForegroundColor $Yellow
        
        for ($i = 5; $i -lt $backupFiles.Count; $i++) {
            Remove-Item -Path $backupFiles[$i].FullName -Force
            Write-Host "  Eliminado: $($backupFiles[$i].Name)" -ForegroundColor $Yellow
        }
    }
}
catch {
    Write-Host "✗ Error al limpiar backups antiguos: $_" -ForegroundColor $Red
}

Write-Host ""
Write-Host "¡Backup completado!" -ForegroundColor $Green
Write-Host "Archivo de backup: $backupZip" -ForegroundColor $Blue
Write-Host "Para restaurar, use: .\restore.ps1 $backupZip" -ForegroundColor $Blue