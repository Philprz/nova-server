#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script de synchronisation bidirectionnelle des clients entre SAP et Salesforce.
Version corrigée pour compatibilité avec l'architecture NOVA existante.
"""

import os
import sys
import asyncio
import logging
import argparse
from datetime import datetime
from typing import Dict, List, Any

# Ajout du répertoire parent pour l'import des modules du projet
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Créer le dossier logs s'il n'existe pas
os.makedirs("logs", exist_ok=True)

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(f"logs/sync_clients_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Import des connecteurs MCP
try:
    from services.mcp_connector import MCPConnector
except ImportError:
    logger.error("Erreur lors de l'import du MCPConnector. Assurez-vous que le module existe.")
    sys.exit(1)

# ===== Configuration =====
# Mappage des champs entre SAP et Salesforce - VERSION CORRIGÉE
FIELD_MAPPING = {
    "sap_to_sf": {
        "CardCode": "AccountNumber",
        "CardName": "Name",
        "Phone1": "Phone",
        "Website": "Website",
        "Notes": "Description",
        # CORRECTION: Supprimer les champs d'adresse problématiques
        "Phone2": "Fax",
        "FederalTaxID": "Sic"
        # Tous les champs MailXXX supprimés car problématiques
    },
    "sf_to_sap": {
        "Name": "CardName",
        "Phone": "Phone1",
        "Fax": "Phone2", 
        "Website": "Website",
        "Description": "Notes",
        "Sic": "FederalTaxID"
        # CORRECTION : Supprimer TOUS les champs d'adresse et Industry
        # Car ils causent des erreurs SAP constantes
    }
}

# CORRECTION: Utiliser AccountNumber au lieu d'un champ personnalisé
SAP_ID_FIELD = "CardCode"
SF_ID_FIELD = "AccountNumber"

# ===== Fonctions principales =====
async def test_connections() -> bool:
    """Test des connexions MCP SAP et Salesforce"""
    logger.info("Test des connexions MCP...")
    
    try:
        # Test SAP
        sap_test = await MCPConnector.call_sap_mcp("ping", {})
        if "error" in sap_test:
            logger.error(f"Connexion SAP échouée: {sap_test['error']}")
            return False
        logger.info("✅ Connexion SAP OK")
        
        # Test Salesforce
        sf_test = await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": "SELECT Id FROM Account LIMIT 1"
        })
        if "error" in sf_test:
            logger.error(f"Connexion Salesforce échouée: {sf_test['error']}")
            return False
        logger.info("✅ Connexion Salesforce OK")
        
        return True
        
    except Exception as e:
        logger.error(f"Erreur lors du test des connexions: {str(e)}")
        return False

async def get_sap_customers() -> List[Dict[str, Any]]:
    """Récupère tous les clients depuis SAP"""
    logger.info("Récupération des clients SAP...")
    
    try:
        # CORRECTION: Utiliser l'endpoint correct pour les BusinessPartners
        result = await MCPConnector.call_sap_mcp("sap_read", {
            "endpoint": "/BusinessPartners?$filter=CardType eq 'cCustomer'&$orderby=CardCode",
            "method": "GET"
        })
        
        if "error" in result:
            logger.error(f"Erreur lors de la récupération des clients SAP: {result['error']}")
            return []
        
        customers = result.get("value", [])
        logger.info(f"{len(customers)} clients trouvés dans SAP")
        return customers
        
    except Exception as e:
        logger.error(f"Exception lors de la récupération des clients SAP: {str(e)}")
        return []

async def get_salesforce_accounts() -> List[Dict[str, Any]]:
    """Récupère tous les comptes depuis Salesforce"""
    logger.info("Récupération des comptes Salesforce...")
    
    try:
        # CORRECTION: Requête avec tous les champs nécessaires
        query = """
        SELECT Id, Name, AccountNumber, Type, Industry, AnnualRevenue, NumberOfEmployees,
               Phone, Fax, Website, Description,
               BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry,
               ShippingStreet, ShippingCity, ShippingState, ShippingPostalCode, ShippingCountry,
               CreatedDate, LastModifiedDate, Sic
        FROM Account 
        ORDER BY Name
        """
        
        result = await MCPConnector.call_salesforce_mcp("salesforce_query", {
            "query": query
        })
        
        if "error" in result:
            logger.error(f"Erreur lors de la récupération des comptes Salesforce: {result['error']}")
            return []
        
        accounts = result.get("records", [])
        logger.info(f"{len(accounts)} comptes trouvés dans Salesforce")
        return accounts
        
    except Exception as e:
        logger.error(f"Exception lors de la récupération des comptes Salesforce: {str(e)}")
        return []

def prepare_account_for_salesforce(sap_customer: Dict[str, Any]) -> Dict[str, Any]:
    """Convertit un client SAP en compte Salesforce"""
    sf_account = {}
    
    # Mappage des champs avec nettoyage
    for sap_field, sf_field in FIELD_MAPPING["sap_to_sf"].items():
        if sf_field and sap_field in sap_customer and sap_customer[sap_field] is not None:
            value = sap_customer[sap_field]
            
            # Nettoyage des données
            if isinstance(value, str):
                value = value.strip()
                if len(value) == 0:
                    continue
            
            # Validation des limites Salesforce
            if sf_field == "Phone" and len(str(value)) > 40:
                value = str(value)[:40]
            elif sf_field == "Description" and len(str(value)) > 32000:
                value = str(value)[:32000]
            elif sf_field == "Name" and len(str(value)) > 255:
                value = str(value)[:255]
            
            sf_account[sf_field] = value
    
    # CORRECTION: Validation cohérence État/Pays pour Salesforce
    # Si état sans pays, supprimer l'état
    if sf_account.get("BillingState") and not sf_account.get("BillingCountry"):
        logger.warning(f"Suppression BillingState sans BillingCountry pour {sap_customer.get('CardName')}")
        del sf_account["BillingState"]
    
    if sf_account.get("ShippingState") and not sf_account.get("ShippingCountry"):
        logger.warning(f"Suppression ShippingState sans ShippingCountry pour {sap_customer.get('CardName')}")
        del sf_account["ShippingState"]
    
    # Valeurs par défaut
    if not sf_account.get("Type"):
        sf_account["Type"] = "Customer"
    
    return sf_account

def prepare_customer_for_sap(sf_account: Dict[str, Any], card_code: str = None) -> Dict[str, Any]:
    """Convertit un compte Salesforce en client SAP - VERSION CORRIGÉE NOTES SAP"""
    
    # Détecter le pays à partir des données Salesforce
    country = sf_account.get("BillingCountry", "")
    validation_type = "FR"  # Par défaut France
    
    if country:
        country_lower = country.lower()
        if "usa" in country_lower or "united states" in country_lower or "america" in country_lower:
            validation_type = "US"
        elif "uk" in country_lower or "united kingdom" in country_lower or "britain" in country_lower:
            validation_type = "UK"
    
    # CORRECTION PRINCIPALE: Notes ultra-courtes pour éviter l'erreur SAP
    # SAP BusinessPartner Notes a une limite stricte apparemment < 100 caractères
    base_notes = f"NOVA - {validation_type}"  # Maximum 10 caractères
    
    sap_customer = {
        "CardType": "cCustomer",
        "GroupCode": 100,
        "Currency": "EUR",
        "Valid": "tYES",
        "Frozen": "tNO",
        "Notes": base_notes  # Notes très courtes
    }
    
    # CardCode
    if card_code:
        sap_customer["CardCode"] = card_code
    
    # Mappage simplifié sans les champs problématiques
    safe_mappings = {
        "Name": "CardName",
        "Phone": "Phone1", 
        "Website": "Website",
        "Sic": "FederalTaxID"
    }
    
    for sf_field, sap_field in safe_mappings.items():
        if sf_field in sf_account and sf_account[sf_field] is not None:
            value = sf_account[sf_field]
            
            # Ignorer les attributs Salesforce
            if isinstance(value, dict) and "attributes" in value:
                continue
                
            # Nettoyage
            if isinstance(value, str):
                value = value.strip()
                if len(value) == 0:
                    continue
            
            # Limites SAP STRICTES
            if sap_field == "CardName" and len(str(value)) > 100:
                value = str(value)[:100]
            elif sap_field in ["Phone1"] and len(str(value)) > 20:
                value = str(value)[:20]
            elif sap_field == "Website" and len(str(value)) > 100:
                value = str(value)[:100]
            elif sap_field == "FederalTaxID" and len(str(value)) > 32:
                value = str(value)[:32]
                
            sap_customer[sap_field] = value
    
    # CORRECTION FINALE: Garder les Notes très courtes
    # Ne plus ajouter de description pour éviter le dépassement
    final_notes = base_notes
    
    # VALIDATION STRICTE: Limiter à 50 caractères pour être sûr
    if len(final_notes) > 50:
        final_notes = final_notes[:50]
    
    sap_customer["Notes"] = final_notes
    
    # Référence croisée Salesforce (TOUJOURS EN DERNIER pour écraser si nécessaire)
    if sf_account.get("Id"):
        sap_customer["FederalTaxID"] = sf_account["Id"][:32]
    
    return sap_customer

def generate_card_code_from_sf(sf_account: Dict[str, Any]) -> str:
    """Génère un CardCode SAP à partir d'un compte Salesforce"""
    import re
    import time
    
    name = sf_account.get("Name", "CLIENT")
    clean_name = re.sub(r'[^a-zA-Z0-9]', '', name)[:8].upper()
    timestamp = str(int(time.time()))[-4:]
    
    return f"SF{clean_name}{timestamp}"[:15]

async def create_account_in_salesforce(sap_customer: Dict[str, Any]) -> Dict[str, Any]:
    """Crée un nouveau compte dans Salesforce à partir d'un client SAP"""
    sf_data = prepare_account_for_salesforce(sap_customer)
    
    if not sf_data.get("Name"):
        return {"error": "Nom du client requis pour création Salesforce"}
    
    logger.info(f"Création du compte Salesforce pour {sap_customer.get('CardName')}")
    
    result = await MCPConnector.call_salesforce_mcp("salesforce_create_record", {
        "sobject": "Account", 
        "data": sf_data
    })
    
    if "error" in result:
        logger.error(f"Erreur lors de la création du compte: {result['error']}")
    else:
        logger.info(f"✅ Compte créé avec succès: {result.get('id')}")
        
    return result

async def update_account_in_salesforce(sf_id: str, sap_customer: Dict[str, Any]) -> Dict[str, Any]:
    """Met à jour un compte existant dans Salesforce"""
    sf_data = prepare_account_for_salesforce(sap_customer)
    
    # Ne pas modifier l'AccountNumber lors d'une mise à jour
    if "AccountNumber" in sf_data:
        del sf_data["AccountNumber"]
    
    if not sf_data:
        logger.info(f"Aucune donnée à mettre à jour pour le compte {sf_id}")
        return {"success": True}
    
    logger.info(f"Mise à jour du compte Salesforce {sf_id}")
    
    result = await MCPConnector.call_salesforce_mcp("salesforce_update_record", {
        "sobject": "Account",
        "record_id": sf_id,
        "data": sf_data
    })
    
    if "error" in result:
        logger.error(f"Erreur lors de la mise à jour du compte: {result['error']}")
    else:
        logger.info("✅ Compte mis à jour avec succès")
        
    return result

async def create_customer_in_sap(sf_account: Dict[str, Any]) -> Dict[str, Any]:
    """Crée un nouveau client dans SAP à partir d'un compte Salesforce"""
    
    # Générer un CardCode ou utiliser l'AccountNumber existant
    card_code = sf_account.get("AccountNumber")
    if not card_code:
        card_code = generate_card_code_from_sf(sf_account)
    
    sap_data = prepare_customer_for_sap(sf_account, card_code)
    
    if not sap_data.get("CardName"):
        return {"error": "Nom du client requis pour création SAP"}
    
    logger.info(f"Création du client SAP pour {sf_account.get('Name')} (CardCode: {card_code})")
    
    # CORRECTION: Utiliser la méthode correcte du connecteur
    result = await MCPConnector.call_sap_mcp("sap_create_customer_complete", {
        "customer_data": sap_data
    })
    
    if "error" in result:
        logger.error(f"Erreur lors de la création du client SAP: {result['error']}")
    elif result.get("success"):
        logger.info(f"✅ Client SAP créé avec succès: {card_code}")
        
        # Mise à jour du compte Salesforce avec le CardCode si nécessaire
        if not sf_account.get("AccountNumber") and sf_account.get("Id"):
            await MCPConnector.call_salesforce_mcp("salesforce_update_record", {
                "sobject": "Account",
                "record_id": sf_account["Id"],
                "data": {"AccountNumber": card_code}
            })
    
    return result

async def sync_sap_to_salesforce(dry_run=False) -> Dict[str, int]:
    """Synchronise les clients SAP vers Salesforce"""
    stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
    
    # 1. Obtenir tous les clients SAP
    sap_customers = await get_sap_customers()
    if not sap_customers:
        logger.warning("Aucun client SAP trouvé")
        return stats
    
    # 2. Obtenir tous les comptes Salesforce pour le lookup
    sf_accounts = await get_salesforce_accounts()
    sf_accounts_by_account_number = {}
    
    for account in sf_accounts:
        account_number = account.get("AccountNumber")
        if account_number:
            sf_accounts_by_account_number[account_number] = account
    
    logger.info(f"Mapping créé: {len(sf_accounts_by_account_number)} comptes Salesforce avec AccountNumber")
    
    # 3. Pour chaque client SAP, vérifier s'il existe dans Salesforce
    for i, customer in enumerate(sap_customers, 1):
        try:
            card_code = customer.get("CardCode")
            if not card_code:
                logger.warning(f"Client SAP sans CardCode, ignoré: {customer.get('CardName')}")
                stats["skipped"] += 1
                continue
            
            logger.info(f"[{i}/{len(sap_customers)}] Traitement SAP → SF: {card_code} - {customer.get('CardName')}")
            
            # Si le client existe dans Salesforce, mise à jour
            if card_code in sf_accounts_by_account_number:
                sf_account = sf_accounts_by_account_number[card_code]
                sf_id = sf_account.get("Id")
                
                if dry_run:
                    logger.info(f"🔍 [DRY RUN] Mise à jour compte SF {sf_id}")
                    stats["updated"] += 1
                else:
                    result = await update_account_in_salesforce(sf_id, customer)
                    if "error" not in result:
                        stats["updated"] += 1
                    else:
                        stats["failed"] += 1
            else:
                # Sinon, création d'un nouveau compte
                if dry_run:
                    logger.info(f"🔍 [DRY RUN] Création compte SF pour {customer.get('CardName')}")
                    stats["created"] += 1
                else:
                    result = await create_account_in_salesforce(customer)
                    if "error" not in result:
                        stats["created"] += 1
                    else:
                        stats["failed"] += 1
            
            # Pause pour éviter les limites API
            if i % 10 == 0:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erreur traitement client SAP {customer.get('CardCode', 'UNKNOWN')}: {str(e)}")
            stats["failed"] += 1
    
    return stats

async def sync_salesforce_to_sap(dry_run=False) -> Dict[str, int]:
    """Synchronise les comptes Salesforce vers SAP"""
    stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
    
    # 1. Obtenir tous les comptes Salesforce
    sf_accounts = await get_salesforce_accounts()
    if not sf_accounts:
        logger.warning("Aucun compte Salesforce trouvé")
        return stats
    
    # 2. Obtenir tous les clients SAP pour le lookup
    sap_customers = await get_sap_customers()
    sap_customers_by_card_code = {c.get("CardCode"): c for c in sap_customers if c.get("CardCode")}
    
    logger.info(f"Mapping créé: {len(sap_customers_by_card_code)} clients SAP")
    
    # 3. Pour chaque compte Salesforce, vérifier s'il existe dans SAP
    for i, account in enumerate(sf_accounts, 1):
        try:
            account_number = account.get("AccountNumber")
            account_name = account.get("Name", "Sans nom")
            
            logger.info(f"[{i}/{len(sf_accounts)}] Traitement SF → SAP: {account.get('Id')} - {account_name}")
            
            # Si aucun AccountNumber, créer un nouveau client SAP
            if not account_number:
                if dry_run:
                    new_card_code = generate_card_code_from_sf(account)
                    logger.info(f"🔍 [DRY RUN] Création client SAP pour {account_name} (CardCode: {new_card_code})")
                    stats["created"] += 1
                else:
                    result = await create_customer_in_sap(account)
                    if "error" not in result and result.get("success"):
                        stats["created"] += 1
                    else:
                        stats["failed"] += 1
                continue
            
            # Si le client existe déjà dans SAP, on pourrait faire une mise à jour
            # Mais pour la sécurité, on évite pour l'instant
            if account_number in sap_customers_by_card_code:
                logger.info(f"Client SAP {account_number} existe déjà, pas de mise à jour")
                stats["skipped"] += 1
            else:
                # Le compte a un AccountNumber mais n'existe pas dans SAP
                if dry_run:
                    logger.info(f"🔍 [DRY RUN] Création client SAP pour {account_name} (CardCode: {account_number})")
                    stats["created"] += 1
                else:
                    result = await create_customer_in_sap(account)
                    if "error" not in result and result.get("success"):
                        stats["created"] += 1
                    else:
                        stats["failed"] += 1
            
            # Pause pour éviter les limites API
            if i % 10 == 0:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Erreur traitement compte SF {account.get('Id', 'UNKNOWN')}: {str(e)}")
            stats["failed"] += 1
    
    return stats

async def run_sync(direction="both", dry_run=False):
    """Exécute la synchronisation dans la direction spécifiée"""
    start_time = datetime.now()
    logger.info(f"==== Début de la synchronisation ({direction}) ====")
    if dry_run:
        logger.info("🔍 MODE DRY RUN - Aucune modification ne sera effectuée")
    
    try:
        # Test des connexions
        if not await test_connections():
            logger.error("❌ Échec du test des connexions")
            return
        
        # Synchronisation selon la direction choisie
        total_stats = {"created": 0, "updated": 0, "failed": 0, "skipped": 0}
        
        if direction in ["both", "sap2sf"]:
            logger.info("=== Synchronisation SAP → Salesforce ===")
            sap_to_sf_stats = await sync_sap_to_salesforce(dry_run)
            logger.info(f"📊 Résultats SAP → Salesforce: {sap_to_sf_stats}")
            if not dry_run:
                for key in total_stats:
                    total_stats[key] += sap_to_sf_stats.get(key, 0)
        
        if direction in ["both", "sf2sap"]:
            logger.info("=== Synchronisation Salesforce → SAP ===")
            sf_to_sap_stats = await sync_salesforce_to_sap(dry_run)
            logger.info(f"📊 Résultats Salesforce → SAP: {sf_to_sap_stats}")
            if not dry_run:
                for key in total_stats:
                    total_stats[key] += sf_to_sap_stats.get(key, 0)
        
        # Résumé final
        logger.info("=" * 60)
        logger.info("📊 RÉSUMÉ FINAL DE LA SYNCHRONISATION")
        logger.info("=" * 60)
        if not dry_run:
            logger.info(f"✅ Créations totales: {total_stats['created']}")
            logger.info(f"🔄 Mises à jour totales: {total_stats['updated']}")
            logger.info(f"❌ Échecs totaux: {total_stats['failed']}")
            logger.info(f"⏭️ Ignorés totaux: {total_stats['skipped']}")
        else:
            logger.info("🔍 Mode DRY RUN - Aucune modification effectuée")
        
    except Exception as e:
        logger.error(f"❌ Erreur lors de la synchronisation: {e}", exc_info=True)
    finally:
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        logger.info(f"🕐 Durée totale: {duration:.2f} secondes")
        logger.info("==== Fin de la synchronisation ====")

if __name__ == "__main__":
    # Parse des arguments en ligne de commande
    parser = argparse.ArgumentParser(description="Synchronisation bidirectionnelle des clients entre SAP et Salesforce")
    parser.add_argument("--direction", choices=["both", "sap2sf", "sf2sap"], default="both",
                      help="Direction de la synchronisation: les deux (both), SAP vers Salesforce (sap2sf) ou Salesforce vers SAP (sf2sap)")
    parser.add_argument("--dry-run", action="store_true", help="Mode simulation (aucune modification)")
    parser.add_argument("--verbose", action="store_true", help="Activer le mode verbeux")
    
    args = parser.parse_args()
    
    # Configuration du niveau de log
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        
    # Exécution de la synchronisation
    asyncio.run(run_sync(args.direction, args.dry_run))