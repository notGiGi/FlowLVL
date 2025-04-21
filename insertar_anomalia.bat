@echo off
echo Sistema de inserción de anomalías
echo ===============================
echo.
echo 1. Insertar anomalía en app-server (severidad media)
echo 2. Insertar anomalía en app-server (severidad alta)
echo 3. Insertar anomalía en app-server (severidad crítica)
echo 4. Insertar anomalía en database (severidad media)
echo 5. Insertar anomalía en database (severidad alta)
echo 6. Insertar anomalía en database (severidad crítica)
echo.
set /p choice="Selecciona una opción (1-6): "

if "%choice%"=="1" (
    python force_anomaly.py app-server --severity medium
) else if "%choice%"=="2" (
    python force_anomaly.py app-server --severity high
) else if "%choice%"=="3" (
    python force_anomaly.py app-server --severity critical
) else if "%choice%"=="4" (
    python force_anomaly.py database --severity medium
) else if "%choice%"=="5" (
    python force_anomaly.py database --severity high
) else if "%choice%"=="6" (
    python force_anomaly.py database --severity critical
) else (
    echo Opción no válida
)

echo.
pause