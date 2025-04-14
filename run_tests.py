import os
import sys
import time
import subprocess

def run_test(test_file):
    print(f"\n=== Ejecutando {test_file} ===\n")
    result = subprocess.run([sys.executable, test_file])
    return result.returncode == 0

def main():
    # Lista de pruebas
    tests = [
        "tests/test_scenario1.py",
        "tests/test_scenario2.py", 
        "tests/test_scenario3.py"
    ]
    
    # Ejecutar cada prueba
    results = {}
    for test in tests:
        success = run_test(test)
        results[test] = success
        time.sleep(1)  # Pausa entre pruebas
    
    # Mostrar resultados
    print("\n=== RESULTADOS DE LAS PRUEBAS ===")
    all_success = True
    for test, success in results.items():
        status = "EXITOSO" if success else "FALLIDO"
        print(f"{test}: {status}")
        all_success = all_success and success
    
    print(f"\nResultado general: {'TODAS LAS PRUEBAS EXITOSAS' if all_success else 'ALGUNAS PRUEBAS FALLARON'}")
    
if __name__ == "__main__":
    main()
