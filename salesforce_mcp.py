# salesforce_mcp.py - VERSION REFACTORISÉE ET OPTIMISÉE

from mcp.server.fastmcp import FastMCP
import os
import json
from datetime import datetime
import sys
import io
import asyncio
from typing import Optional, List, Dict, Any
import traceback
import argparse

# Configuration de l'encodage pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Créer le dossier logs s'il n'existe pas
import shutil
if os.path.exists("logs") and not os.path.isdir("logs"):
    os.remove("logs")  # Supprimer si c'est un fichier
os.makedirs("logs", exist_ok=True)
if os.path.exists("cache") and not os.path.isdir("cache"):
    os.remove("cache")  # Supprimer si c'est un fichier
os.makedirs("cache", exist_ok=True)
log_file = open("logs/salesforce_mcp.log", "w", encoding="utf-8")

# === CONSTANTES ===
CACHE_FILE = "cache/metadata_salesforce.json"

# Messages d'erreur centralisés
ERROR_MESSAGES = {
    "SF_CONNECTION_FAILED": "Impossible de se connecter à Salesforce",
    "SF_LIBRARY_MISSING": "La bibliothèque simple-salesforce n'est pas installée",
    "SF_OBJECT_NOT_FOUND": "Objet Salesforce '{}' non trouvé",
    "SF_RECORD_NOT_FOUND": "Enregistrement non trouvé",
    "SF_PRICEBOOK_NOT_FOUND": "Pricebook standard non trouvé",
    "SF_CREATE_FAILED": "Échec de création: {}",
    "SF_UPDATE_FAILED": "Échec de mise à jour: {}",
    "CACHE_LOAD_ERROR": "Erreur lors du chargement du cache: {}",
    "CACHE_SAVE_ERROR": "Erreur lors de l'enregistrement du cache: {}"
}

# Messages de succès centralisés
SUCCESS_MESSAGES = {
    "SF_CONNECTION_OK": "Connexion Salesforce établie avec succès",
    "SF_QUERY_OK": "Requête exécutée en {:.2f}ms - {} résultats",
    "SF_CREATE_OK": "Enregistrement {} créé avec succès: {}",
    "SF_UPDATE_OK": "Enregistrement {} {} mis à jour avec succès",
    "SF_PRICEBOOK_FOUND": "Pricebook standard trouvé: {} - {}",
    "SF_PRODUCT_COMPLETE": "Produit et entrée Pricebook créés avec succès",
    "SF_OPPORTUNITY_COMPLETE": "Opportunité créée avec {} lignes"
}

# === JOURNALISATION CENTRALISÉE ===
def log(message: str, level: str = "INFO", *args):
    """Journalisation centralisée avec formatage"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = message.format(*args) if args else message
    log_entry = f"[{timestamp}] [{level}] {formatted_message}"
    log_file.write(f"{log_entry}\n")
    log_file.flush()
    print(log_entry)

def log_error(message_key: str, *args):
    """Journalise une erreur avec message centralisé"""
    log(ERROR_MESSAGES[message_key], "ERROR", *args)

def log_success(message_key: str, *args):
    """Journalise un succès avec message centralisé"""
    log(SUCCESS_MESSAGES[message_key], "SUCCESS", *args)

def log_warning(message: str, *args):
    """Journalise un avertissement"""
    log(message, "WARNING", *args)

# === GESTION D'ERREURS CENTRALISÉE ===
def handle_error(error: Exception, context: str = "opération") -> Dict[str, Any]:
    """Gestion centralisée des erreurs avec logging détaillé pour debug"""
    error_msg = str(error)
    error_type = type(error).__name__
    
    # ⚠️ CORRECTION: Log plus détaillé pour diagnostic
    if hasattr(error, 'content'):
        log(f"Erreur {error_type} dans {context}: {error_msg}", "ERROR")
        log(f"Détails Salesforce: {error.content}", "ERROR")
    elif hasattr(error, 'response'):
        log(f"Erreur {error_type} dans {context}: {error_msg}", "ERROR")
        log(f"Réponse HTTP: {error.response}", "ERROR")
    else:
        log(f"Erreur {error_type} dans {context}: {error_msg}", "ERROR")
    
    # Renvoyer une erreur détaillée pour debug
    return {
        "error": error_msg,
        "error_type": error_type,
        "context": context
    }

def handle_sf_object_error(sobject: str, error: Exception) -> Dict[str, Any]:
    """Gestion spécifique des erreurs d'objets Salesforce"""
    if "AttributeError" in str(type(error)):
        log_error("SF_OBJECT_NOT_FOUND", sobject)
        return {"error": ERROR_MESSAGES["SF_OBJECT_NOT_FOUND"].format(sobject)}
    return handle_error(error, f"objet {sobject}")

def validate_sf_connection(sf) -> Optional[Dict[str, Any]]:
    """Valide la connexion Salesforce"""
    if sf is None:
        if not init_salesforce():
            return {"error": ERROR_MESSAGES["SF_CONNECTION_FAILED"]}
    return None

# === INITIALISATION ===
log("Démarrage du serveur MCP Salesforce - VERSION REFACTORISÉE", "STARTUP")

mcp = FastMCP("salesforce_mcp")
sf = None

def init_salesforce() -> bool:
    """Initialise la connexion Salesforce"""
    global sf
    try:
        from simple_salesforce import Salesforce
        from dotenv import load_dotenv
        
        load_dotenv()
        credentials = {
            'username': os.getenv("SALESFORCE_USERNAME"),
            'password': os.getenv("SALESFORCE_PASSWORD"),
            'security_token': os.getenv("SALESFORCE_SECURITY_TOKEN"),
            'domain': os.getenv("SALESFORCE_DOMAIN", "login"),
            'version': "55.0"
        }
        
        log(f"Connexion à Salesforce avec {credentials['username']} sur {credentials['domain']}...")
        
        sf = Salesforce(**credentials)
        
        # Test de connexion
        sf.query("SELECT Id FROM Account LIMIT 1")
        
        log_success("SF_CONNECTION_OK")
        return True
        
    except ImportError:
        log_error("SF_LIBRARY_MISSING")
        return False
    except Exception as e:
        log(f"Erreur de connexion Salesforce: {str(e)}", "ERROR")
        return False

# === UTILITAIRES CACHE ===
def load_cache() -> Dict[str, Any]:
    """Charge le cache avec gestion d'erreurs centralisée"""
    if not os.path.exists(CACHE_FILE):
        return {}
    
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log_error("CACHE_LOAD_ERROR", str(e))
        return {}

def save_cache(data: Dict[str, Any]) -> bool:
    """Sauvegarde le cache avec gestion d'erreurs"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        log_error("CACHE_SAVE_ERROR", str(e))
        return False

# === UTILITAIRES VALIDATION ===
def is_success_result(result: Dict[str, Any]) -> bool:
    """Vérifie si un résultat est un succès"""
    return result.get("success", False) and "error" not in result

def has_records(query_result: Dict[str, Any]) -> bool:
    """Vérifie si une requête a retourné des enregistrements"""
    return query_result.get("totalSize", 0) > 0

# === OUTILS MCP ===
@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP Salesforce"""
    log("Ping reçu!")
    return "pong! Serveur MCP Salesforce opérationnel - VERSION REFACTORISÉE"

@mcp.tool(name="salesforce_query")
async def salesforce_query(query: str) -> Dict[str, Any]:
    """Exécute une requête SOQL sur Salesforce"""
    global sf
    
    # Validation de la connexion
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        log(f"Exécution de la requête SOQL: {query}")
        start_time = datetime.now()
        
        result = sf.query(query)
        
        end_time = datetime.now()
        query_time_ms = (end_time - start_time).total_seconds() * 1000
        
        response = {
            "totalSize": result.get("totalSize", 0),
            "records": result.get("records", []),
            "done": result.get("done", True),
            "query_time_ms": query_time_ms
        }
        
        if "nextRecordsUrl" in result:
            response["nextRecordsUrl"] = result["nextRecordsUrl"]
        
        log_success("SF_QUERY_OK", query_time_ms, result.get('totalSize', 0))
        return response
        
    except Exception as e:
        return handle_error(e, "exécution requête SOQL")

@mcp.tool(name="salesforce_create_record")
async def salesforce_create_record(sobject: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Crée un enregistrement dans Salesforce"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        log(f"Création d'un enregistrement {sobject}")
        
        sf_object = getattr(sf, sobject)
        result = sf_object.create(data)
        
        if is_success_result(result):
            record_id = result.get("id")
            log_success("SF_CREATE_OK", sobject, record_id)
            return {
                "success": True,
                "id": record_id,
                "created": True
            }
        else:
            log_error("SF_CREATE_FAILED", str(result))
            return {"error": ERROR_MESSAGES["SF_CREATE_FAILED"].format(result)}
            
    except AttributeError as e:
        return handle_sf_object_error(sobject, e)
    except Exception as e:
        return handle_error(e, f"création {sobject}")

@mcp.tool(name="salesforce_update_record")
async def salesforce_update_record(sobject: str, record_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Met à jour un enregistrement dans Salesforce"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        log(f"Mise à jour {sobject} {record_id}")
        
        sf_object = getattr(sf, sobject)
        sf_object.update(record_id, data)
        
        log_success("SF_UPDATE_OK", sobject, record_id)
        return {
            "success": True,
            "id": record_id,
            "updated": True
        }
        
    except AttributeError as e:
        return handle_sf_object_error(sobject, e)
    except Exception as e:
        return handle_error(e, f"mise à jour {sobject}")

@mcp.tool(name="salesforce_get_standard_pricebook")
async def salesforce_get_standard_pricebook() -> Dict[str, Any]:
    """Récupère l'ID du Pricebook standard"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        log("Recherche du Pricebook standard")
        
        result = sf.query("SELECT Id, Name FROM Pricebook2 WHERE IsStandard = TRUE LIMIT 1")
        
        if has_records(result):
            pricebook = result["records"][0]
            log_success("SF_PRICEBOOK_FOUND", pricebook['Id'], pricebook['Name'])
            return {
                "success": True,
                "pricebook_id": pricebook["Id"],
                "pricebook_name": pricebook["Name"]
            }
        else:
            log_error("SF_PRICEBOOK_NOT_FOUND")
            return {"error": ERROR_MESSAGES["SF_PRICEBOOK_NOT_FOUND"]}
            
    except Exception as e:
        return handle_error(e, "recherche Pricebook")

@mcp.tool(name="salesforce_create_product_complete")
async def salesforce_create_product_complete(product_data: Dict[str, Any], unit_price: float = 0.0) -> Dict[str, Any]:
    """Crée un produit complet dans Salesforce avec son entrée Pricebook"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        product_name = product_data.get('Name', 'Sans nom')
        log(f"Création produit complet: {product_name}")
        
        # Vérifier si le produit existe déjà
        product_code = product_data.get("ProductCode")
        if product_code:
            existing_check = sf.query(f"SELECT Id FROM Product2 WHERE ProductCode = '{product_code}' LIMIT 1")
            if has_records(existing_check):
                existing_id = existing_check["records"][0]["Id"]
                log(f"Produit existant trouvé: {existing_id}")
                return {
                    "success": True,
                    "product_id": existing_id,
                    "created": False,
                    "message": "Produit existant utilisé"
                }
        
        # Créer le produit
        product_result = sf.Product2.create(product_data)
        
        if not is_success_result(product_result):
            return {"error": f"Échec création produit: {product_result}"}
        
        product_id = product_result.get("id")
        log(f"Produit créé: {product_id}", "SUCCESS")
        
        # Récupérer le Pricebook standard
        pricebook_result = await salesforce_get_standard_pricebook()
        if not pricebook_result.get("success"):
            return {"error": "Impossible de récupérer le Pricebook standard"}
        
        pricebook_id = pricebook_result["pricebook_id"]
        
        # Créer l'entrée Pricebook
        pricebook_entry_data = {
            "Pricebook2Id": pricebook_id,
            "Product2Id": product_id,
            "UnitPrice": unit_price,
            "IsActive": True
        }
        
        pricebook_entry_result = sf.PricebookEntry.create(pricebook_entry_data)
        pricebook_entry_id = pricebook_entry_result.get("id") if is_success_result(pricebook_entry_result) else None
        
        if pricebook_entry_id:
            log(f"Entrée Pricebook créée: {pricebook_entry_id}", "SUCCESS")
        else:
            log(f"Échec création entrée Pricebook: {pricebook_entry_result}", "WARNING")
        
        log_success("SF_PRODUCT_COMPLETE")
        return {
            "success": True,
            "product_id": product_id,
            "pricebook_entry_id": pricebook_entry_id,
            "created": True,
            "message": SUCCESS_MESSAGES["SF_PRODUCT_COMPLETE"]
        }
        
    except Exception as e:
        return handle_error(e, "création produit complet")

@mcp.tool(name="salesforce_create_opportunity_complete")
async def salesforce_create_opportunity_complete(opportunity_data: Dict[str, Any], line_items: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Crée une opportunité complète avec ses lignes"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        opportunity_name = opportunity_data.get('Name', 'Sans nom')
        log(f"Création opportunité complète: {opportunity_name}")
        
        # Créer l'opportunité
        opportunity_result = sf.Opportunity.create(opportunity_data)
        
        if not is_success_result(opportunity_result):
            return {"error": f"Échec création opportunité: {opportunity_result}"}
        
        opportunity_id = opportunity_result.get("id")
        log(f"Opportunité créée: {opportunity_id}", "SUCCESS")
        
        # Créer les lignes d'opportunité
        line_items_created = []
        if line_items:
            log(f"Création de {len(line_items)} lignes d'opportunité")
            
            for i, line_item in enumerate(line_items):
                try:
                    line_item["OpportunityId"] = opportunity_id
                    line_result = sf.OpportunityLineItem.create(line_item)
                    
                    if is_success_result(line_result):
                        line_id = line_result.get("id")
                        line_items_created.append(line_id)
                        log(f"Ligne {i+1} créée: {line_id}", "SUCCESS")
                    else:
                        log(f"Échec création ligne {i+1}: {line_result}", "ERROR")
                        
                except Exception as e:
                    log(f"Erreur création ligne {i+1}: {str(e)}", "ERROR")
        
        log_success("SF_OPPORTUNITY_COMPLETE", len(line_items_created))
        return {
            "success": True,
            "opportunity_id": opportunity_id,
            "line_items_created": line_items_created,
            "lines_count": len(line_items_created),
            "message": SUCCESS_MESSAGES["SF_OPPORTUNITY_COMPLETE"].format(len(line_items_created))
        }
        
    except Exception as e:
        return handle_error(e, "création opportunité complète")

@mcp.tool(name="salesforce_inspect")
async def inspect_salesforce(object_name: str = None) -> Dict[str, Any]:
    """Liste les objets et champs Salesforce depuis le cache"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        cache = load_cache()
        
        if object_name:
            return _inspect_single_object(object_name, cache)
        else:
            return _inspect_all_objects(cache)
            
    except Exception as e:
        return handle_error(e, "inspection Salesforce")

def _inspect_single_object(object_name: str, cache: Dict[str, Any]) -> Dict[str, Any]:
    """Inspecte un objet Salesforce spécifique"""
    log(f"Inspection de l'objet Salesforce: {object_name}")
    
    if object_name in cache:
        log(f"Objet {object_name} trouvé dans le cache")
        return cache[object_name]
    
    try:
        obj_desc = sf.__getattr__(object_name).describe()
        
        result = {
            "name": obj_desc["name"],
            "label": obj_desc["label"],
            "fields": [
                {
                    "name": f["name"],
                    "label": f["label"],
                    "type": f["type"],
                    "required": not f["nillable"],
                    "picklistValues": f.get("picklistValues", []) if f["type"] == "picklist" else []
                }
                for f in obj_desc["fields"]
            ],
            "update_time": datetime.now().isoformat()
        }
        
        cache[object_name] = result
        save_cache(cache)
        
        log(f"Objet {object_name} inspecté avec succès - {len(result['fields'])} champs")
        return result
        
    except Exception as e:
        return handle_error(e, f"inspection objet {object_name}")

def _inspect_all_objects(cache: Dict[str, Any]) -> Dict[str, Any]:
    """Inspecte tous les objets Salesforce"""
    log("Récupération de la liste des objets Salesforce")
    
    try:
        # Vérifier le cache
        if "objects" in cache:
            cache_time = datetime.fromisoformat(cache["objects"].get("update_time", "2000-01-01"))
            if (datetime.now() - cache_time).total_seconds() < 86400:  # 24 heures
                log("Utilisation des objets en cache")
                return {"objects": cache["objects"]["list"]}
        
        # Récupérer depuis Salesforce
        describe = sf.describe()
        objects = describe["sobjects"]
        
        object_list = [
            {
                "name": obj["name"], 
                "label": obj["label"],
                "custom": obj["custom"]
            }
            for obj in objects
        ]
        
        cache["objects"] = {
            "update_time": datetime.now().isoformat(),
            "count": len(object_list),
            "list": object_list
        }
        save_cache(cache)
        
        log(f"Liste des objets récupérée - {len(object_list)} objets")
        return {"objects": object_list}
        
    except Exception as e:
        return handle_error(e, "récupération objets")

@mcp.tool(name="salesforce_refresh_metadata")
async def refresh_salesforce_metadata(objects_to_refresh: Optional[List[str]] = None) -> Dict[str, Any]:
    """Force la mise à jour des métadonnées Salesforce"""
    global sf
    
    error_check = validate_sf_connection(sf)
    if error_check:
        return error_check
    
    try:
        log("Rafraîchissement des métadonnées Salesforce")
        
        cache = load_cache()
        
        if not objects_to_refresh:
            objects_to_refresh = _get_default_objects_to_refresh()
            _update_objects_cache(cache)
        
        updated, errors = _refresh_objects_metadata(objects_to_refresh, cache)
        
        save_cache(cache)
        
        return {
            "status": "ok" if not errors else "partial",
            "updated": updated,
            "errors": errors,
            "summary": f"{len(updated)} objets mis à jour, {len(errors)} erreurs"
        }
        
    except Exception as e:
        return handle_error(e, "rafraîchissement métadonnées")

def _get_default_objects_to_refresh() -> List[str]:
    """Récupère la liste par défaut des objets à rafraîchir"""
    describe = sf.describe()
    return [
        obj["name"] for obj in describe["sobjects"] 
        if not obj["custom"] and obj["createable"]
    ][:15]

def _update_objects_cache(cache: Dict[str, Any]) -> None:
    """Met à jour le cache des objets"""
    describe = sf.describe()
    objects = describe["sobjects"]
    
    object_list = [
        {
            "name": obj["name"], 
            "label": obj["label"],
            "custom": obj["custom"]
        }
        for obj in objects
    ]
    
    cache["objects"] = {
        "update_time": datetime.now().isoformat(),
        "count": len(object_list),
        "list": object_list
    }

def _refresh_objects_metadata(objects_to_refresh: List[str], cache: Dict[str, Any]) -> tuple:
    """Rafraîchit les métadonnées des objets spécifiés"""
    updated = []
    errors = []
    
    for obj_name in objects_to_refresh:
        try:
            log(f"Rafraîchissement de l'objet {obj_name}")
            
            obj_desc = sf.__getattr__(obj_name).describe()
            
            result = {
                "name": obj_desc["name"],
                "label": obj_desc["label"],
                "fields": [
                    {
                        "name": f["name"],
                        "label": f["label"],
                        "type": f["type"],
                        "required": not f["nillable"],
                        "picklistValues": f.get("picklistValues", []) if f["type"] == "picklist" else []
                    }
                    for f in obj_desc["fields"]
                ],
                "update_time": datetime.now().isoformat()
            }
            
            cache[obj_name] = result
            updated.append(obj_name)
            
            log(f"Objet {obj_name} rafraîchi avec succès - {len(result['fields'])} champs")
            
        except Exception as e:
            log(f"Erreur lors du rafraîchissement de l'objet {obj_name}: {str(e)}", "ERROR")
            errors.append({"object": obj_name, "error": str(e)})
    
    return updated, errors

# === INITIALISATION ET GESTION ARGUMENTS ===
init_salesforce()

# Table de mappage des fonctions MCP
mcp_functions = {
    "ping": ping,
    "salesforce_query": salesforce_query,
    "salesforce_create_record": salesforce_create_record,
    "salesforce_update_record": salesforce_update_record,
    "salesforce_get_standard_pricebook": salesforce_get_standard_pricebook,
    "salesforce_create_product_complete": salesforce_create_product_complete,
    "salesforce_create_opportunity_complete": salesforce_create_opportunity_complete,
    "salesforce_inspect": inspect_salesforce,
    "salesforce_refresh_metadata": refresh_salesforce_metadata
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-file", help="Fichier d'entrée JSON")
    parser.add_argument("--output-file", help="Fichier de sortie JSON")
    args, unknown = parser.parse_known_args()
    
    if args.input_file and args.output_file:
        try:
            with open(args.input_file, 'r') as f:
                input_data = json.load(f)
            
            action = input_data.get("action")
            params = input_data.get("params", {})
            
            log(f"Exécution de l'action: {action}")
            
            if action in mcp_functions:
                try:
                    result = asyncio.run(mcp_functions[action](**params))
                    with open(args.output_file, 'w') as f:
                        json.dump(result, f, indent=2)
                    log(f"Action {action} exécutée avec succès", "SUCCESS")
                    sys.exit(0)
                except Exception as e:
                    log(f"Erreur lors de l'exécution de {action}: {str(e)}", "ERROR")
                    with open(args.output_file, 'w') as f:
                        json.dump({"error": str(e)}, f)
                    sys.exit(1)
            else:
                error_msg = f"Action inconnue: {action}. Actions disponibles: {list(mcp_functions.keys())}"
                log(error_msg, "ERROR")
                with open(args.output_file, 'w') as f:
                    json.dump({"error": error_msg}, f)
                sys.exit(1)
                
        except Exception as e:
            log(f"Erreur lors du traitement des arguments: {str(e)}", "ERROR")
            sys.exit(1)
    
    try:
        log("Lancement du serveur MCP Salesforce refactorisé...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        log("Arrêt du serveur MCP Salesforce par l'utilisateur", "INFO")
    except Exception as e:
        log(f"Erreur fatale du serveur MCP Salesforce: {str(e)}", "ERROR")
        log(f"Traceback: {traceback.format_exc()}", "DEBUG")
    finally:
        log_file.close()