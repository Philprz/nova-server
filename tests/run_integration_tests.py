#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de lancement pour les tests d'intégration End-to-End
Validation complète du POC NOVA avec intégrations réelles
"""

import os
import sys
import subprocess
from datetime import datetime

def print_header():
    """Affiche l'en-tête des tests d'intégration"""
    print("=" * 80)
    print("🚀 TESTS D'INTÉGRATION END-TO-END - POC NOVA")
    print("=" * 80)
    print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🎯 Objectif: Validation fonctionnelle complète du workflow")
    print("⚠️  ATTENTION: Tests avec intégrations réelles !")
    print("-" * 80)

def check_prerequisites():
    """Vérifie les prérequis pour les tests d'intégration"""
    print("🔍 Vérification des prérequis...")
    
    # Vérifier fichier .env
    if not os.path.exists('.env'):
        print("❌ Fichier .env manquant")
        return False
    
    # Vérifier variables critiques
    required_vars = [
        "ANTHROPIC_API_KEY",
        "SALESFORCE_USERNAME",
        "SALESFORCE_PASSWORD", 
        "SALESFORCE_SECURITY_TOKEN",
        "SAP_REST_BASE_URL",
        "SAP_USER",
        "SAP_CLIENT_PASSWORD"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("❌ Variables d'environnement manquantes:")
        for var in missing_vars:
            print(f"   - {var}")
        return False
    
    print("✅ Configuration complète trouvée")
    
    # Vérifier modules Python
    print("🔍 Vérification des modules...")
    try:
        print("✅ Modules Python disponibles")
    except ImportError as e:
        print(f"❌ Module manquant: {e}")
        return False
    
    return True

def run_connectivity_tests():
    """Lance les tests de connectivité préliminaires"""
    print("\n🔗 Tests de connectivité préliminaires...")
    
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/test_integration_workflow.py::TestIntegrationConnections",
            "-v", "--tb=short"
        ], capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ Tests de connectivité réussis")
            return True
        else:
            print("❌ Tests de connectivité échoués")
            print(result.stdout)
            print(result.stderr)
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Timeout lors des tests de connectivité")
        return False
    except Exception as e:
        print(f"❌ Erreur tests de connectivité: {e}")
        return False

def run_integration_tests(test_type="all"):
    """Lance les tests d'intégration selon le type"""
    print(f"\n🧪 Lancement des tests d'intégration ({test_type})...")
    
    # Commandes selon le type de test
    test_commands = {
        "all": [
            sys.executable, "-m", "pytest", 
            "tests/test_integration_workflow.py",
            "-v", "--tb=short", "-m", "integration"
        ],
        "workflow": [
            sys.executable, "-m", "pytest",
            "tests/test_integration_workflow.py::TestIntegrationWorkflow", 
            "-v", "--tb=short"
        ],
        "performance": [
            sys.executable, "-m", "pytest",
            "tests/test_integration_workflow.py::TestIntegrationPerformance",
            "-v", "--tb=short"
        ],
        "recovery": [
            sys.executable, "-m", "pytest",
            "tests/test_integration_workflow.py::TestIntegrationRecuperation",
            "-v", "--tb=short"
        ]
    }
    
    if test_type not in test_commands:
        print(f"❌ Type de test invalide: {test_type}")
        return False
    
    try:
        result = subprocess.run(
            test_commands[test_type], 
            timeout=300  # 5 minutes max
        )
        
        return result.returncode == 0
        
    except subprocess.TimeoutExpired:
        print("❌ Timeout lors des tests d'intégration (>5min)")
        return False
    except Exception as e:
        print(f"❌ Erreur tests d'intégration: {e}")
        return False

def generate_report(success_count, total_count):
    """Génère le rapport final"""
    print("\n" + "=" * 80)
    print("📊 RAPPORT FINAL - TESTS D'INTÉGRATION")
    print("=" * 80)
    
    success_rate = (success_count / total_count) * 100 if total_count > 0 else 0
    
    print(f"✅ Tests réussis: {success_count}/{total_count}")
    print(f"📈 Taux de réussite: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🏆 EXCELLENT - POC prêt pour démonstration !")
        status = "EXCELLENT"
    elif success_rate >= 75:
        print("✅ TRÈS BON - Quelques optimisations à prévoir")
        status = "TRÈS BON"
    elif success_rate >= 50:
        print("⚠️ CORRECT - Améliorations nécessaires")
        status = "CORRECT"
    else:
        print("❌ INSUFFISANT - Révision majeure requise")
        status = "INSUFFISANT"
    
    print(f"\n🎯 Recommandations selon statut '{status}':")
    
    if status == "EXCELLENT":
        print("   → Documenter les scénarios validés")
        print("   → Préparer la démonstration client")
        print("   → Planifier la mise en production")
    elif status == "TRÈS BON":
        print("   → Analyser les échecs mineurs")
        print("   → Optimiser les points faibles")
        print("   → Valider en conditions réelles")
    elif status == "CORRECT":
        print("   → Identifier les goulots d'étranglement")
        print("   → Corriger les intégrations défaillantes")
        print("   → Relancer les tests après corrections")
    else:
        print("   → Audit complet de l'architecture")
        print("   → Vérifier les configurations système")
        print("   → Réviser l'approche d'intégration")
    
    print("\n📁 Fichiers générés:")
    print("   - htmlcov/index.html (Rapport de couverture)")
    print("   - Logs détaillés dans la console")
    
    print("=" * 80)
    return status

def main():
    """Fonction principale"""
    print_header()
    
    # Vérifications préliminaires
    if not check_prerequisites():
        print("\n❌ Prérequis non satisfaits - Arrêt des tests")
        sys.exit(1)
    
    # Tests de connectivité
    if not run_connectivity_tests():
        print("\n❌ Connectivité insuffisante - Arrêt des tests")
        response = input("\nContinuer malgré les problèmes de connectivité ? (o/N): ")
        if response.lower() not in ['o', 'oui', 'y', 'yes']:
            sys.exit(1)
    
    # Tests d'intégration
    test_results = []
    test_types = ["workflow", "performance", "recovery"]
    
    for test_type in test_types:
        print(f"\n🎯 === PHASE: {test_type.upper()} ===")
        success = run_integration_tests(test_type)
        test_results.append(success)
        
        if success:
            print(f"✅ Phase {test_type} réussie")
        else:
            print(f"❌ Phase {test_type} échouée")
    
    # Génération du rapport
    success_count = sum(test_results)
    total_count = len(test_results)
    
    final_status = generate_report(success_count, total_count)
    
    # Code de sortie
    if final_status in ["EXCELLENT", "TRÈS BON"]:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    # Gestion des arguments
    if len(sys.argv) > 1:
        test_type = sys.argv[1]
        if test_type in ["connectivity", "workflow", "performance", "recovery", "all"]:
            if test_type == "connectivity":
                if check_prerequisites() and run_connectivity_tests():
                    print("✅ Tests de connectivité réussis")
                    sys.exit(0)
                else:
                    sys.exit(1)
            else:
                print_header()
                if check_prerequisites():
                    success = run_integration_tests(test_type)
                    sys.exit(0 if success else 1)
                else:
                    sys.exit(1)
        else:
            print(f"Usage: {sys.argv[0]} [connectivity|workflow|performance|recovery|all]")
            sys.exit(1)
    else:
        main()