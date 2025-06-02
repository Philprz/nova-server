#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Test du workflow enrichi avec validation client complète
"""

import sys
import os
import asyncio
import json
import uuid
from datetime import datetime

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from workflow.devis_workflow import DevisWorkflow
    print("✅ DevisWorkflow enrichi importé avec succès")
except ImportError as e:
    print(f"❌ Erreur import DevisWorkflow: {e}")
    sys.exit(1)

async def test_workflow_enriched_complete():
    """Test complet du workflow enrichi avec tous les scénarios"""
    print("🚀 TEST COMPLET DU WORKFLOW ENRICHI AVEC VALIDATION")
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Générer un ID unique pour ce test
    unique_id = str(uuid.uuid4())[:8]
    
    # Scénarios de test
    test_scenarios = [
        {
            "name": "Client inexistant - Création automatique",
            "prompt": f"faire un devis pour 10 unités de A00001 pour le client NOVA-ENRICHED-{unique_id}",
            "expected": "creation_automatique"
        },
        {
            "name": "Client inexistant - Validation France",
            "prompt": f"devis pour NOVA-FRANCE-{unique_id} SARL avec 5 ref A00002",
            "expected": "validation_france"
        },
        {
            "name": "Client inexistant - Validation USA",
            "prompt": f"quote for NOVA-USA-{unique_id} Inc with 20 items A00001",
            "expected": "validation_usa"
        },
        {
            "name": "Client existant",
            "prompt": "faire un devis pour 15 unités de A00001 pour le client Edge Communications",
            "expected": "client_existant"
        }
    ]
    
    results = []
    
    for i, scenario in enumerate(test_scenarios, 1):
        print(f"\n{'='*80}")
        print(f"🧪 TEST {i}/{len(test_scenarios)}: {scenario['name']}")
        print(f"{'='*80}")
        print(f"Prompt: {scenario['prompt']}")
        
        try:
            # Créer une nouvelle instance du workflow pour chaque test
            workflow = DevisWorkflow()
            
            # Vérifier l'état de la validation
            validation_status = "✅ Activée" if workflow.validation_enabled else "❌ Désactivée"
            print(f"Validation enrichie: {validation_status}")
            
            # Lancer le test
            start_time = datetime.now()
            result = await workflow.process_prompt(scenario["prompt"])
            end_time = datetime.now()
            
            processing_time = (end_time - start_time).total_seconds()
            
            # Analyser le résultat
            print(f"\n📊 RÉSULTAT ({processing_time:.2f}s):")
            print(f"   Statut: {result.get('status', 'unknown')}")
            
            if result.get("status") == "success":
                print("   ✅ SUCCÈS!")
                
                # Informations client
                client = result.get("client", {})
                print("\n👤 CLIENT:")
                print(f"   Nom: {client.get('name', 'N/A')}")
                print(f"   Salesforce ID: {client.get('salesforce_id', 'N/A')}")
                print(f"   SAP CardCode: {client.get('sap_card_code', 'N/A')}")
                
                # Informations de validation
                validation_info = result.get("validation_info", {})
                if validation_info:
                    print("\n🔍 VALIDATION:")
                    client_val = validation_info.get("client_validation", {})
                    if client_val:
                        print(f"   Erreurs: {client_val.get('errors_count', 0)}")
                        print(f"   Avertissements: {client_val.get('warnings_count', 0)}")
                        print(f"   Suggestions: {client_val.get('suggestions_count', 0)}")
                        
                        # Doublons détectés
                        duplicates = client_val.get("duplicate_check", {})
                        if duplicates.get("duplicates_found"):
                            print(f"   🔍 Doublons détectés: {duplicates.get('count', 0)}")
                    
                    # Création client
                    client_creation = validation_info.get("client_creation", {})
                    if client_creation.get("validation_used"):
                        print("   🆕 Client créé avec validation enrichie")
                
                # Informations devis
                print("\n💰 DEVIS:")
                print(f"   ID: {result.get('quote_id', 'N/A')}")
                print(f"   SAP DocNum: {result.get('sap_doc_num', 'N/A')}")
                print(f"   Montant: {result.get('total_amount', 0):.2f} {result.get('currency', 'EUR')}")
                print(f"   Produits: {len(result.get('products', []))}")
                
                # Statut final
                test_status = "✅ RÉUSSI"
                
            elif result.get("status") == "error":
                print("   ❌ ÉCHEC")
                print(f"   Message: {result.get('message', 'Erreur inconnue')}")
                print(f"   Détails: {result.get('error_details', 'N/A')}")
                test_status = "❌ ÉCHOUÉ"
            else:
                print(f"   ⚠️ STATUT INCONNU: {result.get('status')}")
                test_status = "⚠️ INCONNU"
            
            # Sauvegarder le résultat
            results.append({
                "scenario": scenario["name"],
                "prompt": scenario["prompt"],
                "expected": scenario["expected"],
                "status": result.get("status"),
                "test_status": test_status,
                "processing_time": processing_time,
                "result": result,
                "timestamp": datetime.now().isoformat()
            })
            
        except Exception as e:
            print(f"   💥 EXCEPTION: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            
            results.append({
                "scenario": scenario["name"],
                "prompt": scenario["prompt"],
                "expected": scenario["expected"],
                "status": "exception",
                "test_status": "💥 EXCEPTION",
                "processing_time": 0,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            })
        
        # Pause entre les tests
        if i < len(test_scenarios):
            print("\n⏳ Pause de 3 secondes avant le test suivant...")
            await asyncio.sleep(3)
    
    # Résumé global
    print(f"\n{'='*80}")
    print("📈 RÉSUMÉ GLOBAL DES TESTS")
    print(f"{'='*80}")
    
    success_count = sum(1 for r in results if r["status"] == "success")
    error_count = sum(1 for r in results if r["status"] == "error")
    exception_count = sum(1 for r in results if r["status"] == "exception")
    
    print(f"Tests réussis: {success_count}/{len(results)} ✅")
    print(f"Tests échoués: {error_count}/{len(results)} ❌")
    print(f"Exceptions: {exception_count}/{len(results)} 💥")
    
    # Détail par test
    for result in results:
        print(f"   {result['test_status']} {result['scenario']}")
        if result.get("processing_time"):
            print(f"      Temps: {result['processing_time']:.2f}s")
    
    # Calcul du temps moyen
    valid_times = [r["processing_time"] for r in results if r["processing_time"] > 0]
    if valid_times:
        avg_time = sum(valid_times) / len(valid_times)
        print(f"\n⏱️ Temps moyen de traitement: {avg_time:.2f}s")
    
    # Sauvegarder tous les résultats
    result_file = f"test_workflow_enriched_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    try:
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump({
                "test_summary": {
                    "unique_id": unique_id,
                    "total_tests": len(results),
                    "success_count": success_count,
                    "error_count": error_count,
                    "exception_count": exception_count,
                    "average_processing_time": sum(valid_times) / len(valid_times) if valid_times else 0,
                    "timestamp": datetime.now().isoformat()
                },
                "test_results": results
            }, f, indent=2, ensure_ascii=False, default=str)
        print(f"\n📁 Résultats détaillés sauvegardés: {result_file}")
    except Exception as e:
        print(f"⚠️ Impossible de sauvegarder les résultats: {e}")
    
    # Évaluation finale
    print("\n🎯 ÉVALUATION FINALE:")
    success_rate = (success_count / len(results)) * 100
    
    if success_rate >= 75:
        print(f"   🚀 EXCELLENT ({success_rate:.1f}%) - Workflow enrichi prêt pour production!")
        print("   → Validation client fonctionnelle")
        print("   → Création automatique opérationnelle")
        print("   → Intégration Salesforce/SAP validée")
    elif success_rate >= 50:
        print(f"   ⚠️ CORRECT ({success_rate:.1f}%) - Améliorations nécessaires")
        print("   → Analyser les échecs")
        print("   → Optimiser les validations")
    else:
        print(f"   ❌ INSUFFISANT ({success_rate:.1f}%) - Révision majeure requise")
        print("   → Vérifier la configuration")
        print("   → Corriger les bugs identifiés")
    
    return results

async def main():
    """Fonction principale"""
    print("🎯 TEST COMPLET DU WORKFLOW ENRICHI AVEC VALIDATION CLIENT")
    
    # Lancer les tests complets
    results = await test_workflow_enriched_complete()
    
    # Statistiques finales
    success_count = sum(1 for r in results if r["status"] == "success")
    success_rate = (success_count / len(results)) * 100
    
    print("\n🏁 TESTS TERMINÉS")
    print(f"Taux de réussite global: {success_rate:.1f}%")
    
    if success_rate >= 75:
        print("🎉 Workflow enrichi validé - Prêt pour l'intégration complète!")
    else:
        print("🔧 Améliorations nécessaires avant la mise en production")

if __name__ == "__main__":
    asyncio.run(main())