# services/field_analyzer.py
"""
Analyseur de champs pour identifier les patterns et champs obligatoires
dans Salesforce et SAP pour la création de clients
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Any
from collections import Counter
from mcp_connector import MCPConnector
from services.security_helpers import safe_int
# Ajouter le répertoire racine au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configuration des logs
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(f'logs/field_analyzer_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('field_analyzer')



class FieldAnalyzer:
    """Analyseur de champs pour Salesforce et SAP"""
    
    def __init__(self):
        self.analysis_results = {
            "salesforce": {
                "metadata": None,
                "sample_analysis": None,
                "field_patterns": None
            },
            "sap": {
                "metadata": None,
                "sample_analysis": None,
                "field_patterns": None
            },
            "mapping_suggestions": None,
            "creation_requirements": None,
            "timestamp": datetime.now().isoformat()
        }
    
    async def analyze_all(self, sample_size: int = 50) -> Dict[str, Any]:
        """
        Lance l'analyse complète des deux systèmes
        
        Args:
            sample_size: Nombre d'enregistrements à analyser par système
        """
        logger.info("=== DÉBUT DE L'ANALYSE DES CHAMPS ===")
        logger.info(f"Taille d'échantillon: {sample_size} enregistrements par système")
        
        try:
            # Analyse Salesforce
            logger.info("--- Analyse Salesforce ---")
            sf_analysis = await self._analyze_salesforce(sample_size)
            self.analysis_results["salesforce"] = sf_analysis
            
            # Analyse SAP
            logger.info("--- Analyse SAP ---")
            sap_analysis = await self._analyze_sap(sample_size)
            self.analysis_results["sap"] = sap_analysis
            
            # Génération des suggestions de mapping
            logger.info("--- Génération des suggestions de mapping ---")
            mapping_suggestions = self._generate_mapping_suggestions()
            self.analysis_results["mapping_suggestions"] = mapping_suggestions
            
            # Génération des exigences de création
            logger.info("--- Génération des exigences de création ---")
            creation_requirements = self._generate_creation_requirements()
            self.analysis_results["creation_requirements"] = creation_requirements
            
            # Sauvegarde des résultats
            await self._save_analysis_results()
            
            # Génération du rapport
            self._generate_summary_report()
            
            logger.info("=== ANALYSE TERMINÉE ===")
            return self.analysis_results
            
        except Exception as e:
            logger.exception(f"Erreur lors de l'analyse: {str(e)}")
            return {"error": str(e)}
    
    async def _analyze_salesforce(self, sample_size: int) -> Dict[str, Any]:
        """Analyse les comptes Salesforce"""
        logger.info("Analyse des comptes Salesforce...")
        
        try:
            # 1. Récupérer les métadonnées des comptes
            logger.info("Récupération des métadonnées Account...")
            metadata_result = await MCPConnector.call_salesforce_mcp("salesforce_inspect", {
                "object_name": "Account"
            })
            
            if "error" in metadata_result:
                logger.error(f"Erreur métadonnées Salesforce: {metadata_result['error']}")
                return {"error": metadata_result["error"]}
            
            # 2. Récupérer un échantillon de comptes
            logger.info(f"Récupération d'un échantillon de {sample_size} comptes...")
            
            # Construire la requête avec tous les champs importants
            important_fields = [
                "Id", "Name", "AccountNumber", "Type", "Industry", "AnnualRevenue", 
                "NumberOfEmployees", "Phone", "Fax", "Website", "Description",
                "BillingStreet", "BillingCity", "BillingState", "BillingPostalCode", "BillingCountry",
                "ShippingStreet", "ShippingCity", "ShippingState", "ShippingPostalCode", "ShippingCountry",
                "ParentId", "OwnerId", "Rating", "SicDesc", "TickerSymbol", "AccountSource",
                "CreatedDate", "LastModifiedDate"
            ]
            
            safe_fields = ", ".join(f for f in important_fields if f.isidentifier())
            query = f"SELECT {safe_fields} FROM Account ORDER BY CreatedDate DESC LIMIT {safe_int(sample_size, default=5, max_value=50)}"
            
            sample_result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
                "query": query
            })
            
            if "error" in sample_result:
                logger.error(f"Erreur échantillon Salesforce: {sample_result['error']}")
                return {"error": sample_result["error"]}
            
            # 3. Analyser l'échantillon
            sample_accounts = sample_result.get("records", [])
            logger.info(f"Analyse de {len(sample_accounts)} comptes Salesforce...")
            
            field_analysis = self._analyze_field_patterns(sample_accounts, "Salesforce")
            
            return {
                "metadata": metadata_result,
                "sample_size": len(sample_accounts),
                "sample_analysis": field_analysis,
                "field_patterns": self._extract_salesforce_patterns(sample_accounts)
            }
            
        except Exception as e:
            logger.exception(f"Erreur analyse Salesforce: {str(e)}")
            return {"error": str(e)}
    
    async def _analyze_sap(self, sample_size: int) -> Dict[str, Any]:
        """Analyse les clients SAP (Business Partners)"""
        logger.info("Analyse des clients SAP...")
        
        try:
            # 1. Récupérer un échantillon de clients SAP
            logger.info(f"Récupération d'un échantillon de {sample_size} clients SAP...")
            
            # Requête pour récupérer les Business Partners de type Customer
            endpoint = f"/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CreateDate desc&$top={sample_size}"
            
            sample_result = await MCPConnector.call_sap_mcp("sap_read", {
                "endpoint": endpoint,
                "method": "GET"
            })
            
            if "error" in sample_result:
                logger.error(f"Erreur échantillon SAP: {sample_result['error']}")
                return {"error": sample_result["error"]}
            
            # 2. Analyser l'échantillon
            sample_customers = sample_result.get("value", [])
            logger.info(f"Analyse de {len(sample_customers)} clients SAP...")
            
            if not sample_customers:
                logger.warning("Aucun client SAP trouvé dans l'échantillon")
                return {"error": "Aucun client SAP trouvé"}
            
            field_analysis = self._analyze_field_patterns(sample_customers, "SAP")
            
            # 3. Analyser la structure des champs SAP
            sap_patterns = self._extract_sap_patterns(sample_customers)
            
            return {
                "sample_size": len(sample_customers),
                "sample_analysis": field_analysis,
                "field_patterns": sap_patterns,
                "metadata": {
                    "analyzed_fields": list(sample_customers[0].keys()) if sample_customers else [],
                    "total_fields": len(sample_customers[0].keys()) if sample_customers else 0
                }
            }
            
        except Exception as e:
            logger.exception(f"Erreur analyse SAP: {str(e)}")
            return {"error": str(e)}
    
    def _analyze_field_patterns(self, records: List[Dict], system_name: str) -> Dict[str, Any]:
        """Analyse les patterns dans les champs d'un échantillon d'enregistrements"""
        if not records:
            return {"error": "Aucun enregistrement à analyser"}
        
        total_records = len(records)
        field_stats = {}
        
        # Analyser chaque champ
        for field_name in records[0].keys():
            values = []
            non_null_count = 0
            empty_string_count = 0
            unique_values = set()
            
            for record in records:
                value = record.get(field_name)
                values.append(value)
                
                if value is not None:
                    non_null_count += 1
                    if isinstance(value, str):
                        if value.strip() == "":
                            empty_string_count += 1
                        else:
                            unique_values.add(value)
                    else:
                        unique_values.add(str(value))
            
            # Calculer les statistiques
            fill_rate = (non_null_count / total_records) * 100
            non_empty_rate = ((non_null_count - empty_string_count) / total_records) * 100 if non_null_count > 0 else 0
            uniqueness_rate = (len(unique_values) / non_null_count) * 100 if non_null_count > 0 else 0
            
            field_stats[field_name] = {
                "fill_rate": fill_rate,
                "non_empty_rate": non_empty_rate,
                "uniqueness_rate": uniqueness_rate,
                "total_records": total_records,
                "non_null_count": non_null_count,
                "unique_values_count": len(unique_values),
                "sample_values": list(unique_values)[:5],  # 5 premiers exemples
                "is_likely_required": fill_rate >= 95.0,
                "is_business_critical": non_empty_rate >= 80.0
            }
        
        # Identifier les champs probablement obligatoires
        required_fields = [field for field, stats in field_stats.items() if stats["is_likely_required"]]
        business_critical_fields = [field for field, stats in field_stats.items() if stats["is_business_critical"]]
        
        logger.info(f"Analyse {system_name} - {total_records} enregistrements:")
        logger.info(f"  - Champs probablement obligatoires: {len(required_fields)}")
        logger.info(f"  - Champs critiques métier: {len(business_critical_fields)}")
        
        return {
            "total_records": total_records,
            "field_statistics": field_stats,
            "required_fields": required_fields,
            "business_critical_fields": business_critical_fields,
            "total_fields_analyzed": len(field_stats)
        }
    
    def _extract_salesforce_patterns(self, accounts: List[Dict]) -> Dict[str, Any]:
        """Extrait les patterns spécifiques à Salesforce"""
        patterns = {
            "address_patterns": {
                "billing_complete": 0,
                "shipping_complete": 0,
                "both_addresses": 0
            },
            "industry_distribution": Counter(),
            "type_distribution": Counter(),
            "common_field_combinations": [],
            "data_quality_indicators": {}
        }
        
        for account in accounts:
            # Analyse des adresses
            billing_complete = all([
                account.get("BillingStreet"), 
                account.get("BillingCity"), 
                account.get("BillingCountry")
            ])
            shipping_complete = all([
                account.get("ShippingStreet"), 
                account.get("ShippingCity"), 
                account.get("ShippingCountry")
            ])
            
            if billing_complete:
                patterns["address_patterns"]["billing_complete"] += 1
            if shipping_complete:
                patterns["address_patterns"]["shipping_complete"] += 1
            if billing_complete and shipping_complete:
                patterns["address_patterns"]["both_addresses"] += 1
            
            # Distribution des industries et types
            if account.get("Industry"):
                patterns["industry_distribution"][account["Industry"]] += 1
            if account.get("Type"):
                patterns["type_distribution"][account["Type"]] += 1
        
        return patterns
    
    def _extract_sap_patterns(self, customers: List[Dict]) -> Dict[str, Any]:
        """Extrait les patterns spécifiques à SAP"""
        patterns = {
            "card_type_distribution": Counter(),
            "group_code_distribution": Counter(),
            "currency_distribution": Counter(),
            "address_patterns": {
                "bill_to_complete": 0,
                "ship_to_complete": 0,
                "both_addresses": 0
            },
            "common_prefixes": Counter(),
            "data_quality_indicators": {}
        }
        
        for customer in customers:
            # Distribution des types de carte
            if customer.get("CardType"):
                patterns["card_type_distribution"][customer["CardType"]] += 1
            
            # Distribution des groupes
            if customer.get("GroupCode"):
                patterns["group_code_distribution"][customer["GroupCode"]] += 1
            
            # Distribution des devises
            if customer.get("Currency"):
                patterns["currency_distribution"][customer["Currency"]] += 1
            
            # Analyse des adresses SAP
            bill_to_complete = all([
                customer.get("BillToStreet"), 
                customer.get("BillToCity"), 
                customer.get("BillToCountry")
            ])
            ship_to_complete = all([
                customer.get("ShipToStreet"), 
                customer.get("ShipToCity"), 
                customer.get("ShipToCountry")
            ])
            
            if bill_to_complete:
                patterns["address_patterns"]["bill_to_complete"] += 1
            if ship_to_complete:
                patterns["address_patterns"]["ship_to_complete"] += 1
            if bill_to_complete and ship_to_complete:
                patterns["address_patterns"]["both_addresses"] += 1
            
            # Analyse des préfixes de CardCode
            card_code = customer.get("CardCode", "")
            if len(card_code) >= 2:
                prefix = card_code[:2]
                patterns["common_prefixes"][prefix] += 1
        
        return patterns
    
    def _generate_mapping_suggestions(self) -> Dict[str, Any]:
        """Génère des suggestions de mapping entre Salesforce et SAP"""
        logger.info("Génération des suggestions de mapping...")
        
        # Mapping basé sur l'analyse des noms de champs et des patterns
        field_mappings = {
            # Informations de base
            "Name": "CardName",
            "AccountNumber": "CardCode",
            "Phone": "Phone1",
            "Fax": "Fax",
            "Website": "Website",
            
            # Adresse de facturation
            "BillingStreet": "BillToStreet",
            "BillingCity": "BillToCity",
            "BillingState": "BillToState",
            "BillingPostalCode": "BillToZipCode",
            "BillingCountry": "BillToCountry",
            
            # Adresse de livraison
            "ShippingStreet": "ShipToStreet",
            "ShippingCity": "ShipToCity",
            "ShippingState": "ShipToState",
            "ShippingPostalCode": "ShipToZipCode",
            "ShippingCountry": "ShipToCountry",
            
            # Informations métier
            "Industry": "Industry",
            "Description": "Notes",
            "AnnualRevenue": "DunningTerm",  # Approximation
            
            # Champs calculés/constants pour SAP
            "CONSTANTS": {
                "CardType": "cCustomer",
                "GroupCode": 100,  # Groupe par défaut
                "Currency": "EUR",
                "Valid": "tYES",
                "Frozen": "tNO"
            }
        }
        
        # Génération des règles de transformation
        transformation_rules = {
            "CardCode": {
                "source": "Name",
                "transformation": "generate_from_name",
                "description": "Générer un CardCode unique basé sur le nom"
            },
            "GroupCode": {
                "source": "Type",
                "transformation": "map_type_to_group",
                "description": "Mapper le type Salesforce vers un groupe SAP"
            }
        }
        
        return {
            "field_mappings": field_mappings,
            "transformation_rules": transformation_rules,
            "confidence_level": "high",
            "validation_needed": [
                "Vérifier les codes de groupe SAP disponibles",
                "Valider les codes de devise acceptés",
                "Confirmer les formats d'adresse"
            ]
        }
    
    def _generate_creation_requirements(self) -> Dict[str, Any]:
        """Génère les exigences pour la création de clients"""
        logger.info("Génération des exigences de création...")
        
        sf_analysis = self.analysis_results.get("salesforce", {}).get("sample_analysis", {})
        sap_analysis = self.analysis_results.get("sap", {}).get("sample_analysis", {})
        
        requirements = {
            "salesforce": {
                "absolutely_required": [],
                "business_required": [],
                "optional": []
            },
            "sap": {
                "absolutely_required": [],
                "business_required": [],
                "optional": []
            },
            "workflow_requirements": {},
            "validation_rules": {}
        }
        
        # Analyser les exigences Salesforce
        if sf_analysis and "field_statistics" in sf_analysis:
            for field, stats in sf_analysis["field_statistics"].items():
                if stats["is_likely_required"]:
                    requirements["salesforce"]["absolutely_required"].append(field)
                elif stats["is_business_critical"]:
                    requirements["salesforce"]["business_required"].append(field)
                else:
                    requirements["salesforce"]["optional"].append(field)
        
        # Analyser les exigences SAP
        if sap_analysis and "field_statistics" in sap_analysis:
            for field, stats in sap_analysis["field_statistics"].items():
                if stats["is_likely_required"]:
                    requirements["sap"]["absolutely_required"].append(field)
                elif stats["is_business_critical"]:
                    requirements["sap"]["business_required"].append(field)
                else:
                    requirements["sap"]["optional"].append(field)
        
        # Définir les exigences du workflow
        requirements["workflow_requirements"] = {
            "minimum_required_from_user": [
                "company_name",
                "contact_info",  # phone ou email
                "primary_address"
            ],
            "auto_generated": [
                "account_number",
                "creation_date",
                "default_settings"
            ],
            "optional_from_user": [
                "industry",
                "annual_revenue",
                "description",
                "shipping_address"
            ]
        }
        
        # Règles de validation
        requirements["validation_rules"] = {
            "company_name": {
                "min_length": 2,
                "max_length": 100,
                "pattern": "^[a-zA-Z0-9\\s\\-\\.&]+$"
            },
            "phone": {
                "pattern": "^[+]?[0-9\\s\\-\\.\\(\\)]+$",
                "min_length": 8
            },
            "email": {
                "pattern": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
            },
            "postal_code": {
                "pattern": "^[0-9]{5}$|^[0-9]{5}-[0-9]{4}$"
            }
        }
        
        return requirements
    
    async def _save_analysis_results(self):
        """Sauvegarde les résultats d'analyse"""
        try:
            filename = f"field_analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(self.analysis_results, f, indent=2, ensure_ascii=False, default=str)
            
            logger.info(f"📁 Résultats d'analyse sauvegardés: {filename}")
            
        except Exception as e:
            logger.warning(f"Impossible de sauvegarder les résultats: {str(e)}")
    
    def _generate_summary_report(self):
        """Génère un rapport de synthèse lisible"""
        logger.info("\n" + "="*80)
        logger.info("📊 RAPPORT DE SYNTHÈSE - ANALYSE DES CHAMPS")
        logger.info("="*80)
        
        # Résumé Salesforce
        sf_analysis = self.analysis_results.get("salesforce", {}).get("sample_analysis", {})
        if sf_analysis:
            logger.info(f"\n🔷 SALESFORCE - {sf_analysis.get('total_records', 0)} comptes analysés")
            logger.info(f"   Champs obligatoires identifiés: {len(sf_analysis.get('required_fields', []))}")
            logger.info(f"   Champs critiques métier: {len(sf_analysis.get('business_critical_fields', []))}")
            
            if sf_analysis.get('required_fields'):
                logger.info(f"   → Obligatoires: {', '.join(sf_analysis['required_fields'][:5])}...")
        
        # Résumé SAP
        sap_analysis = self.analysis_results.get("sap", {}).get("sample_analysis", {})
        if sap_analysis:
            logger.info(f"\n🔶 SAP - {sap_analysis.get('total_records', 0)} clients analysés")
            logger.info(f"   Champs obligatoires identifiés: {len(sap_analysis.get('required_fields', []))}")
            logger.info(f"   Champs critiques métier: {len(sap_analysis.get('business_critical_fields', []))}")
            
            if sap_analysis.get('required_fields'):
                logger.info(f"   → Obligatoires: {', '.join(sap_analysis['required_fields'][:5])}...")
        
        # Résumé du mapping
        mapping = self.analysis_results.get("mapping_suggestions", {})
        if mapping:
            logger.info("\n🔄 MAPPING IDENTIFIÉ")
            logger.info(f"   Correspondances directes: {len(mapping.get('field_mappings', {}))}")
            logger.info(f"   Transformations nécessaires: {len(mapping.get('transformation_rules', {}))}")
        
        # Recommandations
        requirements = self.analysis_results.get("creation_requirements", {})
        if requirements:
            logger.info("\n✅ RECOMMANDATIONS")
            workflow_req = requirements.get("workflow_requirements", {})
            if workflow_req:
                min_required = workflow_req.get("minimum_required_from_user", [])
                logger.info(f"   Minimum requis de l'utilisateur: {', '.join(min_required)}")
        
        logger.info("\n" + "="*80)
        logger.info("📋 PROCHAINES ÉTAPES RECOMMANDÉES:")
        logger.info("   1. Valider les mappings identifiés")
        logger.info("   2. Implémenter le workflow de création client")
        logger.info("   3. Créer les règles de validation")
        logger.info("   4. Tester avec des données réelles")
        logger.info("="*80)

# Fonctions utilitaires pour usage direct
async def analyze_customer_fields(sample_size: int = 50):
    """Lance l'analyse complète des champs clients"""
    analyzer = FieldAnalyzer()
    return await analyzer.analyze_all(sample_size)

async def quick_analysis(sample_size: int = 10):
    """Lance une analyse rapide avec un petit échantillon"""
    logger.info("🚀 Analyse rapide des champs clients")
    return await analyze_customer_fields(sample_size)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Analyse des champs clients Salesforce et SAP")
    parser.add_argument("--sample-size", type=int, default=50, help="Taille de l'échantillon à analyser")
    parser.add_argument("--quick", action="store_true", help="Analyse rapide avec 10 enregistrements")
    
    args = parser.parse_args()
    
    if args.quick:
        logger.info("🚀 Mode analyse rapide")
        results = asyncio.run(quick_analysis())
    else:
        logger.info(f"🚀 Analyse complète avec échantillon de {args.sample_size}")
        results = asyncio.run(analyze_customer_fields(args.sample_size))
    
    if results and "error" not in results:
        print("\n✅ Analyse terminée avec succès !")
        print("📁 Vérifiez les fichiers générés pour les détails complets")
    else:
        print(f"❌ Erreur lors de l'analyse: {results.get('error', 'Erreur inconnue')}")