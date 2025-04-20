# -*- coding: utf-8 -*-
import logging

# Configurar nivel de logging m�s detallado
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("debug.log"),
        logging.StreamHandler()
    ]
)

# Obtener y configurar loggers principales
loggers = [
    'predictive_maintenance',
    'api_server',
    'simple_collector',
    'simple_detector',
    'simple_recommender'
]

for logger_name in loggers:
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)
    
    # A�adir handler que muestre mensajes en consola
    console = logging.StreamHandler()
    console.setLevel(logging.DEBUG)
    logger.addHandler(console)

print("Logging configurado en modo DEBUG. Los mensajes se mostrar�n en consola y en debug.log")
