# Servidor web para el sistema de mantenimiento predictivo
from api import app

if __name__ == "__main__":
    print("Iniciando servidor web en http://localhost:8080")
    print("Presiona CTRL+C para detener el servidor")
    app.run(host="0.0.0.0", port=8080, debug=False)