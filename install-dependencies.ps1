# install-dependencies.ps1 - Script para instalar dependencias en Windows PowerShell

Write-Host "Instalando dependencias para todos los componentes..."

# Crear entornos virtuales para cada componente Python
$components = @("collectors", "preprocessor", "anomaly_detector", "predictive_engine", "action_recommender", "api")

foreach ($component in $components) {
    Write-Host "Configurando entorno virtual para $component..."
    
    if (Test-Path -Path $component) {
        # Crear entorno virtual
        python -m venv "$component\venv"
        
        # Activar entorno virtual e instalar dependencias
        if (Test-Path -Path "$component\requirements.txt") {
            Write-Host "Instalando dependencias para $component..."
            & "$component\venv\Scripts\pip" install -r "$component\requirements.txt"
        } else {
            Write-Host "No se encontró requirements.txt para $component"
        }
    } else {
        Write-Host "El directorio $component no existe"
    }
}

# Instalar dependencias para el dashboard
if (Test-Path -Path "dashboard") {
    Write-Host "Instalando dependencias para el dashboard..."
    
    # Verificar si Node.js está instalado
    try {
        $nodeVersion = node --version
        Write-Host "Node.js detectado: $nodeVersion"
        
        Set-Location dashboard
        npm install
        Set-Location ..
    } catch {
        Write-Host "ADVERTENCIA: Node.js no está instalado. No se pueden instalar las dependencias del dashboard."
        Write-Host "Por favor, instala Node.js e instala las dependencias manualmente con 'npm install' en el directorio dashboard."
    }
} else {
    Write-Host "El directorio dashboard no existe"
}

Write-Host "Instalación de dependencias completada."