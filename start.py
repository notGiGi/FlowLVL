# -*- coding: utf-8 -*-
import subprocess
import os
import time
import webbrowser
import sys

def run_command(command, wait=True):
    if wait:
        subprocess.call(command, shell=True)
    else:
        if os.name == 'nt':  # Windows
            subprocess.Popen(command, shell=True)
        else:  # Linux/Mac
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

print("Iniciando sistema de mantenimiento predictivo...")

# Iniciar el sistema principal en segundo plano
print("Iniciando el motor principal...")
run_command("python main.py", wait=False)

# Esperar a que el sistema se inicie
print("Esperando a que el sistema se inicie...")
time.sleep(3)

# Iniciar el servidor web
print("Iniciando el servidor web...")
run_command("python api.py", wait=False)

# Esperar a que el servidor web se inicie
print("Esperando a que el servidor web se inicie...")
time.sleep(3)

# Abrir el navegador
print("Abriendo el navegador...")
try:
    webbrowser.open("http://localhost:5000")
    print("Interfaz web abierta en http://localhost:5000")
except:
    print("No se pudo abrir el navegador automáticamente")
    print("Por favor, abre manualmente http://localhost:5000")

print("\nSistema iniciado correctamente!")
print("Presiona Ctrl+C para detener el sistema cuando hayas terminado")

try:
    # Mantener el script en ejecución
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\nDeteniendo el sistema...")
    if os.name == 'nt':  # Windows
        run_command("taskkill /f /im python.exe", wait=True)
    else:
        run_command("pkill -f python", wait=True)
    print("Sistema detenido correctamente")
