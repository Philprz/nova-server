# tests/test_sap_verification.py
"""
Script de vérification que les clients et devis sont bien enregistrés dans SAP
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
        logging.FileHandler(f"logs/test_sap_verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("test_sap_verification")

class SAPVerificationTester:
    """Testeur de vérification des données dans SAP"""
    
    def __init__(self):
        self.test_results = []
        self.workflow = DevisWorkflow()
    
    async def run_complete_test(self):
        """Lance le test complet de vérification SAP"""
        logger.info("=== DÉBUT TEST DE VÉRIFICATION SAP ===")
        
        # Test avec le prompt réel
        test_prompt = "faire un devis pour 500 ref A00002 pour le client Edge Communications"
        
        try:
            # Étape 1: Exécuter le workflow complet
            logger.info(f"Étape 1: Exécution du workflow avec: '{test_prompt}'")
            workflow_result = await self.workflow.process_prompt(test_prompt)
            
            logger.info(f"Résultat workflow: {json.dumps(workflow_result, indent=2)}")
            
            if workflow_result.get("status") != "success":
                logger.error(f"❌ Workflow échoué: {workflow_result.get('message')}")
                return False
            
            # Étape 2: Vérifier le client dans SAP
            sap_card_code = workflow_result.get("client", {}).get("sap_card_code")
            if sap_card_code:
                await self.verify_client_in_sap(sap_card_code)
            else:
                logger.warning("⚠️ Pas de CardCode SAP dans le résultat")
            
            # Étape 3: Vérifier le devis dans SAP
            sap_doc_num = workflow_result.get("sap_doc_num")
            sap_doc_entry = workflow_result.get("sap_doc_entry")
            
            if sap_doc_num or sap_doc_entry:
                await self.verify_quotation_in_sap(sap_doc_num, sap_doc_entry)
            else:
                logger.warning("⚠️ Pas de référence devis SAP dans le résultat")
            
            # Étape 4: Lister tous les devis récents
            await self.list_recent_quotations()
            
            # Étape 5: Lister tous les clients récents
            await self.list_recent_clients()
            
            return True
            
        except Exception as e:
            logger.exception(f"Erreur lors du test: {str(e)}")
            return False
    
    async def verify_client_in_sap(self, card_code: str):
        """Vérifie qu'un client existe bien dans SAP"""
        logger.info(f"--- Vérification du client SAP: {card_code} ---")
        
        try:
            # Récupérer le client par CardCode
            client_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/BusinessPartners('{card_code}')",
                "method": "GET"
            })
            
            if "error" in client_result:
                logger.error(f"❌ Client {card_code} non trouvé dans SAP: {client_result['error']}")
                return False
            
            logger.info(f"✅ Client trouvé dans SAP:")
            logger.info(f"   - CardCode: {client_result.get('CardCode')}")
            logger.info(f"   - CardName: {client_result.get('CardName')}")
            logger.info(f"   - CardType: {client_result.get('CardType')}")
            logger.info(f"   - Adresse: {client_result.get('BillToStreet', '')} {client_result.get('BillToCity', '')}")
            logger.info(f"   - Téléphone: {client_result.get('Phone1', 'Non renseigné')}")
            logger.info(f"   - Créé le: {client_result.get('CreateDate', 'Date non disponible')}")
            
            return True
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification du client: {str(e)}")
            return False
    
    async def verify_quotation_in_sap(self, doc_num: str = None, doc_entry: int = None):
        """Vérifie qu'un devis existe bien dans SAP"""
        logger.info(f"--- Vérification du devis SAP: DocNum={doc_num}, DocEntry={doc_entry} ---")
        
        try:
            # Essayer de récupérer par DocEntry d'abord (plus fiable)
            if doc_entry:
                quotation_result = await MCPConnector.call_sap_mcp("sap_read", {
                    "endpoint": f"/Quotations({doc_entry})",
                    "method": "GET"
                })
            elif doc_num:
                # Rechercher par DocNum
                quotation_result = await MCPConnector.call_sap_mcp("sap_read", {
                    "endpoint": f"/Quotations?$filter=DocNum eq {doc_num}",
                    "method": "GET"
                })
                
                if "value" in quotation_result and quotation_result["value"]:
                    quotation_result = quotation_result["value"][0]
            else:
                logger.warning("Aucune référence de devis fournie")
                return False
            
            if "error" in quotation_result:
                logger.error(f"❌ Devis non trouvé dans SAP: {quotation_result['error']}")
                return False
            
            logger.info(f"✅ Devis trouvé dans SAP:")
            logger.info(f"   - DocEntry: {quotation_result.get('DocEntry')}")
            logger.info(f"   - DocNum: {quotation_result.get('DocNum')}")
            logger.info(f"   - CardCode: {quotation_result.get('CardCode')}")
            logger.info(f"   - DocDate: {quotation_result.get('DocDate')}")
            logger.info(f"   - DocTotal: {quotation_result.get('DocTotal')} {quotation_result.get('DocCurrency', 'EUR')}")
            logger.info(f"   - Statut: {quotation_result.get('DocumentStatus')}")
            logger.info(f"   - Commentaires: {quotation_result.get('Comments', 'Aucun')}")
            
            # Récupérer les lignes du devis
            await self.verify_quotation_lines(quotation_result.get('DocEntry'))
            
            return True
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification du devis: {str(e)}")
            return False
    
    async def verify_quotation_lines(self, doc_entry: int):
        """Vérifie les lignes d'un devis"""
        logger.info(f"--- Vérification des lignes du devis {doc_entry} ---")
        
        try:
            lines_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})/DocumentLines",
                "method": "GET"
            })
            
            if "error" in lines_result:
                logger.warning(f"Impossible de récupérer les lignes: {lines_result['error']}")
                return
            
            if "value" in lines_result:
                lines = lines_result["value"]
                logger.info(f"✅ {len(lines)} ligne(s) trouvée(s):")
                
                for i, line in enumerate(lines, 1):
                    logger.info(f"   Ligne {i}:")
                    logger.info(f"     - Article: {line.get('ItemCode')} - {line.get('ItemDescription', '')}")
                    logger.info(f"     - Quantité: {line.get('Quantity')}")
                    logger.info(f"     - Prix unitaire: {line.get('Price')}")
                    logger.info(f"     - Total ligne: {line.get('LineTotal')}")
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification des lignes: {str(e)}")
    
    async def list_recent_quotations(self):
        """Liste les devis récents dans SAP"""
        logger.info("--- Liste des devis récents ---")
        
        try:
            # Récupérer les 5 derniers devis
            recent_quotes = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": "/Quotations?$orderby=DocEntry desc&$top=5",
                "method": "GET"
            })
            
            if "error" in recent_quotes:
                logger.warning(f"Impossible de lister les devis: {recent_quotes['error']}")
                return
            
            if "value" in recent_quotes:
                quotes = recent_quotes["value"]
                logger.info(f"✅ {len(quotes)} devis récent(s) trouvé(s):")
                
                for quote in quotes:
                    logger.info(f"   - DocNum: {quote.get('DocNum')} | Client: {quote.get('CardCode')} | Total: {quote.get('DocTotal')} | Date: {quote.get('DocDate')}")
            
        except Exception as e:
            logger.exception(f"Erreur lors du listage des devis: {str(e)}")
    
    async def list_recent_clients(self):
        """Liste les clients récents dans SAP"""
        logger.info("--- Liste des clients récents ---")
        
        try:
            # Récupérer les 5 derniers clients
            recent_clients = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CreateDate desc&$top=5",
                "method": "GET"
            })
            
            if "error" in recent_clients:
                logger.warning(f"Impossible de lister les clients: {recent_clients['error']}")
                return
            
            if "value" in recent_clients:
                clients = recent_clients["value"]
                logger.info(f"✅ {len(clients)} client(s) récent(s) trouvé(s):")
                
                for client in clients:
                    logger.info(f"   - CardCode: {client.get('CardCode')} | Nom: {client.get('CardName')} | Créé: {client.get('CreateDate', 'Date inconnue')}")
            
        except Exception as e:
            logger.exception(f"Erreur lors du listage des clients: {str(e)}")
    
    async def test_specific_search(self):
        """Test de recherche spécifique"""
        logger.info("--- Test de recherche spécifique ---")
        
        # Rechercher Edge Communications
        try:
            edge_search = await MCPConnector.call_sap_mcp("sap_search", {
                "query": "Edge Communications",
                "entity_type": "BusinessPartners",
                "limit": 5
            })
            
            logger.info(f"Recherche 'Edge Communications': {edge_search}")
            
            # Rechercher le produit A00002
            product_search = await MCPConnector.call_sap_mcp("sap_search", {
                "query": "A00002",
                "entity_type": "Items",
                "limit": 5
            })
            
            logger.info(f"Recherche produit 'A00002': {product_search}")
            
        except Exception as e:
            logger.exception(f"Erreur lors des recherches: {str(e)}")

async def main():
    """Fonction principale"""
    tester = SAPVerificationTester()
    
    logger.info("🚀 Démarrage du test de vérification SAP")
    
    # Test principal
    success = await tester.run_complete_test()
    
    # Test de recherche spécifique
    await tester.test_specific_search()
    
    if success:
        logger.info("✅ Test de vérification terminé avec succès")
    else:
        logger.error("❌ Test de vérification échoué")
    
    logger.info("=== FIN DU TEST DE VÉRIFICATION SAP ===")

if __name__ == "__main__":
    asyncio.run(main())