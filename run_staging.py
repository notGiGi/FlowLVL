# run_staging.py
import subprocess
import sys
import time

def run_integration_tests():
    print("=== Ejecución de pruebas de integración ===")
    retcode = subprocess.call([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_integration.py"])
    if retcode == 0:
        print("Pruebas de integración completadas exitosamente.\n")
    else:
        print("Fallas en las pruebas de integración.\n")
    return retcode

def run_load_tests():
    print("=== Ejecución de prueba de carga ===")
    retcode = subprocess.call([sys.executable, "tests/load_test.py"])
    print("Prueba de carga finalizada.\n")
    return retcode

if __name__ == "__main__":
    overall_start = time.time()
    ret_integration = run_integration_tests()
    if ret_integration != 0:
        print("Abortando debido a fallas en las pruebas de integración.")
        sys.exit(ret_integration)
    ret_load = run_load_tests()
    if ret_load != 0:
        print("Abortando debido a fallas en la prueba de carga.")
        sys.exit(ret_load)
    overall_time = time.time() - overall_start
    print(f"Fase de Staging completada en {overall_time:.2f} segundos.")
