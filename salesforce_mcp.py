# salesforce_mcp.py
from mcp.server.fastmcp import FastMCP
import os
import json
from datetime import datetime
import sys
import io
from typing import Optional, List
import traceback

# Configuration de l'encodage pour Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Créer le dossier logs s'il n'existe pas
os.makedirs("logs", exist_ok=True)
log_file = open("logs/salesforce_mcp.log", "w", encoding="utf-8")

# Journalisation
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted_message = f"[{timestamp}] {message}"
    log_file.write(f"{formatted_message}\n")
    log_file.flush()
    print(formatted_message)

log("Démarrage du serveur MCP Salesforce...")

# Création du serveur MCP
mcp = FastMCP("salesforce_mcp")

# Constantes
CACHE_FILE = "cache/metadata_salesforce.json"
os.makedirs("cache", exist_ok=True)

# Variables globales
sf = None

# Initialisation de Salesforce
def init_salesforce():
    global sf
    try:
        from simple_salesforce import Salesforce
        from dotenv import load_dotenv
        
        load_dotenv()
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        log(f"Connexion à Salesforce avec {username} sur {domain}...")
        
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Test de connexion rapide
        sf.query("SELECT Id FROM Account LIMIT 1")
        log("✅ Connexion Salesforce établie avec succès")
        return True
    except Exception as e:
        log(f"❌ Erreur de connexion Salesforce: {str(e)}")
        return False

# Fonctions utilitaires pour le cache
def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log(f"Erreur lors du chargement du cache: {str(e)}")
    return {}

def save_cache(data):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log(f"Erreur lors de l'enregistrement du cache: {str(e)}")

# Outils MCP
@mcp.tool(name="ping")
def ping() -> str:
    """Test simple de disponibilité du serveur MCP Salesforce"""
    log("Ping reçu!")
    return "pong! Serveur MCP Salesforce opérationnel"

@mcp.tool(name="salesforce_query")
async def salesforce_query(query: str) -> dict:
    """
    Exécute une requête SOQL sur Salesforce.
    
    Args:
        query: Une requête SOQL valide (ex: "SELECT Id, Name FROM Account LIMIT 5")
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    global sf
    
    try:
        if sf is None:
            if not init_salesforce():
                return {"error": "Impossible de se connecter à Salesforce"}
        
        log(f"Exécution de la requête SOQL: {query}")
        start_time = datetime.now()
        result = sf.query(query)
        end_time = datetime.now()
        query_time_ms = (end_time - start_time).total_seconds() * 1000
        
        log(f"Requête exécutée en {query_time_ms:.2f}ms - {result.get('totalSize', 0)} résultats")
        
        return {
            "totalSize": result.get("totalSize", 0),
            "records": result.get("records", []),
            "done": result.get("done", True),
            "query_time_ms": query_time_ms
        }
    except Exception as e:
        log(f"Erreur lors de l'exécution de la requête SOQL: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="salesforce_inspect")
async def inspect_salesforce(object_name: Optional[str] = None) -> dict:
    """
    Liste les objets et champs Salesforce depuis le cache.
    
    Args:
        object_name: Nom de l'objet à inspecter (optionnel)
        
    Returns:
        Un dictionnaire contenant les métadonnées ou une erreur
    """
    global sf
    
    try:
        if sf is None:
            if not init_salesforce():
                return {"error": "Impossible de se connecter à Salesforce"}
        
        cache = load_cache()
        
        if object_name:
            log(f"Inspection de l'objet Salesforce: {object_name}")
            
            # Vérifier si l'objet est dans le cache
            if object_name in cache:
                log(f"Objet {object_name} trouvé dans le cache")
                return cache[object_name]
            
            # Sinon, récupérer les métadonnées
            try:
                obj_desc = sf.__getattr__(object_name).describe()
                
                # Formatter les résultats
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
                
                # Mettre à jour le cache
                cache[object_name] = result
                save_cache(cache)
                
                log(f"Objet {object_name} inspecté avec succès - {len(result['fields'])} champs")
                return result
            except Exception as e:
                log(f"Erreur lors de l'inspection de l'objet {object_name}: {str(e)}")
                return {"error": str(e)}
        else:
            # Liste des objets
            log("Récupération de la liste des objets Salesforce")
            
            try:
                # Utiliser le cache si disponible et récent (< 24h)
                if "objects" in cache:
                    cache_time = datetime.fromisoformat(cache["objects"].get("update_time", "2000-01-01"))
                    now = datetime.now()
                    if (now - cache_time).total_seconds() < 86400:  # 24 heures
                        log("Utilisation des objets en cache")
                        return {"objects": cache["objects"]["list"]}
                
                # Sinon, récupérer la liste
                describe = sf.describe()
                objects = describe["sobjects"]
                
                # Formatter les résultats
                object_list = [
                    {
                        "name": obj["name"], 
                        "label": obj["label"],
                        "custom": obj["custom"]
                    }
                    for obj in objects
                ]
                
                # Mettre à jour le cache
                cache["objects"] = {
                    "update_time": datetime.now().isoformat(),
                    "count": len(object_list),
                    "list": object_list
                }
                save_cache(cache)
                
                log(f"Liste des objets récupérée - {len(object_list)} objets")
                return {"objects": object_list}
            except Exception as e:
                log(f"Erreur lors de la récupération des objets: {str(e)}")
                return {"error": str(e)}
    except Exception as e:
        log(f"Erreur inattendue dans inspect_salesforce: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="salesforce_refresh_metadata")
async def refresh_salesforce_metadata(objects_to_refresh: Optional[List[str]] = None) -> dict:
    """
    Force la mise à jour des métadonnées Salesforce.
    
    Args:
        objects_to_refresh: Liste des objets à rafraîchir (optionnel)
        
    Returns:
        Un dictionnaire contenant le résultat de l'opération
    """
    global sf
    
    try:
        if sf is None:
            if not init_salesforce():
                return {"error": "Impossible de se connecter à Salesforce"}
        
        log("Rafraîchissement des métadonnées Salesforce")
        
        cache = load_cache()
        cache_updated = False
        
        # Si aucun objet n'est spécifié, rafraîchir la liste des objets
        if not objects_to_refresh:
            try:
                describe = sf.describe()
                objects = describe["sobjects"]
                
                # Limiter à 15 objets standard pour éviter de surcharger
                objects_to_refresh = [
                    obj["name"] for obj in objects 
                    if not obj["custom"] and obj["createable"]
                ][:15]
                
                # Mise à jour du cache des objets
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
                cache_updated = True
                
                log(f"Liste des objets mise à jour - {len(objects_to_refresh)} objets sélectionnés pour rafraîchissement")
            except Exception as e:
                log(f"Erreur lors du rafraîchissement de la liste des objets: {str(e)}")
                return {"error": str(e)}
        
        # Rafraîchir les métadonnées pour chaque objet
        updated = []
        errors = []
        
        for obj_name in objects_to_refresh:
            try:
                log(f"Rafraîchissement de l'objet {obj_name}")
                
                # Récupérer les métadonnées
                obj_desc = sf.__getattr__(obj_name).describe()
                
                # Formatter les résultats
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
                
                # Mettre à jour le cache
                cache[obj_name] = result
                cache_updated = True
                updated.append(obj_name)
                
                log(f"Objet {obj_name} rafraîchi avec succès - {len(result['fields'])} champs")
            except Exception as e:
                log(f"Erreur lors du rafraîchissement de l'objet {obj_name}: {str(e)}")
                errors.append({"object": obj_name, "error": str(e)})
        
        # Sauvegarder le cache si des mises à jour ont été effectuées
        if cache_updated:
            save_cache(cache)
        
        return {
            "status": "ok" if not errors else "partial",
            "updated": updated,
            "errors": errors,
            "summary": f"{len(updated)} objets mis à jour, {len(errors)} erreurs"
        }
    except Exception as e:
        log(f"Erreur inattendue dans refresh_salesforce_metadata: {str(e)}")
        return {"error": str(e)}

# Tentative d'initialisation au démarrage
init_salesforce()

if __name__ == "__main__":
    try:
        log("Lancement du serveur MCP Salesforce...")
        mcp.run(transport="stdio")
    except KeyboardInterrupt:
        log("Arrêt du serveur MCP Salesforce par l'utilisateur")
    except Exception as e:
        log(f"Erreur fatale du serveur MCP Salesforce: {str(e)}")
        log(traceback.format_exc())