#!/bin/bash
# run.sh - Script para ejecutar todo el sistema

# Función para mostrar mensajes
function log() {
  echo -e "\033[1;34m[$(date '+%Y-%m-%d %H:%M:%S')]\033[0m $1"
}

# Función para verificar requisitos
function check_requirements() {
  log "Verificando requisitos..."
  
  # Verificar Docker
  if ! command -v docker &> /dev/null; then
    log "\033[1;31mError: Docker no está instalado. Por favor, instálelo antes de continuar.\033[0m"
    exit 1
  fi
  
  # Verificar Docker Compose
  if ! command -v docker-compose &> /dev/null; then
    log "\033[1;31mError: Docker Compose no está instalado. Por favor, instálelo antes de continuar.\033[0m"
    exit 1
  fi
  
  # Verificar espacio libre
  if command -v df &> /dev/null; then
    space=$(df -h . | awk 'NR==2 {print $4}')
    log "Espacio libre: $space"
  fi
  
  # Verificar memoria total
  if command -v free &> /dev/null; then
    memory=$(free -h | awk '/^Mem:/ {print $2}')
    log "Memoria total: $memory"
  fi
  
  log "Requisitos verificados correctamente."
}

# Función para verificar y crear directorios
function check_directories() {
  log "Verificando y creando directorios..."
  
  # Comprobar si estamos en el directorio correcto (con docker-compose.yml)
  if [ ! -f "docker-compose.yml" ]; then
    log "\033[1;31mError: No se encontró el archivo docker-compose.yml en el directorio actual.\033[0m"
    log "Asegúrese de ejecutar este script desde el directorio raíz del proyecto."
    exit 1
  fi
  
  # Crear directorio para modelos si no existe
  if [ ! -d "models" ]; then
    log "Creando directorio para modelos..."
    mkdir -p models
  fi
  
  # Crear directorios para componentes si no existen
  components=("collectors/config" "preprocessor" "anomaly_detector" "predictive_engine" "action_recommender" "api" "dashboard" "prometheus" "grafana/provisioning/datasources" "grafana/provisioning/dashboards" "db-init")
  
  for dir in "${components[@]}"; do
    if [ ! -d "$dir" ]; then
      log "Creando directorio: $dir"
      mkdir -p "$dir"
    fi
  done
  
  log "Directorios verificados correctamente."
}

# Función para generar las configuraciones iniciales
function setup_initial_configs() {
  log "Configurando archivos iniciales..."
  
  # Comprobar si existe el archivo .env
  if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
      log "Creando archivo .env a partir de .env.example..."
      cp .env.example .env
      log "\033[1;33mAtención: Se ha creado un archivo .env con valores predeterminados.\033[0m"
      log "\033[1;33mSe recomienda revisar y ajustar las variables de entorno en el archivo .env antes de continuar.\033[0m"
    else
      log "\033[1;31mError: No se encontró el archivo .env.example.\033[0m"
      exit 1
    fi
  fi
  
  # Comprobar si existe la configuración de Prometheus
  if [ ! -f "prometheus/prometheus.yml" ]; then
    log "\033[1;31mError: No se encontró el archivo prometheus.yml.\033[0m"
    log "Por favor, asegúrese de que exista el archivo prometheus/prometheus.yml antes de continuar."
    exit 1
  fi
  
  log "Archivos iniciales configurados correctamente."
}

# Función para iniciar los servicios
function start_services() {
  log "Iniciando servicios..."
  
  # Construir las imágenes Docker
  log "Construyendo imágenes Docker..."
  docker-compose build
  
  # Iniciar servicios
  log "Iniciando contenedores..."
  docker-compose up -d
  
  # Esperar a que los servicios estén disponibles
  log "Esperando a que los servicios estén disponibles..."
  sleep 30
  
  # Verificar el estado de los servicios
  log "Verificando el estado de los servicios..."
  docker-compose ps
  
  log "\033[1;32mServicios iniciados correctamente.\033[0m"
}

# Función para verificar el acceso a los servicios
function check_services() {
  log "Verificando acceso a los servicios..."
  
  # Verificar API
  log "Verificando API REST..."
  if command -v curl &> /dev/null; then
    status_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
    if [ "$status_code" = "200" ]; then
      log "\033[1;32mAPI REST accesible: http://localhost:8000\033[0m"
    else
      log "\033[1;33mADVERTENCIA: API REST no responde correctamente (código $status_code)\033[0m"
    fi
  else
    log "\033[1;33mADVERTENCIA: No se puede verificar la API REST (curl no está instalado)\033[0m"
  fi
  
  # Mostrar enlaces a las interfaces
  log "\033[1;32mEnlaces a las interfaces:\033[0m"
  log "  - Dashboard Web: \033[1;36mhttp://localhost:3001\033[0m"
  log "  - API REST: \033[1;36mhttp://localhost:8000\033[0m"
  log "  - Documentación de la API: \033[1;36mhttp://localhost:8000/docs\033[0m"
  log "  - Grafana: \033[1;36mhttp://localhost:3000\033[0m (usuario: admin, contraseña: admin)"
  log "  - Prometheus: \033[1;36mhttp://localhost:9090\033[0m"
}

# Función principal
function main() {
  log "\033[1;32m============================================\033[0m"
  log "\033[1;32m  Sistema Predictivo de Mantenimiento       \033[0m"
  log "\033[1;32m============================================\033[0m"
  
  # Verificar requisitos
  check_requirements
  
  # Verificar y crear directorios
  check_directories
  
  # Configurar archivos iniciales
  setup_initial_configs
  
  # Preguntar al usuario si desea continuar
  read -p "¿Desea iniciar los servicios ahora? (s/n): " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Ss]$ ]]; then
    log "Operación cancelada por el usuario."
    exit 0
  fi
  
  # Iniciar servicios
  start_services
  
  # Verificar servicios
  check_services
  
  log "\033[1;32m============================================\033[0m"
  log "\033[1;32m  Sistema iniciado correctamente            \033[0m"
  log "\033[1;32m============================================\033[0m"
}

# Ejecutar función principal
main