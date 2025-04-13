#!/bin/bash
# verify-installation.sh - Verifica que todos los componentes estén correctamente instalados

echo "Verificando la instalación del sistema predictivo..."

# Función para verificar archivo
check_file() {
    if [ -f "$1" ]; then
        echo "✅ $1 encontrado"
        return 0
    else
        echo "❌ $1 no encontrado"
        return 1
    fi
}

# Función para verificar directorio
check_dir() {
    if [ -d "$1" ]; then
        echo "✅ $1 encontrado"
        return 0
    else
        echo "❌ $1 no encontrado"
        return 1
    fi
}

# Verificar archivos principales
echo "Verificando archivos principales..."
main_files=("docker-compose.yml" ".env")
main_ok=true

for file in "${main_files[@]}"; do
    if ! check_file "$file"; then
        main_ok=false
    fi
done

if $main_ok; then
    echo "✅ Archivos principales OK"
else
    echo "❌ Faltan archivos principales"
fi

# Verificar componentes
echo ""
echo "Verificando componentes..."
components=("collectors" "preprocessor" "anomaly_detector" "predictive_engine" "action_recommender" "api" "dashboard")
components_ok=true

for component in "${components[@]}"; do
    if ! check_dir "$component"; then
        components_ok=false
        continue
    fi
    
    # Verificar Dockerfile y requirements.txt (excepto dashboard)
    if [ "$component" != "dashboard" ]; then
        if ! check_file "$component/Dockerfile"; then
            components_ok=false
        fi
        
        if ! check_file "$component/requirements.txt"; then
            components_ok=false
        fi
    else
        # Verificar archivos específicos del dashboard
        if ! check_file "$component/Dockerfile"; then
            components_ok=false
        fi
        
        if ! check_file "$component/package.json"; then
            components_ok=false
        fi
        
        if ! check_file "$component/nginx.conf"; then
            components_ok=false
        fi
    fi
    
    # Verificar archivos de código específicos
    case "$component" in
        "collectors")
            check_file "$component/collector.py" || components_ok=false
            check_dir "$component/config" || components_ok=false
            ;;
        "preprocessor")
            check_file "$component/preprocessor.py" || components_ok=false
            ;;
        "anomaly_detector")
            check_file "$component/anomaly_detector.py" || components_ok=false
            ;;
        "predictive_engine")
            check_file "$component/predictive_engine.py" || components_ok=false
            ;;
        "action_recommender")
            check_file "$component/action_recommender.py" || components_ok=false
            ;;
        "api")
            check_file "$component/main.py" || components_ok=false
            ;;
        "dashboard")
            check_dir "$component/src" || components_ok=false
            ;;
    esac
done

if $components_ok; then
    echo "✅ Componentes OK"
else
    echo "❌ Faltan archivos en algunos componentes"
fi

# Verificar configuraciones adicionales
echo ""
echo "Verificando configuraciones adicionales..."
configs_ok=true

# Verificar Prometheus
if ! check_dir "prometheus"; then
    configs_ok=false
else
    check_file "prometheus/prometheus.yml" || configs_ok=false
fi

# Verificar Grafana
if ! check_dir "grafana"; then
    configs_ok=false
else
    check_dir "grafana/provisioning" || configs_ok=false
    check_dir "grafana/provisioning/datasources" || configs_ok=false
    check_dir "grafana/provisioning/dashboards" || configs_ok=false
    check_file "grafana/provisioning/datasources/datasource.yml" || configs_ok=false
    check_file "grafana/provisioning/dashboards/dashboards.yml" || configs_ok=false
    check_file "grafana/provisioning/dashboards/system_overview.json" || configs_ok=false
fi

# Verificar inicialización de base de datos
if ! check_dir "db-init"; then
    configs_ok=false
else
    check_file "db-init/init-timescaledb.sh" || configs_ok=false
fi

if $configs_ok; then
    echo "✅ Configuraciones adicionales OK"
else
    echo "❌ Faltan configuraciones adicionales"
fi

# Resumen
echo ""
echo "Resumen de la verificación:"
if $main_ok && $components_ok && $configs_ok; then
    echo "✅ Todos los archivos necesarios están presentes"
    echo "El sistema está listo para ser iniciado con: ./run.sh"
else
    echo "❌ Faltan algunos archivos necesarios"
    echo "Por favor, complete la instalación antes de iniciar el sistema"
fi

# Verificar permisos de ejecución
echo ""
echo "Verificando permisos de ejecución para scripts..."
scripts=("run.sh" "install-dependencies.sh" "db-init/init-timescaledb.sh")
permissions_ok=true

for script in "${scripts[@]}"; do
    if [ -f "$script" ]; then
        if [ -x "$script" ]; then
            echo "✅ $script tiene permisos de ejecución"
        else
            echo "❌ $script no tiene permisos de ejecución"
            echo "   Ejecute: chmod +x $script"
            permissions_ok=false
        fi
    fi
done

if ! $permissions_ok; then
    echo ""
    echo "❗ Algunos scripts no tienen permisos de ejecución"
    echo "Ejecute el siguiente comando para asignar permisos:"
    echo "chmod +x run.sh install-dependencies.sh db-init/init-timescaledb.sh"
fi