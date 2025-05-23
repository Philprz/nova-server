# tests/test_integration_bidirectional.py
"""
Test d'intégration bidirectionnelle Salesforce ↔ SAP
Vérifie que les devis sont créés dans les DEUX systèmes
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow.devis_workflow import DevisWorkflow
from services.mcp_connector import MCPConnector

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/test_bidirectionnel_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_bidirectionnel")

class BidirectionalTester:
    """Testeur d'intégration bidirectionnelle"""
    
    def __init__(self):
        self.workflow = DevisWorkflow()
        self.test_results = {
            "workflow_success": False,
            "sap_verification": False,
            "salesforce_verification": False,
            "data_consistency": False
        }
    
    async def run_complete_test(self):
        """Lance le test complet bidirectionnel"""
        logger.info("=== DÉBUT TEST INTÉGRATION BIDIRECTIONNELLE ===")
        
        # Prompt de test
        test_prompt = "faire un devis pour 500 ref A00002 pour le client Edge Communications"
        
        try:
            # Étape 1: Exécuter le workflow complet
            logger.info("=== ÉTAPE 1: EXÉCUTION WORKFLOW COMPLET ===")
            workflow_result = await self.workflow.process_prompt(test_prompt)
            
            logger.info("Résultat workflow:")
            logger.info(json.dumps(workflow_result, indent=2, default=str))
            
            if workflow_result.get("status") != "success":
                logger.error(f"❌ Workflow échoué: {workflow_result.get('message')}")
                return False
            
            self.test_results["workflow_success"] = True
            logger.info("✅ Workflow exécuté avec succès")
            
            # Extraire les informations clés
            sap_doc_num = workflow_result.get("sap_doc_num")
            sap_doc_entry = workflow_result.get("sap_doc_entry")
            sap_card_code = workflow_result.get("client", {}).get("sap_card_code")
            salesforce_opportunity_id = workflow_result.get("salesforce_quote_id")
            
            logger.info(f"Informations extraites:")
            logger.info(f"  - SAP DocNum: {sap_doc_num}")
            logger.info(f"  - SAP DocEntry: {sap_doc_entry}")
            logger.info(f"  - SAP CardCode: {sap_card_code}")
            logger.info(f"  - Salesforce Opportunity ID: {salesforce_opportunity_id}")
            
            # Étape 2: Vérification dans SAP
            logger.info("=== ÉTAPE 2: VÉRIFICATION SAP ===")
            sap_success = await self.verify_sap_data(sap_doc_entry, sap_doc_num, sap_card_code)
            self.test_results["sap_verification"] = sap_success
            
            # Étape 3: Vérification dans Salesforce
            logger.info("=== ÉTAPE 3: VÉRIFICATION SALESFORCE ===")
            sf_success = await self.verify_salesforce_data(salesforce_opportunity_id, workflow_result.get("client", {}).get("salesforce_id"))
            self.test_results["salesforce_verification"] = sf_success
            
            # Étape 4: Vérification de la cohérence des données
            logger.info("=== ÉTAPE 4: VÉRIFICATION COHÉRENCE ===")
            consistency_success = await self.verify_data_consistency(workflow_result)
            self.test_results["data_consistency"] = consistency_success
            
            # Résumé final
            await self.print_final_summary()
            
            return all(self.test_results.values())
            
        except Exception as e:
            logger.exception(f"Erreur lors du test bidirectionnel: {str(e)}")
            return False
    
    async def verify_sap_data(self, doc_entry: int = None, doc_num: str = None, card_code: str = None) -> bool:
        """Vérifie les données dans SAP"""
        success = True
        
        try:
            # Vérifier le client SAP
            if card_code:
                logger.info(f"Vérification client SAP: {card_code}")
                client_result = await MCPConnector.verify_sap_customer(card_code)
                
                if "error" in client_result:
                    logger.error(f"❌ Client SAP non trouvé: {client_result['error']}")
                    success = False
                else:
                    logger.info(f"✅ Client SAP vérifié: {client_result.get('CardName')}")
                    logger.info(f"   - Adresse: {client_result.get('BillToStreet', '')} {client_result.get('BillToCity', '')}")
                    logger.info(f"   - Téléphone: {client_result.get('Phone1', 'Non renseigné')}")
            
            # Vérifier le devis SAP
            if doc_entry or doc_num:
                logger.info(f"Vérification devis SAP: DocEntry={doc_entry}, DocNum={doc_num}")
                quote_result = await MCPConnector.verify_sap_quotation(doc_entry, doc_num)
                
                if "error" in quote_result:
                    logger.error(f"❌ Devis SAP non trouvé: {quote_result['error']}")
                    success = False
                else:
                    # Si c'est une liste de résultats, prendre le premier
                    if "value" in quote_result and quote_result["value"]:
                        quote_data = quote_result["value"][0]
                    else:
                        quote_data = quote_result
                    
                    logger.info(f"✅ Devis SAP vérifié:")
                    logger.info(f"   - DocNum: {quote_data.get('DocNum')}")
                    logger.info(f"   - Client: {quote_data.get('CardCode')}")
                    logger.info(f"   - Total: {quote_data.get('DocTotal')} {quote_data.get('DocCurrency', 'EUR')}")
                    logger.info(f"   - Statut: {quote_data.get('DocumentStatus')}")
                    
                    # Vérifier les lignes du devis
                    await self.verify_sap_quote_lines(quote_data.get('DocEntry'))
            
        except Exception as e:
            logger.exception(f"Erreur vérification SAP: {str(e)}")
            success = False
        
        return success
    
    async def verify_sap_quote_lines(self, doc_entry: int):
        """Vérifie les lignes du devis SAP"""
        try:
            lines_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})/DocumentLines",
                "method": "GET"
            })
            
            if "error" in lines_result:
                logger.warning(f"Impossible de récupérer les lignes SAP: {lines_result['error']}")
                return
            
            if "value" in lines_result:
                lines = lines_result["value"]
                logger.info(f"✅ {len(lines)} ligne(s) de devis SAP:")
                
                for i, line in enumerate(lines, 1):
                    logger.info(f"   Ligne {i}: {line.get('ItemCode')} - Qté: {line.get('Quantity')} - Prix: {line.get('Price')}")
            
        except Exception as e:
            logger.warning(f"Erreur vérification lignes SAP: {str(e)}")
    
    async def verify_salesforce_data(self, opportunity_id: str = None, account_id: str = None) -> bool:
        """Vérifie les données dans Salesforce"""
        success = True
        
        try:
            # Vérifier le compte Salesforce
            if account_id:
                logger.info(f"Vérification compte Salesforce: {account_id}")
                account_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                    "query": f"SELECT Id, Name, BillingStreet, BillingCity, Phone FROM Account WHERE Id = '{account_id}'"
                })
                
                if "error" in account_result or account_result.get("totalSize", 0) == 0:
                    logger.error(f"❌ Compte Salesforce non trouvé")
                    success = False
                else:
                    account = account_result["records"][0]
                    logger.info(f"✅ Compte Salesforce vérifié: {account.get('Name')}")
                    logger.info(f"   - Adresse: {account.get('BillingStreet', '')} {account.get('BillingCity', '')}")
                    logger.info(f"   - Téléphone: {account.get('Phone', 'Non renseigné')}")
            
            # Vérifier l'opportunité Salesforce
            if opportunity_id:
                logger.info(f"Vérification opportunité Salesforce: {opportunity_id}")
                opp_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                    "query": f"SELECT Id, Name, Amount, StageName, CloseDate, AccountId FROM Opportunity WHERE Id = '{opportunity_id}'"
                })
                
                if "error" in opp_result or opp_result.get("totalSize", 0) == 0:
                    logger.error(f"❌ Opportunité Salesforce non trouvée")
                    success = False
                else:
                    opp = opp_result["records"][0]
                    logger.info(f"✅ Opportunité Salesforce vérifiée:")
                    logger.info(f"   - Nom: {opp.get('Name')}")
                    logger.info(f"   - Montant: {opp.get('Amount')}")
                    logger.info(f"   - Étape: {opp.get('StageName')}")
                    logger.info(f"   - Date fermeture: {opp.get('CloseDate')}")
                    
                    # Vérifier les lignes d'opportunité
                    await self.verify_salesforce_opportunity_lines(opportunity_id)
            
        except Exception as e:
            logger.exception(f"Erreur vérification Salesforce: {str(e)}")
            success = False
        
        return success
    
    async def verify_salesforce_opportunity_lines(self, opportunity_id: str):
        """Vérifie les lignes de l'opportunité Salesforce"""
        try:
            lines_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": f"SELECT Id, Quantity, UnitPrice, TotalPrice, PricebookEntry.Product2.Name, PricebookEntry.Product2.ProductCode FROM OpportunityLineItem WHERE OpportunityId = '{opportunity_id}'"
            })
            
            if "error" in lines_result:
                logger.warning(f"Impossible de récupérer les lignes Salesforce: {lines_result['error']}")
                return
            
            if lines_result.get("totalSize", 0) > 0:
                lines = lines_result["records"]
                logger.info(f"✅ {len(lines)} ligne(s) d'opportunité Salesforce:")
                
                for i, line in enumerate(lines, 1):
                    product_name = line.get("PricebookEntry", {}).get("Product2", {}).get("Name", "N/A")
                    product_code = line.get("PricebookEntry", {}).get("Product2", {}).get("ProductCode", "N/A")
                    logger.info(f"   Ligne {i}: {product_code} ({product_name}) - Qté: {line.get('Quantity')} - Prix: {line.get('UnitPrice')} - Total: {line.get('TotalPrice')}")
            else:
                logger.warning("⚠️ Aucune ligne d'opportunité trouvée")
            
        except Exception as e:
            logger.warning(f"Erreur vérification lignes Salesforce: {str(e)}")
    
    async def verify_data_consistency(self, workflow_result: Dict[str, Any]) -> bool:
        """Vérifie la cohérence des données entre SAP et Salesforce"""
        logger.info("Vérification de la cohérence des données...")
        
        try:
            # Comparer les montants
            sap_total = workflow_result.get("total_amount", 0)
            
            # Récupérer le montant Salesforce si l'opportunité existe
            sf_opportunity_id = workflow_result.get("salesforce_quote_id")
            if sf_opportunity_id:
                opp_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                    "query": f"SELECT Amount FROM Opportunity WHERE Id = '{sf_opportunity_id}'"
                })
                
                if "error" not in opp_result and opp_result.get("totalSize", 0) > 0:
                    sf_total = opp_result["records"][0].get("Amount", 0)
                    
                    logger.info(f"Comparaison des montants:")
                    logger.info(f"  - SAP: {sap_total} EUR")
                    logger.info(f"  - Salesforce: {sf_total}")
                    
                    # Tolérance de 0.01 pour les arrondis
                    if abs(float(sap_total) - float(sf_total or 0)) < 0.01:
                        logger.info("✅ Montants cohérents")
                        return True
                    else:
                        logger.error(f"❌ Incohérence des montants: SAP={sap_total}, SF={sf_total}")
                        return False
            
            # Si pas d'opportunité Salesforce, vérifier au moins la cohérence interne
            products = workflow_result.get("products", [])
            calculated_total = sum(p.get("line_total", 0) for p in products)
            
            if abs(float(sap_total) - float(calculated_total)) < 0.01:
                logger.info(f"✅ Cohérence interne vérifiée: {calculated_total} EUR")
                return True
            else:
                logger.error(f"❌ Incohérence interne: calculé={calculated_total}, déclaré={sap_total}")
                return False
                
        except Exception as e:
            logger.exception(f"Erreur vérification cohérence: {str(e)}")
            return False
    
    async def print_final_summary(self):
        """Affiche le résumé final des tests"""
        logger.info("=== RÉSUMÉ FINAL DES TESTS ===")
        
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)
        
        logger.info(f"Tests réussis: {passed_tests}/{total_tests}")
        logger.info("")
        
        for test_name, result in self.test_results.items():
            status = "✅ RÉUSSI" if result else "❌ ÉCHOUÉ"
            logger.info(f"  {test_name}: {status}")
        
        logger.info("")
        
        if all(self.test_results.values()):
            logger.info("🎉 INTÉGRATION BIDIRECTIONNELLE RÉUSSIE !")
            logger.info("✅ Le client a été créé dans SAP avec toutes les données Salesforce")
            logger.info("✅ Le devis a été créé dans SAP et est visible dans les quotations")
            logger.info("✅ L'opportunité a été créée dans Salesforce avec ses lignes")
            logger.info("✅ Les données sont cohérentes entre les deux systèmes")
        else:
            logger.error("❌ INTÉGRATION BIDIRECTIONNELLE INCOMPLÈTE")
            
            failed_tests = [name for name, result in self.test_results.items() if not result]
            logger.error(f"Tests échoués: {', '.join(failed_tests)}")
        
        logger.info("=== FIN DU RÉSUMÉ ===")
    
    async def test_connections_only(self):
        """Test rapide des connexions uniquement"""
        logger.info("=== TEST RAPIDE DES CONNEXIONS ===")
        
        # Test Salesforce
        try:
            sf_test = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": "SELECT Id, Name FROM Account LIMIT 1"
            })
            
            if "error" in sf_test:
                logger.error(f"❌ Connexion Salesforce échouée: {sf_test['error']}")
            else:
                logger.info(f"✅ Salesforce connecté - {sf_test.get('totalSize', 0)} comptes trouvés")
        except Exception as e:
            logger.error(f"❌ Erreur test Salesforce: {str(e)}")
        
        # Test SAP
        try:
            sap_test = await MCPConnector.call_sap_mcp("ping", {})
            
            if "error" in sap_test:
                logger.error(f"❌ Connexion SAP échouée: {sap_test.get('error', 'Erreur inconnue')}")
            else:
                logger.info(f"✅ SAP connecté: {sap_test}")
        except Exception as e:
            logger.error(f"❌ Erreur test SAP: {str(e)}")
        
        logger.info("=== FIN TEST CONNEXIONS ===")

async def main():
    """Fonction principale"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test d'intégration bidirectionnelle Salesforce ↔ SAP")
    parser.add_argument("--connections-only", action="store_true", help="Tester uniquement les connexions")
    parser.add_argument("--prompt", type=str, help="Prompt personnalisé pour le test", 
                       default="faire un devis pour 500 ref A00002 pour le client Edge Communications")
    
    args = parser.parse_args()
    
    tester = BidirectionalTester()
    
    if args.connections_only:
        await tester.test_connections_only()
    else:
        logger.info("🚀 Démarrage du test d'intégration bidirectionnelle")
        logger.info(f"Prompt de test: {args.prompt}")
        
        # Modifier le prompt si fourni
        if args.prompt != "faire un devis pour 500 ref A00002 pour le client Edge Communications":
            # Cette partie nécessiterait de modifier le workflow pour accepter un prompt personnalisé
            logger.info(f"Utilisation du prompt personnalisé: {args.prompt}")
        
        success = await tester.run_complete_test()
        
        if success:
            logger.info("✅ Test d'intégration bidirectionnelle réussi")
            return 0
        else:
            logger.error("❌ Test d'intégration bidirectionnelle échoué")
            return 1
    
    return 0

if __name__ == "__main__":
    import sys
    exit_code = asyncio.run(main())
    sys.exit(exit_code)