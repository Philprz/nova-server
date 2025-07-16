#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Exemple d'utilisation complète de l'agent de recherche d'entreprises dans NOVA
Cas d'usage : Création d'un devis avec enrichissement automatique du client
"""

import asyncio
import json
from datetime import datetime
from typing import Dict, Any

# Imports NOVA
from services.company_search_service import company_search_service
from workflow.devis_workflow import DevisWorkflow
from services.llm_extractor import LLMExtractor

class ExempleUtilisationAgent:
    """
    Exemple d'utilisation complète de l'agent de recherche d'entreprises
    intégré dans le workflow NOVA
    """
    
    def __init__(self):
        self.workflow = DevisWorkflow()
        self.llm_extractor = LLMExtractor()
    
    async def scenario_creation_devis_avec_enrichissement(self):
        """
        Scénario complet : Création d'un devis avec enrichissement automatique
        """
        print("🎯 SCÉNARIO : Création de devis avec enrichissement automatique")
        print("=" * 60)
        
        # 1. Prompt utilisateur (simulation)
        user_prompt = "faire un devis pour 100 ref A00001 pour Total"
        print(f"📝 Prompt utilisateur : {user_prompt}")
        
        # 2. Extraction LLM
        extraction_result = await self.llm_extractor.extract_devis_info(user_prompt)
        print(f"🤖 Extraction LLM : {extraction_result}")
        
        # 3. Enrichissement du client avec l'agent de recherche
        client_name = extraction_result.get('client_name', 'Total')
        print(f"\n🔍 Recherche entreprise : {client_name}")
        
        # Recherche détaillée
        search_result = await company_search_service.search_company(client_name)
        
        if search_result['success'] and search_result['companies']:
            company_info = search_result['companies'][0]
            print(f"✅ Entreprise trouvée :")
            print(f"   - Nom : {company_info['denomination']}")
            print(f"   - SIREN : {company_info['siren']}")
            print(f"   - Activité : {company_info['activite_principale']}")
            print(f"   - Statut : {company_info['etat_administratif']}")
            print(f"   - Source : {company_info['source']}")
            
            # Enrichissement des données client
            enriched_client_data = {
                'company_name': company_info['denomination'],
                'siren': company_info['siren'],
                'industry': company_info['activite_principale'],
                'legal_form': company_info['forme_juridique'],
                'status': company_info['etat_administratif'],
                'enriched_by_agent': True,
                'enriched_at': datetime.now().isoformat()
            }
            
        else:
            print("❌ Entreprise non trouvée")
            # Suggestions
            suggestions = await company_search_service.get_suggestions(client_name)
            print(f"💡 Suggestions : {suggestions}")
            
            # Données client de base
            enriched_client_data = {
                'company_name': client_name,
                'enriched_by_agent': False,
                'suggestions': suggestions
            }
        
        # 4. Validation SIREN si disponible
        if 'siren' in enriched_client_data:
            siren = enriched_client_data['siren']
            validation_result = await company_search_service.validate_siren(siren)
            print(f"\n✅ Validation SIREN {siren} : {validation_result['valid']}")
        
        # 5. Création du devis avec données enrichies
        devis_data = {
            'client_data': enriched_client_data,
            'products': extraction_result.get('products', []),
            'prompt': user_prompt,
            'enriched_workflow': True
        }
        
        print(f"\n💰 Données devis enrichies :")
        print(json.dumps(devis_data, indent=2, ensure_ascii=False))
        
        return devis_data
    
    async def scenario_recherche_multiple_entreprises(self):
        """
        Scénario : Recherche et comparaison de plusieurs entreprises
        """
        print("\n🎯 SCÉNARIO : Recherche multiple d'entreprises")
        print("=" * 60)
        
        # Liste d'entreprises à rechercher
        companies_to_search = [
            "Total",
            "Société Générale", 
            "Orange",
            "Rondot Group",
            "Entreprise Inexistante"
        ]
        
        results = []
        
        for company_name in companies_to_search:
            print(f"\n🔍 Recherche : {company_name}")
            
            # Recherche
            search_result = await company_search_service.search_company(
                company_name, 
                max_results=3
            )
            
            if search_result['success'] and search_result['companies']:
                company = search_result['companies'][0]
                print(f"✅ Trouvé : {company['denomination']} ({company['siren']})")
                results.append({
                    'query': company_name,
                    'found': True,
                    'company': company
                })
            else:
                print(f"❌ Non trouvé")
                # Suggestions
                suggestions = await company_search_service.get_suggestions(company_name)
                print(f"💡 Suggestions : {suggestions}")
                results.append({
                    'query': company_name,
                    'found': False,
                    'suggestions': suggestions
                })
        
        # Export des résultats
        found_companies = [r['company'] for r in results if r['found']]
        if found_companies:
            export_filename = await company_search_service.export_search_results(
                found_companies, 
                'json'
            )
            print(f"\n📁 Résultats exportés : {export_filename}")
        
        return results
    
    async def scenario_enrichissement_liste_clients(self):
        """
        Scénario : Enrichissement d'une liste de clients existants
        """
        print("\n🎯 SCÉNARIO : Enrichissement liste de clients")
        print("=" * 60)
        
        # Simulation d'une liste de clients existants
        clients_existants = [
            {
                'id': 1,
                'company_name': 'Total',
                'email': 'contact@total.com',
                'phone': '01 23 45 67 89'
            },
            {
                'id': 2,
                'company_name': 'Société Générale',
                'email': 'info@societegenerale.com'
            },
            {
                'id': 3,
                'company_name': 'Rondot Group',
                'email': 'contact@rondotgroup.com'
            }
        ]
        
        enriched_clients = []
        
        for client in clients_existants:
            print(f"\n🔍 Enrichissement client {client['id']} : {client['company_name']}")
            
            # Enrichissement via l'agent
            enriched_data = await company_search_service.enrich_client_data(client)
            
            if 'enriched_data' in enriched_data:
                enrichment_info = enriched_data['enriched_data']
                print(f"✅ Enrichi avec SIREN : {enrichment_info.get('siren')}")
                print(f"   - Dénomination officielle : {enrichment_info.get('denomination_officielle')}")
                print(f"   - Activité : {enrichment_info.get('activite_principale')}")
                print(f"   - Source : {enrichment_info.get('source')}")
            else:
                print(f"❌ Enrichissement impossible")
            
            enriched_clients.append(enriched_data)
        
        # Statistiques d'enrichissement
        enriched_count = sum(1 for c in enriched_clients if 'enriched_data' in c)
        print(f"\n📊 Statistiques d'enrichissement :")
        print(f"   - Total clients : {len(clients_existants)}")
        print(f"   - Clients enrichis : {enriched_count}")
        print(f"   - Taux d'enrichissement : {(enriched_count/len(clients_existants))*100:.1f}%")
        
        return enriched_clients
    
    async def scenario_validation_siren_bulk(self):
        """
        Scénario : Validation en masse de numéros SIREN
        """
        print("\n🎯 SCÉNARIO : Validation en masse SIREN")
        print("=" * 60)
        
        # Liste de SIREN à valider
        sirens_to_validate = [
            "542051180",    # Total (valide)
            "552120222",    # Société Générale (valide)
            "775665019",    # Orange (valide)
            "123456789",    # Invalide
            "987654321",    # Invalide
            "ABC123456",    # Invalide (format)
        ]
        
        validation_results = []
        
        for siren in sirens_to_validate:
            print(f"\n🔍 Validation SIREN : {siren}")
            
            # Validation
            validation_result = await company_search_service.validate_siren(siren)
            
            if validation_result['valid']:
                print(f"✅ SIREN valide")
                
                # Récupération des informations entreprise
                company_info = await company_search_service.get_company_by_siren(siren)
                if company_info['success']:
                    print(f"   - Entreprise : {company_info['company']['denomination']}")
                    print(f"   - Statut : {company_info['company']['etat_administratif']}")
            else:
                print(f"❌ SIREN invalide")
            
            validation_results.append({
                'siren': siren,
                'valid': validation_result['valid'],
                'company_info': company_info if validation_result['valid'] else None
            })
        
        # Statistiques de validation
        valid_count = sum(1 for r in validation_results if r['valid'])
        print(f"\n📊 Statistiques de validation :")
        print(f"   - Total SIREN testés : {len(sirens_to_validate)}")
        print(f"   - SIREN valides : {valid_count}")
        print(f"   - Taux de validité : {(valid_count/len(sirens_to_validate))*100:.1f}%")
        
        return validation_results
    
    async def scenario_monitoring_performance(self):
        """
        Scénario : Monitoring des performances de l'agent
        """
        print("\n🎯 SCÉNARIO : Monitoring des performances")
        print("=" * 60)
        
        # Statistiques du cache
        cache_stats = await company_search_service.get_cache_stats()
        print(f"📊 Statistiques du cache :")
        print(f"   - Total entrées : {cache_stats.get('total_entries', 0)}")
        print(f"   - Entrées INSEE : {cache_stats.get('insee_entries', 0)}")
        print(f"   - Entrées Pappers : {cache_stats.get('pappers_entries', 0)}")
        print(f"   - Entreprises locales : {cache_stats.get('local_companies', 0)}")
        print(f"   - Taille index : {cache_stats.get('search_index_size', 0)}")
        
        # Test de performance
        import time
        
        print(f"\n⏱️  Test de performance (10 recherches) :")
        start_time = time.time()
        
        test_queries = ["Total", "Orange", "Société Générale", "Bouygues", "Renault"] * 2
        
        for query in test_queries:
            result = await company_search_service.search_company(query, max_results=1)
        
        end_time = time.time()
        duration = end_time - start_time
        
        print(f"   - Durée totale : {duration:.2f}s")
        print(f"   - Temps moyen par recherche : {duration/len(test_queries):.2f}s")
        
        return {
            'cache_stats': cache_stats,
            'performance_test': {
                'queries': len(test_queries),
                'duration': duration,
                'avg_time': duration/len(test_queries)
            }
        }


async def main():
    """
    Fonction principale - Exécution de tous les scénarios
    """
    print("🚀 EXEMPLES D'UTILISATION - AGENT DE RECHERCHE D'ENTREPRISES NOVA")
    print("=" * 80)
    
    exemple = ExempleUtilisationAgent()
    
    # Exécution des scénarios
    scenarios = [
        exemple.scenario_creation_devis_avec_enrichissement,
        exemple.scenario_recherche_multiple_entreprises,
        exemple.scenario_enrichissement_liste_clients,
        exemple.scenario_validation_siren_bulk,
        exemple.scenario_monitoring_performance
    ]
    
    for scenario in scenarios:
        try:
            await scenario()
            print("\n" + "="*80)
        except Exception as e:
            print(f"❌ Erreur dans le scénario {scenario.__name__}: {e}")
    
    print("\n🎉 TOUS LES SCÉNARIOS TERMINÉS!")
    print("✅ L'agent de recherche d'entreprises est opérationnel dans NOVA.")


if __name__ == "__main__":
    # Exécution des exemples
    asyncio.run(main())
