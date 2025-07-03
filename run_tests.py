
import subprocess
import sys
from pathlib import Path
import os

def run_tests():
    """Exécute tous les tests avec le bon environnement"""
    project_root = Path(__file__).parent
    
    # S'assurer qu'on est dans le bon répertoire
    os.chdir(project_root)
    
    # Exécuter les tests
    test_files = [
        "tests/test_missing_info_workflow.py",
        # Ajouter d'autres fichiers de test ici
    ]
    
    for test_file in test_files:
        print(f"\n{'='*50}")
        print(f"Exécution de {test_file}")
        print('='*50)
        
        result = subprocess.run(
            [sys.executable, "-m", test_file.replace('/', '.').replace('.py', '')],
            capture_output=True,
            text=True
        )
        
        print(result.stdout)
        if result.stderr:
            print("ERREURS:", result.stderr)

if __name__ == "__main__":
    run_tests()