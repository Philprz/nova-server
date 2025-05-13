import sys
import os

# Afficher l'environnement Python utilisé
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Python path: {sys.path}")

# Tenter d'importer simple-salesforce
try:
    import simple_salesforce
    print("✅ Import simple_salesforce réussi")
    print(f"Version: {simple_salesforce.__version__}")
    print(f"Path: {simple_salesforce.__file__}")
except ImportError as e:
    print(f"❌ Erreur d'import: {e}")

# Vérifier si le package est installé dans pip
import subprocess
try:
    result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True)
    print("\nPackages installés:")
    for line in result.stdout.split('\n'):
        if 'salesforce' in line.lower():
            print(f"TROUVÉ: {line}")
except Exception as e:
    print(f"Erreur lors de la vérification des packages: {e}")