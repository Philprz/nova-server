# tests/verify_created_documents.py
"""
Script de vérification des documents créés dans SAP et Salesforce
Vérifie l'existence et le contenu des devis/opportunités créés par le workflow
"""

import os
import sys
import asyncio
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional

# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.mcp_connector import MCPConnector

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f"logs/verification_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("verification")

class DocumentVerifier:
    """Vérificateur de documents créés dans SAP et Salesforce"""
    
    def __init__(self):
        self.verification_results = {
            "sap_quotation": None,
            "salesforce_opportunity": None,
            "data_consistency": None,
            "summary": None
        }
    
    async def verify_documents(self, sap_doc_num: str = None, sap_doc_entry: int = None, 
                             salesforce_opportunity_id: str = None) -> Dict[str, Any]:
        """
        Vérifie les documents dans les deux systèmes
        
        Args:
            sap_doc_num: Numéro de document SAP (ex: "367")
            sap_doc_entry: ID d'entrée SAP
            salesforce_opportunity_id: ID opportunité Salesforce
        """
        logger.info("=== DÉBUT DE LA VÉRIFICATION DES DOCUMENTS ===")
        
        try:
            # Vérification SAP
            if sap_doc_num or sap_doc_entry:
                sap_result = await self._verify_sap_quotation(sap_doc_num, sap_doc_entry)
                self.verification_results["sap_quotation"] = sap_result
            
            # Vérification Salesforce
            if salesforce_opportunity_id:
                sf_result = await self._verify_salesforce_opportunity(salesforce_opportunity_id)
                self.verification_results["salesforce_opportunity"] = sf_result
            
            # Vérification de la cohérence
            consistency_result = await self._verify_data_consistency()
            self.verification_results["data_consistency"] = consistency_result
            
            # Résumé
            summary = self._generate_summary()
            self.verification_results["summary"] = summary
            
            # Sauvegarder les résultats
            await self._save_results()
            
            logger.info("=== VÉRIFICATION TERMINÉE ===")
            return self.verification_results
            
        except Exception as e:
            logger.exception(f"Erreur lors de la vérification: {str(e)}")
            return {"error": str(e)}
    
    async def _verify_sap_quotation(self, doc_num: str = None, doc_entry: int = None) -> Dict[str, Any]:
        """Vérifie le devis SAP"""
        logger.info(f"--- Vérification devis SAP: DocNum={doc_num}, DocEntry={doc_entry} ---")
        
        try:
            # Construire la requête selon les paramètres disponibles
            if doc_entry:
                endpoint = f"/Quotations({doc_entry})"
            elif doc_num:
                endpoint = f"/Quotations?$filter=DocNum eq {doc_num}"
            else:
                return {"error": "Aucune référence SAP fournie"}
            
            # Récupérer le devis
            quotation_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": endpoint,
                "method": "GET"
            })
            
            if "error" in quotation_result:
                logger.error(f"❌ Devis SAP non trouvé: {quotation_result['error']}")
                return {"found": False, "error": quotation_result["error"]}
            
            # Traiter la réponse (peut être un objet direct ou un array)
            if "value" in quotation_result and quotation_result["value"]:
                quote_data = quotation_result["value"][0]
            else:
                quote_data = quotation_result
            
            logger.info(f"✅ Devis SAP trouvé:")
            logger.info(f"   - DocEntry: {quote_data.get('DocEntry')}")
            logger.info(f"   - DocNum: {quote_data.get('DocNum')}")
            logger.info(f"   - Client: {quote_data.get('CardCode')} - {quote_data.get('CardName', 'N/A')}")
            logger.info(f"   - Date: {quote_data.get('DocDate')}")
            logger.info(f"   - Total: {quote_data.get('DocTotal')} {quote_data.get('DocCurrency', 'EUR')}")
            logger.info(f"   - Statut: {quote_data.get('DocumentStatus')}")
            logger.info(f"   - Commentaires: {quote_data.get('Comments', 'Aucun')}")
            
            # Récupérer les lignes du devis
            lines_data = await self._get_sap_quotation_lines(quote_data.get('DocEntry'))
            
            result = {
                "found": True,
                "data": quote_data,
                "lines": lines_data,
                "summary": {
                    "doc_entry": quote_data.get('DocEntry'),
                    "doc_num": quote_data.get('DocNum'),
                    "card_code": quote_data.get('CardCode'),
                    "card_name": quote_data.get('CardName'),
                    "total_amount": quote_data.get('DocTotal'),
                    "currency": quote_data.get('DocCurrency', 'EUR'),
                    "status": quote_data.get('DocumentStatus'),
                    "date": quote_data.get('DocDate'),
                    "lines_count": len(lines_data) if lines_data else 0
                }
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur vérification devis SAP: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _get_sap_quotation_lines(self, doc_entry: int) -> list:
        """Récupère les lignes du devis SAP - VERSION CORRIGÉE"""
        if not doc_entry:
            return []
        
        try:
            logger.info(f"Récupération des lignes du devis SAP {doc_entry}")
            
            # CORRECTION: Les lignes sont déjà dans le devis principal !
            # Récupérer le devis complet d'abord
            quotation_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": f"/Quotations({doc_entry})",
                "method": "GET"
            })
            
            if "error" in quotation_result:
                logger.warning(f"Impossible de récupérer le devis SAP: {quotation_result['error']}")
                return []
            
            # CORRECTION: Extraire les lignes depuis DocumentLines
            if "DocumentLines" in quotation_result:
                lines = quotation_result["DocumentLines"]
                logger.info(f"✅ {len(lines)} ligne(s) de devis SAP récupérée(s)")
                
                for i, line in enumerate(lines, 1):
                    logger.info(f"   Ligne {i}:")
                    logger.info(f"     - Article: {line.get('ItemCode')} - {line.get('ItemDescription', '')}")
                    logger.info(f"     - Quantité: {line.get('Quantity')}")
                    logger.info(f"     - Prix unitaire: {line.get('Price')}")
                    logger.info(f"     - Total ligne: {line.get('LineTotal')}")
                    logger.info(f"     - TVA: {line.get('VatGroup')} ({line.get('TaxPercentagePerRow')}%)")
                
                return lines
            else:
                logger.warning("⚠️ Aucune ligne DocumentLines trouvée dans le devis")
                return []
            
        except Exception as e:
            logger.warning(f"Erreur récupération lignes SAP: {str(e)}")
            return []
    
    async def _verify_salesforce_opportunity(self, opportunity_id: str) -> Dict[str, Any]:
        """Vérifie l'opportunité Salesforce"""
        logger.info(f"--- Vérification opportunité Salesforce: {opportunity_id} ---")
        
        try:
            # Récupérer l'opportunité avec tous les détails
            opp_query = f"""
            SELECT Id, Name, Amount, StageName, CloseDate, AccountId, Account.Name, 
                   Description, LeadSource, Type, Probability, CreatedDate, LastModifiedDate
            FROM Opportunity 
            WHERE Id = '{opportunity_id}'
            """
            
            opp_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": opp_query
            })
            
            if "error" in opp_result or opp_result.get("totalSize", 0) == 0:
                logger.error(f"❌ Opportunité Salesforce non trouvée")
                return {"found": False, "error": "Opportunité non trouvée"}
            
            opp_data = opp_result["records"][0]
            
            logger.info(f"✅ Opportunité Salesforce trouvée:")
            logger.info(f"   - ID: {opp_data.get('Id')}")
            logger.info(f"   - Nom: {opp_data.get('Name')}")
            logger.info(f"   - Compte: {opp_data.get('Account', {}).get('Name', 'N/A')}")
            logger.info(f"   - Montant: {opp_data.get('Amount')}")
            logger.info(f"   - Étape: {opp_data.get('StageName')}")
            logger.info(f"   - Date fermeture: {opp_data.get('CloseDate')}")
            logger.info(f"   - Source: {opp_data.get('LeadSource')}")
            logger.info(f"   - Description: {opp_data.get('Description', 'Aucune')}")
            
            # Récupérer les lignes d'opportunité
            lines_data = await self._get_salesforce_opportunity_lines(opportunity_id)
            
            result = {
                "found": True,
                "data": opp_data,
                "lines": lines_data,
                "summary": {
                    "id": opp_data.get('Id'),
                    "name": opp_data.get('Name'),
                    "account_name": opp_data.get('Account', {}).get('Name'),
                    "amount": opp_data.get('Amount'),
                    "stage": opp_data.get('StageName'),
                    "close_date": opp_data.get('CloseDate'),
                    "lead_source": opp_data.get('LeadSource'),
                    "created_date": opp_data.get('CreatedDate'),
                    "lines_count": len(lines_data) if lines_data else 0
                }
            }
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur vérification opportunité Salesforce: {str(e)}")
            return {"found": False, "error": str(e)}
    
    async def _get_salesforce_opportunity_lines(self, opportunity_id: str) -> list:
        """Récupère les lignes de l'opportunité Salesforce"""
        try:
            logger.info(f"Récupération des lignes de l'opportunité Salesforce {opportunity_id}")
            
            lines_query = f"""
            SELECT Id, Quantity, UnitPrice, TotalPrice, Description,
                   PricebookEntry.Product2.Name, PricebookEntry.Product2.ProductCode
            FROM OpportunityLineItem 
            WHERE OpportunityId = '{opportunity_id}'
            """
            
            lines_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": lines_query
            })
            
            if "error" in lines_result:
                logger.warning(f"Impossible de récupérer les lignes Salesforce: {lines_result['error']}")
                return []
            
            if lines_result.get("totalSize", 0) > 0:
                lines = lines_result["records"]
                logger.info(f"✅ {len(lines)} ligne(s) d'opportunité Salesforce récupérée(s)")
                
                for i, line in enumerate(lines, 1):
                    product_name = line.get("PricebookEntry", {}).get("Product2", {}).get("Name", "N/A")
                    product_code = line.get("PricebookEntry", {}).get("Product2", {}).get("ProductCode", "N/A")
                    logger.info(f"   Ligne {i}:")
                    logger.info(f"     - Produit: {product_code} - {product_name}")
                    logger.info(f"     - Quantité: {line.get('Quantity')}")
                    logger.info(f"     - Prix unitaire: {line.get('UnitPrice')}")
                    logger.info(f"     - Total ligne: {line.get('TotalPrice')}")
                    logger.info(f"     - Description: {line.get('Description', 'Aucune')}")
                
                return lines
            else:
                logger.warning("⚠️ Aucune ligne d'opportunité trouvée")
                return []
            
        except Exception as e:
            logger.warning(f"Erreur récupération lignes Salesforce: {str(e)}")
            return []
    
    async def _verify_data_consistency(self) -> Dict[str, Any]:
        """Vérifie la cohérence des données entre SAP et Salesforce - VERSION CORRIGÉE"""
        logger.info("--- Vérification de la cohérence des données ---")
        
        try:
            sap_data = self.verification_results.get("sap_quotation")
            sf_data = self.verification_results.get("salesforce_opportunity")
            
            if not sap_data or not sap_data.get("found"):
                return {"consistent": False, "error": "Données SAP manquantes"}
            
            if not sf_data or not sf_data.get("found"):
                return {"consistent": False, "error": "Données Salesforce manquantes"}
            
            # CORRECTION: Comparer les montants HT (sans TVA)
            sap_total_ttc = float(sap_data["summary"]["total_amount"] or 0)
            sap_vat = float(sap_data["data"].get("VatSum", 0))
            sap_total_ht = sap_total_ttc - sap_vat  # Montant HT SAP
            
            sf_total = float(sf_data["summary"]["amount"] or 0)  # Salesforce stocke en HT
            
            # Comparer le nombre de lignes (corrigé)
            sap_lines_count = len(sap_data.get("lines", []))  # Utiliser les lignes réelles
            sf_lines_count = sf_data["summary"]["lines_count"]
            
            # Tolérance pour les arrondis
            amount_consistent = abs(sap_total_ht - sf_total) < 0.01
            lines_consistent = sap_lines_count == sf_lines_count
            
            logger.info(f"Comparaison des données (CORRIGÉE):")
            logger.info(f"  - Montant SAP TTC: {sap_total_ttc} EUR")
            logger.info(f"  - TVA SAP: {sap_vat} EUR")
            logger.info(f"  - Montant SAP HT: {sap_total_ht} EUR")
            logger.info(f"  - Montant Salesforce HT: {sf_total}")
            logger.info(f"  - Cohérence montant: {'✅' if amount_consistent else '❌'}")
            logger.info(f"  - Lignes SAP: {sap_lines_count}")
            logger.info(f"  - Lignes Salesforce: {sf_lines_count}")
            logger.info(f"  - Cohérence lignes: {'✅' if lines_consistent else '❌'}")
            
            overall_consistent = amount_consistent and lines_consistent
            
            result = {
                "consistent": overall_consistent,
                "amount_consistent": amount_consistent,
                "lines_consistent": lines_consistent,
                "comparison": {
                    "sap_amount_ttc": sap_total_ttc,
                    "sap_amount_ht": sap_total_ht,
                    "sap_vat": sap_vat,
                    "sf_amount": sf_total,
                    "amount_difference_ht": abs(sap_total_ht - sf_total),
                    "sap_lines": sap_lines_count,
                    "sf_lines": sf_lines_count
                }
            }
            
            if overall_consistent:
                logger.info("✅ Les données sont parfaitement cohérentes entre SAP et Salesforce")
            else:
                logger.warning("⚠️ Incohérences détectées entre SAP et Salesforce")
            
            return result
            
        except Exception as e:
            logger.exception(f"Erreur vérification cohérence: {str(e)}")
            return {"consistent": False, "error": str(e)}
    
    def _generate_summary(self) -> Dict[str, Any]:
        """Génère un résumé de la vérification"""
        logger.info("--- Génération du résumé ---")
        
        sap_data = self.verification_results.get("sap_quotation")
        sf_data = self.verification_results.get("salesforce_opportunity")
        consistency_data = self.verification_results.get("data_consistency")
        
        summary = {
            "verification_date": datetime.now().isoformat(),
            "sap_document": {
                "found": sap_data.get("found", False) if sap_data else False,
                "doc_num": sap_data.get("summary", {}).get("doc_num") if sap_data and sap_data.get("found") else None,
                "amount": sap_data.get("summary", {}).get("total_amount") if sap_data and sap_data.get("found") else None
            },
            "salesforce_document": {
                "found": sf_data.get("found", False) if sf_data else False,
                "opportunity_id": sf_data.get("summary", {}).get("id") if sf_data and sf_data.get("found") else None,
                "amount": sf_data.get("summary", {}).get("amount") if sf_data and sf_data.get("found") else None
            },
            "data_consistency": {
                "consistent": consistency_data.get("consistent", False) if consistency_data else False,
                "details": consistency_data.get("comparison") if consistency_data else None
            },
            "overall_status": "SUCCESS" if (
                sap_data and sap_data.get("found") and
                sf_data and sf_data.get("found") and
                consistency_data and consistency_data.get("consistent")
            ) else "PARTIAL" if (
                sap_data and sap_data.get("found") or
                sf_data and sf_data.get("found")
            ) else "FAILED"
        }
        
        logger.info(f"📊 Résumé de la vérification:")
        logger.info(f"   - Document SAP: {'✅' if summary['sap_document']['found'] else '❌'}")
        logger.info(f"   - Document Salesforce: {'✅' if summary['salesforce_document']['found'] else '❌'}")
        logger.info(f"   - Cohérence: {'✅' if summary['data_consistency']['consistent'] else '❌'}")
        logger.info(f"   - Statut global: {summary['overall_status']}")
        
        return summary
    
    async def _save_results(self):
        """Sauvegarde les résultats dans un fichier JSON"""
        try:
            filename = f"verification_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.verification_results, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"📁 Résultats sauvegardés dans: {filename}")
            
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder les résultats: {str(e)}")

# Fonction principale pour utilisation directe
async def verify_latest_documents():
    """Vérifie les derniers documents créés en lisant le fichier de résultat du workflow"""
    try:
        # Chercher le dernier fichier de résultat du workflow
        import glob
        result_files = glob.glob("test_result_*.json")
        
        if not result_files:
            logger.error("❌ Aucun fichier de résultat de workflow trouvé")
            return
        
        latest_file = max(result_files, key=os.path.getctime)
        logger.info(f"📁 Lecture du fichier de résultat: {latest_file}")
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            workflow_result = json.load(f)
        
        # Extraire les IDs des documents
        sap_doc_num = workflow_result.get("sap_doc_num")
        sap_doc_entry = workflow_result.get("sap_doc_entry")
        salesforce_opportunity_id = workflow_result.get("salesforce_quote_id")
        
        logger.info(f"Documents à vérifier:")
        logger.info(f"  - SAP DocNum: {sap_doc_num}")
        logger.info(f"  - SAP DocEntry: {sap_doc_entry}")
        logger.info(f"  - Salesforce Opportunity: {salesforce_opportunity_id}")
        
        # Lancer la vérification
        verifier = DocumentVerifier()
        results = await verifier.verify_documents(
            sap_doc_num=sap_doc_num,
            sap_doc_entry=sap_doc_entry,
            salesforce_opportunity_id=salesforce_opportunity_id
        )
        
        return results
        
    except Exception as e:
        logger.exception(f"Erreur lors de la vérification automatique: {str(e)}")
        return {"error": str(e)}

# Fonction pour vérification manuelle avec IDs spécifiques
async def verify_specific_documents(sap_doc_num: str = None, sap_doc_entry: int = None, 
                                  salesforce_opportunity_id: str = None):
    """Vérifie des documents spécifiques avec les IDs fournis"""
    verifier = DocumentVerifier()
    return await verifier.verify_documents(sap_doc_num, sap_doc_entry, salesforce_opportunity_id)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Vérification des documents SAP et Salesforce")
    parser.add_argument("--sap-doc-num", help="Numéro de document SAP")
    parser.add_argument("--sap-doc-entry", type=int, help="ID d'entrée SAP")
    parser.add_argument("--sf-opportunity-id", help="ID opportunité Salesforce")
    parser.add_argument("--auto", action="store_true", help="Vérification automatique des derniers documents")
    
    args = parser.parse_args()
    
    if args.auto:
        logger.info("🚀 Vérification automatique des derniers documents créés")
        results = asyncio.run(verify_latest_documents())
    else:
        logger.info("🚀 Vérification manuelle des documents spécifiés")
        results = asyncio.run(verify_specific_documents(
            sap_doc_num=args.sap_doc_num,
            sap_doc_entry=args.sap_doc_entry,
            salesforce_opportunity_id=args.sf_opportunity_id
        ))
    
    if results and "error" not in results:
        summary = results.get("summary", {})
        print(f"\n🎯 RÉSULTAT FINAL: {summary.get('overall_status', 'INCONNU')}")
        
        if summary.get('overall_status') == 'SUCCESS':
            print("✅ Tous les documents ont été créés avec succès et sont cohérents !")
        elif summary.get('overall_status') == 'PARTIAL':
            print("⚠️ Certains documents ont été créés mais il y a des incohérences")
        else:
            print("❌ Échec de la vérification")
    else:
        print(f"❌ Erreur lors de la vérification: {results.get('error', 'Erreur inconnue')}")