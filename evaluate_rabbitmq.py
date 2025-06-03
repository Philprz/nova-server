# evaluate_rabbitmq.py
"""
Script d'évaluation pour déterminer si RabbitMQ/aio-pika est nécessaire
pour les objectifs du POC NOVA
"""

import asyncio
import time
from typing import Dict, Any
from datetime import datetime       

# Simulation des charges de travail actuelles
class WorkloadSimulator:
    """Simule les charges de travail actuelles du POC pour évaluer le besoin de RabbitMQ"""
    
    def __init__(self):
        self.metrics = {
            "sync_operations": [],
            "async_operations": [],
            "concurrent_requests": [],
            "processing_times": []
        }
    
    async def simulate_current_workflow(self) -> Dict[str, Any]:
        """Simule le workflow actuel de génération de devis"""
        print("🔄 Simulation du workflow actuel de génération de devis...")
        
        start_time = time.time()
        
        # 1. Extraction LLM (Claude) - 2-5 secondes
        await self._simulate_llm_extraction()
        
        # 2. Validation client Salesforce - 1-3 secondes
        await self._simulate_salesforce_validation()
        
        # 3. Récupération produits SAP - 2-4 secondes par produit
        await self._simulate_sap_products(num_products=3)
        
        # 4. Création devis - 1-2 secondes
        await self._simulate_quote_creation()
        
        total_time = time.time() - start_time
        
        return {
            "total_processing_time": total_time,
            "steps_count": 4,
            "average_step_time": total_time / 4,
            "needs_background_processing": total_time > 10.0
        }
    
    async def _simulate_llm_extraction(self):
        """Simule l'appel à Claude pour extraction"""
        await asyncio.sleep(0.3)  # 300ms simulées
        self.metrics["async_operations"].append({
            "operation": "llm_extraction",
            "duration": 0.3,
            "type": "external_api"
        })
    
    async def _simulate_salesforce_validation(self):
        """Simule la validation client Salesforce"""
        await asyncio.sleep(0.2)  # 200ms simulées
        self.metrics["async_operations"].append({
            "operation": "salesforce_validation",
            "duration": 0.2,
            "type": "external_api"
        })
    
    async def _simulate_sap_products(self, num_products: int):
        """Simule la récupération de produits SAP"""
        for i in range(num_products):
            await asyncio.sleep(0.15)  # 150ms par produit
            self.metrics["async_operations"].append({
                "operation": f"sap_product_{i}",
                "duration": 0.15,
                "type": "external_api"
            })
    
    async def _simulate_quote_creation(self):
        """Simule la création du devis"""
        await asyncio.sleep(0.1)  # 100ms simulées
        self.metrics["sync_operations"].append({
            "operation": "quote_creation",
            "duration": 0.1,
            "type": "business_logic"
        })
    
    async def simulate_concurrent_load(self, num_concurrent: int = 5) -> Dict[str, Any]:
        """Simule une charge concurrente"""
        print(f"⚡ Simulation de {num_concurrent} demandes concurrentes...")
        
        start_time = time.time()
        
        # Lancer plusieurs workflows en parallèle
        tasks = [self.simulate_current_workflow() for _ in range(num_concurrent)]
        results = await asyncio.gather(*tasks)
        
        total_time = time.time() - start_time
        
        return {
            "concurrent_requests": num_concurrent,
            "total_time": total_time,
            "average_time_per_request": sum(r["total_processing_time"] for r in results) / len(results),
            "actual_concurrent_efficiency": total_time,
            "results": results
        }

def analyze_current_architecture():
    """Analyse l'architecture actuelle pour identifier les besoins"""
    print("\n🏗️ ANALYSE DE L'ARCHITECTURE ACTUELLE")
    print("=" * 45)
    
    current_patterns = {
        "async_http_calls": {
            "description": "Appels HTTP asynchrones (Claude, Salesforce, SAP)",
            "current_solution": "httpx.AsyncClient",
            "scalability": "Excellente pour POC",
            "limitations": "Pas de retry avancé, pas de persistance"
        },
        "workflow_orchestration": {
            "description": "Orchestration du workflow de devis",
            "current_solution": "DevisWorkflow avec asyncio",
            "scalability": "Bonne pour POC",
            "limitations": "Pas de reprise d'erreur, pas de monitoring"
        },
        "mcp_communication": {
            "description": "Communication avec serveurs MCP",
            "current_solution": "subprocess + fichiers temporaires",
            "scalability": "Suffisante pour POC",
            "limitations": "Pas optimisé, pas de pool de connexions"
        },
        "error_handling": {
            "description": "Gestion d'erreurs et retry",
            "current_solution": "Try/catch basique",
            "scalability": "Limitée",
            "limitations": "Pas de retry intelligent, pas de circuit breaker"
        }
    }
    
    for pattern_name, details in current_patterns.items():
        print(f"\n📋 {pattern_name.upper()}:")
        print(f"   Description: {details['description']}")
        print(f"   Solution actuelle: {details['current_solution']}")
        print(f"   Scalabilité: {details['scalability']}")
        print(f"   Limitations: {details['limitations']}")
    
    return current_patterns

def evaluate_rabbitmq_benefits():
    """Évalue les bénéfices potentiels de RabbitMQ"""
    print("\n🐰 ÉVALUATION DES BÉNÉFICES RABBITMQ")
    print("=" * 40)
    
    rabbitmq_benefits = {
        "reliability": {
            "benefit": "Persistance des messages, garantie de livraison",
            "poc_relevance": "Faible - Le POC peut tolérer quelques échecs",
            "complexity_added": "Moyenne - Configuration, gestion des connexions"
        },
        "scalability": {
            "benefit": "Distribution de charge, scaling horizontal",
            "poc_relevance": "Faible - POC mono-utilisateur",
            "complexity_added": "Élevée - Infrastructure supplémentaire"
        },
        "decoupling": {
            "benefit": "Découplage entre producteurs et consommateurs",
            "poc_relevance": "Moyenne - Peut simplifier certains workflows",
            "complexity_added": "Moyenne - Nouveaux patterns de code"
        },
        "monitoring": {
            "benefit": "Monitoring avancé des queues et messages",
            "poc_relevance": "Faible - Le POC a des besoins simples",
            "complexity_added": "Faible - Interface web native"
        },
        "retry_dlq": {
            "benefit": "Retry automatique et Dead Letter Queues",
            "poc_relevance": "Moyenne - Peut aider pour la robustesse",
            "complexity_added": "Moyenne - Configuration des policies"
        }
    }
    
    for benefit_name, details in rabbitmq_benefits.items():
        print(f"\n📊 {benefit_name.upper()}:")
        print(f"   Bénéfice: {details['benefit']}")
        print(f"   Pertinence POC: {details['poc_relevance']}")
        print(f"   Complexité ajoutée: {details['complexity_added']}")
    
    return rabbitmq_benefits

def check_rabbitmq_dependencies():
    """Vérifie l'état des dépendances RabbitMQ"""
    print("\n🔍 VÉRIFICATION DES DÉPENDANCES RABBITMQ")
    print("=" * 42)
    
    # Vérifier aio-pika
    try:
        import aio_pika
        print("   ✅ aio-pika installé")
        print(f"   📦 Version: {aio_pika.__version__}")
        aio_pika_available = True
    except ImportError:
        print("   ❌ aio-pika non disponible")
        aio_pika_available = False
    
    # Vérifier si RabbitMQ server est installé/accessible
    rabbitmq_server = False
    try:
        # Tenter de ping RabbitMQ sur le port par défaut
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('localhost', 5672))
        sock.close()
        
        if result == 0:
            print("   ✅ RabbitMQ server accessible sur localhost:5672")
            rabbitmq_server = True
        else:
            print("   ❌ RabbitMQ server non accessible sur localhost:5672")
    except Exception as e:
        print(f"   ❌ Erreur test RabbitMQ: {str(e)}")
    
    # Vérifier la complexité d'installation
    if not rabbitmq_server:
        print("\n   📋 INSTALLATION RABBITMQ REQUISE:")
        print("      1. Installer RabbitMQ Server")
        print("      2. Configurer les virtual hosts")
        print("      3. Configurer les utilisateurs/permissions")
        print("      4. Configurer les exchanges/queues")
        print("      5. Mettre en place le monitoring")
    
    return {
        "aio_pika_available": aio_pika_available,
        "rabbitmq_server_accessible": rabbitmq_server,
        "installation_required": not rabbitmq_server,
        "complexity_score": "Élevée" if not rabbitmq_server else "Moyenne"
    }

async def generate_recommendations():
    """Génère des recommandations basées sur l'analyse"""
    print("\n💡 ANALYSE ET RECOMMANDATIONS")
    print("=" * 35)
    
    # Simuler les charges de travail
    simulator = WorkloadSimulator()
    
    # Test workflow simple
    single_result = await simulator.simulate_current_workflow()
    print(f"📊 Workflow simple: {single_result['total_processing_time']:.2f}s")
    
    # Test charge concurrente
    concurrent_result = await simulator.simulate_concurrent_load(5)
    print(f"📊 Charge concurrente (5 req): {concurrent_result['total_time']:.2f}s")
    
    # Analyser l'architecture
    architecture = analyze_current_architecture()
    print(f"\n🏗️ ANALYSE DE L'ARCHITECTURE ACTUELLE{architecture}")
    print("=" * 45)

    # Évaluer RabbitMQ
    rabbitmq_benefits = evaluate_rabbitmq_benefits()
    dependencies = check_rabbitmq_dependencies()
    
    print(f"\n🎯 RECOMMANDATIONS FINALES: {rabbitmq_benefits}")
    print("-" * 25)
    
    # Calculer le score de pertinence RabbitMQ
    performance_score = 2 if single_result['total_processing_time'] > 10 else 1
    complexity_score = 3 if dependencies['installation_required'] else 1
    benefits_score = 2  # Moyenne des bénéfices pour POC
    
    total_score = performance_score + benefits_score - complexity_score
    
    if total_score <= 2:
        recommendation = "NON RECOMMANDÉ"
        reasoning = [
            "✅ Les performances actuelles (asyncio + httpx) sont suffisantes pour le POC",
            "✅ La complexité ajoutée n'est pas justifiée par les bénéfices",
            "✅ Le POC peut réussir sans RabbitMQ",
            "⚠️ Considérer RabbitMQ pour la version production si scaling requis"
        ]
    elif total_score <= 4:
        recommendation = "OPTIONNEL"
        reasoning = [
            "⚠️ RabbitMQ pourrait apporter des bénéfices mais n'est pas critique",
            "⚠️ Évaluer le temps disponible vs. bénéfices",
            "💡 Possible implémentation en fin de POC si temps disponible"
        ]
    else:
        recommendation = "RECOMMANDÉ"
        reasoning = [
            "🚀 Les bénéfices justifient la complexité",
            "🚀 Performances ou robustesse insuffisantes sans RabbitMQ",
            "🚀 Installation prioritaire recommandée"
        ]
    
    print(f"\n🏆 DÉCISION: {recommendation}")
    print(f"📊 Score d'évaluation: {total_score}/6")
    
    for reason in reasoning:
        print(f"   {reason}")
    
    # Actions concrètes
    print("\n📋 ACTIONS RECOMMANDÉES:")
    if recommendation == "NON RECOMMANDÉ":
        print("   1. 🗑️ Supprimer aio-pika de requirements.txt")
        print("   2. 📝 Documenter cette décision d'architecture")
        print("   3. 🔄 Continuer avec l'architecture asyncio actuelle")
        print("   4. 📈 Planifier RabbitMQ pour la version production si nécessaire")
    elif recommendation == "OPTIONNEL":
        print("   1. ⏸️ Reporter l'implémentation RabbitMQ")
        print("   2. 🎯 Se concentrer sur les fonctionnalités core du POC")
        print("   3. 📅 Réevaluer en fin de POC si temps disponible")
    else:
        print("   1. 🐰 Installer et configurer RabbitMQ Server")
        print("   2. 🔄 Implémenter les patterns async avec aio-pika")
        print("   3. 🧪 Migrer progressivement les workflows critiques")
    
    return {
        "recommendation": recommendation,
        "score": total_score,
        "performance_analysis": single_result,
        "concurrent_analysis": concurrent_result,
        "dependencies_status": dependencies,
        "reasoning": reasoning
    }

async def main():
    """Fonction principale d'évaluation"""
    print("🚀 ÉVALUATION DE LA NÉCESSITÉ DE RABBITMQ POUR LE POC NOVA")
    print("=" * 60)
    print(f"📅 Date d'évaluation: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    recommendations = await generate_recommendations()
    
    print(f"\n{'=' * 60}")
    print("📄 RAPPORT D'ÉVALUATION TERMINÉ")
    print("💡 Utilisez ces recommandations pour prendre votre décision d'architecture")
    print("🔄 Cette évaluation peut être refaite plus tard si les besoins évoluent")
    
    return recommendations

if __name__ == "__main__":
    asyncio.run(main())