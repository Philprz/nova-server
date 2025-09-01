#!/usr/bin/env python3
"""
Script de test pour vérifier que les logs sont moins verbeux
"""

import subprocess
import sys

def test_startup_logs():
    """Teste les logs du script de démarrage"""
    print("🔍 Test des logs du script de démarrage...")
    print("-" * 50)
    
    # Simuler l'exécution du script de démarrage en capturant uniquement les premières lignes
    try:
        # On exécute juste les vérifications préliminaires
        result = subprocess.run(
            [sys.executable, "-c", """
import logging
import sys
import os

# Configuration du logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Import des fonctions depuis startup_script
sys.path.insert(0, '.')
from startup_script import run_pre_flight_checks

# Exécuter uniquement les vérifications préliminaires
run_pre_flight_checks()
"""],
            capture_output=True,
            text=True
        )
        
        print("📝 Logs capturés:")
        print(result.stdout)
        if result.stderr:
            print("⚠️ Erreurs:")
            print(result.stderr)
            
        # Analyser les logs pour détecter les doublons
        lines = result.stdout.split('\n')
        unique_lines = set()
        duplicates = []
        
        for line in lines:
            if line and 'INFO' in line:
                # Extraire le message sans l'horodatage
                msg_part = line.split(' - ', 2)[-1] if ' - ' in line else line
                if msg_part in unique_lines:
                    duplicates.append(msg_part)
                else:
                    unique_lines.add(msg_part)
        
        if duplicates:
            print("\n❌ Doublons détectés:")
            for dup in duplicates:
                print(f"  - {dup}")
        else:
            print("\n✅ Aucun doublon détecté")
            
        # Compter le nombre de lignes de log
        log_count = len([l for l in lines if l and ('INFO' in l or 'WARNING' in l or 'ERROR' in l)])
        print(f"\n📊 Nombre total de lignes de log: {log_count}")
        
        if log_count < 10:
            print("✅ Les logs sont maintenant concis!")
        else:
            print("⚠️ Les logs sont encore un peu verbeux")
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")

if __name__ == "__main__":
    test_startup_logs()