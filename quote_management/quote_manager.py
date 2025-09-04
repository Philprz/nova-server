"""
Gestionnaire de devis SAP/Salesforce
Permet de lister, comparer et supprimer des devis dans les deux systèmes
"""

import asyncio
import sys
import os
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
import logging
from dataclasses import dataclass
from enum import Enum

# Ajouter le répertoire parent au path pour importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class QuoteStatus(Enum):
    """Statuts possibles pour un devis"""
    SYNCED = "synced"  # Présent dans les deux systèmes
    ONLY_SAP = "only_sap"  # Uniquement dans SAP
    ONLY_SALESFORCE = "only_salesforce"  # Uniquement dans Salesforce
    MISMATCH = "mismatch"  # Différences entre les deux systèmes


@dataclass
class Quote:
    """Représentation d'un devis"""
    doc_num: Optional[str] = None  # Numéro SAP
    doc_entry: Optional[str] = None  # ID SAP
    opportunity_id: Optional[str] = None  # ID Salesforce
    client_name: str = ""
    client_code: str = ""
    doc_date: Optional[datetime] = None
    total: float = 0.0
    status: QuoteStatus = QuoteStatus.SYNCED
    sap_data: Optional[Dict] = None
    salesforce_data: Optional[Dict] = None
    differences: List[str] = None


class QuoteManager:
    """Gestionnaire principal pour les devis SAP/Salesforce"""
    
    def __init__(self):
        self.mcp_connector = MCPConnector()
        self.quotes_cache = {}
        
    async def get_sap_quotes(self, days_back: int = 30) -> List[Dict]:
        """Récupère les devis SAP des X derniers jours"""
        try:
            # Calculer la date de début
            date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            
            # Construire le filtre OData pour récupérer tous les devis
            filter_string = f"DocDate ge '{date_from}'"
            
            logger.info(f"🔍 Récupération des devis SAP depuis {date_from}")
            
            # Appel direct à l'API SAP
            response = await self.mcp_connector.call_mcp("sap_mcp", "sap_read", {
                "endpoint": f"/Quotations?$filter={filter_string}&$orderby=DocDate desc&$top=500"
            })
            
            if response and response.get("success"):
                quotes = response.get("data", {}).get("value", [])
                logger.info(f"✅ {len(quotes)} devis SAP trouvés")
                return quotes
            else:
                logger.error(f"❌ Erreur récupération devis SAP: {response}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des devis SAP: {e}")
            return []
    
    async def get_salesforce_opportunities(self, days_back: int = 30) -> List[Dict]:
        """Récupère les opportunités Salesforce des X derniers jours"""
        try:
            # Calculer la date de début
            date_from = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            
            logger.info(f"🔍 Récupération des opportunités Salesforce depuis {date_from}")
            
            # Requête SOQL pour récupérer les opportunités
            query = f"""
                SELECT Id, Name, StageName, Amount, CloseDate, 
                       Account.Name, Account.SAP_Code__c, OpportunityNumber__c,
                       SAP_Quote_Number__c, CreatedDate
                FROM Opportunity 
                WHERE CreatedDate >= {date_from}T00:00:00Z
                ORDER BY CreatedDate DESC
                LIMIT 500
            """
            
            response = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_query", {
                "query": query
            })
            
            if response and response.get("success"):
                opportunities = response.get("records", [])
                logger.info(f"✅ {len(opportunities)} opportunités Salesforce trouvées")
                return opportunities
            else:
                logger.error(f"❌ Erreur récupération opportunités Salesforce: {response}")
                return []
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la récupération des opportunités Salesforce: {e}")
            return []
    
    async def compare_quotes(self, sap_quotes: List[Dict], sf_opportunities: List[Dict]) -> List[Quote]:
        """Compare les devis SAP et les opportunités Salesforce"""
        quotes = []
        processed_sap = set()
        processed_sf = set()
        
        # Créer un index des opportunités SF par numéro de devis SAP
        sf_by_sap_num = {}
        for opp in sf_opportunities:
            sap_num = opp.get("SAP_Quote_Number__c")
            if sap_num:
                sf_by_sap_num[sap_num] = opp
        
        # Traiter les devis SAP
        for sap_quote in sap_quotes:
            doc_num = str(sap_quote.get("DocNum", ""))
            doc_entry = str(sap_quote.get("DocEntry", ""))
            
            quote = Quote(
                doc_num=doc_num,
                doc_entry=doc_entry,
                client_name=sap_quote.get("CardName", ""),
                client_code=sap_quote.get("CardCode", ""),
                doc_date=self._parse_date(sap_quote.get("DocDate")),
                total=float(sap_quote.get("DocTotal", 0)),
                sap_data=sap_quote
            )
            
            # Chercher l'opportunité correspondante
            if doc_num in sf_by_sap_num:
                sf_opp = sf_by_sap_num[doc_num]
                quote.opportunity_id = sf_opp.get("Id")
                quote.salesforce_data = sf_opp
                quote.status = QuoteStatus.SYNCED
                
                # Vérifier les différences
                differences = self._check_differences(sap_quote, sf_opp)
                if differences:
                    quote.status = QuoteStatus.MISMATCH
                    quote.differences = differences
                
                processed_sf.add(sf_opp.get("Id"))
            else:
                quote.status = QuoteStatus.ONLY_SAP
            
            quotes.append(quote)
            processed_sap.add(doc_num)
        
        # Traiter les opportunités SF non liées
        for sf_opp in sf_opportunities:
            if sf_opp.get("Id") not in processed_sf:
                quote = Quote(
                    opportunity_id=sf_opp.get("Id"),
                    client_name=sf_opp.get("Account", {}).get("Name", "") if sf_opp.get("Account") else "",
                    client_code=sf_opp.get("Account", {}).get("SAP_Code__c", "") if sf_opp.get("Account") else "",
                    doc_date=self._parse_date(sf_opp.get("CloseDate")),
                    total=float(sf_opp.get("Amount", 0)) if sf_opp.get("Amount") else 0.0,
                    status=QuoteStatus.ONLY_SALESFORCE,
                    salesforce_data=sf_opp
                )
                quotes.append(quote)
        
        return quotes
    
    def _parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse une date depuis différents formats"""
        if not date_str:
            return None
            
        for fmt in ["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%fZ"]:
            try:
                return datetime.strptime(date_str.split("T")[0], "%Y-%m-%d")
            except:
                continue
        return None
    
    def _check_differences(self, sap_quote: Dict, sf_opp: Dict) -> List[str]:
        """Vérifie les différences entre un devis SAP et une opportunité SF"""
        differences = []
        
        # Comparer les montants
        sap_total = float(sap_quote.get("DocTotal", 0))
        sf_amount = float(sf_opp.get("Amount", 0)) if sf_opp.get("Amount") else 0.0
        
        if abs(sap_total - sf_amount) > 0.01:
            differences.append(f"Montant différent: SAP={sap_total:.2f}€ vs SF={sf_amount:.2f}€")
        
        # Comparer les codes clients
        sap_client = sap_quote.get("CardCode", "")
        sf_client = sf_opp.get("Account", {}).get("SAP_Code__c", "") if sf_opp.get("Account") else ""
        
        if sap_client != sf_client:
            differences.append(f"Code client différent: SAP={sap_client} vs SF={sf_client}")
        
        return differences
    
    async def delete_sap_quote(self, doc_entry: str) -> Dict[str, any]:
        """Supprime un devis dans SAP"""
        try:
            logger.info(f"🗑️ Suppression du devis SAP DocEntry={doc_entry}")
            
            # Dans SAP B1, on ne peut pas vraiment supprimer un devis, on doit l'annuler
            # On va le marquer comme annulé
            result = await self.mcp_connector.call_mcp("sap_mcp", "sap_read", {
                "endpoint": f"/Quotations({doc_entry})/Cancel",
                "method": "POST",
                "payload": {}
            })
            
            if result and result.get("success"):
                logger.info(f"✅ Devis SAP {doc_entry} annulé avec succès")
                return {"success": True, "message": "Devis SAP annulé"}
            else:
                logger.error(f"❌ Erreur annulation devis SAP: {result}")
                return {"success": False, "error": result.get("error", "Erreur inconnue")}
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'annulation du devis SAP: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_salesforce_opportunity(self, opportunity_id: str) -> Dict[str, any]:
        """Supprime une opportunité dans Salesforce"""
        try:
            logger.info(f"🗑️ Suppression de l'opportunité Salesforce {opportunity_id}")
            
            # Supprimer l'opportunité via l'API REST
            result = await self.mcp_connector.call_mcp("salesforce_mcp", "salesforce_delete_record", {
                "sobject": "Opportunity",
                "record_id": opportunity_id
            })
            
            if result and result.get("success"):
                logger.info(f"✅ Opportunité Salesforce {opportunity_id} supprimée avec succès")
                return {"success": True, "message": "Opportunité Salesforce supprimée"}
            else:
                logger.error(f"❌ Erreur suppression opportunité Salesforce: {result}")
                return {"success": False, "error": result.get("error", "Erreur inconnue")}
                
        except Exception as e:
            logger.error(f"❌ Erreur lors de la suppression de l'opportunité Salesforce: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_quotes_batch(self, quote_ids: List[Dict[str, str]]) -> Dict[str, any]:
        """Supprime un lot de devis dans SAP et/ou Salesforce"""
        results = {
            "success": True,
            "deleted": {"sap": 0, "salesforce": 0},
            "errors": []
        }
        
        for quote_info in quote_ids:
            # Supprimer dans SAP si nécessaire
            if quote_info.get("sap_doc_entry"):
                result = await self.delete_sap_quote(quote_info["sap_doc_entry"])
                if result["success"]:
                    results["deleted"]["sap"] += 1
                else:
                    results["errors"].append(f"SAP {quote_info['sap_doc_entry']}: {result['error']}")
                    results["success"] = False
            
            # Supprimer dans Salesforce si nécessaire
            if quote_info.get("sf_opportunity_id"):
                result = await self.delete_salesforce_opportunity(quote_info["sf_opportunity_id"])
                if result["success"]:
                    results["deleted"]["salesforce"] += 1
                else:
                    results["errors"].append(f"SF {quote_info['sf_opportunity_id']}: {result['error']}")
                    results["success"] = False
        
        return results


# Fonction principale pour tester
async def main():
    """Fonction de test du gestionnaire de devis"""
    manager = QuoteManager()
    
    # Récupérer les devis des deux systèmes
    logger.info("📊 Début de la synchronisation des devis...")
    
    sap_quotes = await manager.get_sap_quotes(days_back=30)
    sf_opportunities = await manager.get_salesforce_opportunities(days_back=30)
    
    # Comparer les devis
    all_quotes = await manager.compare_quotes(sap_quotes, sf_opportunities)
    
    # Afficher les résultats
    logger.info(f"\n📈 Résumé de la comparaison:")
    logger.info(f"  - Total devis: {len(all_quotes)}")
    logger.info(f"  - Synchronisés: {len([q for q in all_quotes if q.status == QuoteStatus.SYNCED])}")
    logger.info(f"  - Uniquement SAP: {len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SAP])}")
    logger.info(f"  - Uniquement Salesforce: {len([q for q in all_quotes if q.status == QuoteStatus.ONLY_SALESFORCE])}")
    logger.info(f"  - Avec différences: {len([q for q in all_quotes if q.status == QuoteStatus.MISMATCH])}")


if __name__ == "__main__":
    asyncio.run(main())