# Script para reiniciar el sistema
# Guardar como: restart.sh
#!/bin/bash

echo "Reiniciando el sistema..."
docker-compose down
docker-compose up -d

echo "Esperando a que los servicios estén disponibles..."
sleep 30

echo "¡Sistema reiniciado correctamente!"

