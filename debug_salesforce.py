# salesforce_mcp.py
from mcp_app import mcp
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import logging

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Connexion Salesforce
sf = None

# Cache pour les métadonnées Salesforce
CACHE_FILE = "metadata_salesforce.json"

def load_cache():
    """Charge le cache des métadonnées Salesforce"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement du cache: {str(e)}")
    return {}

def save_cache(data):
    """Enregistre le cache des métadonnées Salesforce"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement du cache: {str(e)}")

def init_salesforce():
    """Initialise la connexion Salesforce"""
    global sf
    
    try:
        from simple_salesforce import Salesforce
        
        # Récupérer les informations de connexion
        username = os.getenv("SALESFORCE_USERNAME")
        password = os.getenv("SALESFORCE_PASSWORD")
        security_token = os.getenv("SALESFORCE_SECURITY_TOKEN")
        domain = os.getenv("SALESFORCE_DOMAIN", "login")
        
        # Journaliser sans les credentials sensibles
        logger.info(f"Connexion à Salesforce avec {username} sur {domain}...")
        
        # Initialiser la connexion
        sf = Salesforce(
            username=username,
            password=password,
            security_token=security_token,
            domain=domain
        )
        
        # Tester la connexion
        sf.query("SELECT Id FROM Account LIMIT 1")
        
        logger.info("✅ Connexion Salesforce établie avec succès")
        return True
    except ImportError:
        logger.error("❌ La bibliothèque simple-salesforce n'est pas installée")
        return False
    except Exception as e:
        logger.error(f"❌ Erreur de connexion Salesforce: {str(e)}")
        return False

# Initialiser la connexion au démarrage
init_salesforce()

@mcp.tool(name="ping")
async def ping() -> str:
    """Simple test de disponibilité du serveur MCP"""
    return "pong! Salesforce MCP est opérationnel"

@mcp.tool(name="salesforce.query")
async def salesforce_query(query: str) -> dict:
    """
    Exécute une requête SOQL sur Salesforce.
    
    Args:
        query: Une requête SOQL valide (ex: "SELECT Id, Name FROM Account LIMIT 5")
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    global sf
    
    if sf is None:
        if not init_salesforce():
            return {"error": "Impossible de se connecter à Salesforce"}
    
    try:
        # Exécuter la requête
        start_time = datetime.now()
        result = sf.query(query)
        end_time = datetime.now()
        
        # Construire la réponse
        response = {
            "totalSize": result.get("totalSize", 0),
            "records": result.get("records", []),
            "done": result.get("done", True),
            "query_time_ms": (end_time - start_time).total_seconds() * 1000
        }
        
        # Ajouter nextRecordsUrl si présent
        if "nextRecordsUrl" in result:
            response["nextRecordsUrl"] = result["nextRecordsUrl"]
            
        return response
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution de la requête SOQL: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="salesforce.inspect")
async def inspect_salesforce(object_name: str = None) -> dict:
    """
    Liste les objets et champs Salesforce depuis le cache.
    
    Args:
        object_name: Nom de l'objet à inspecter (optionnel)
        
    Returns:
        Un dictionnaire contenant les métadonnées ou une erreur
    """
    global sf
    
    # Charger le cache
    cache = load_cache()
    
    if object_name:
        # Si l'objet est demandé et présent dans le cache, le retourner
        if object_name in cache:
            return cache[object_name]
        
        # Sinon, essayer de récupérer les informations en direct
        if sf is None:
            if not init_salesforce():
                return {"error": "Impossible de se connecter à Salesforce"}
        
        try:
            # Récupérer les métadonnées de l'objet
            obj_desc = sf.__getattr__(object_name).describe()
            
            # Construire la réponse
            result = {
                "name": obj_desc["name"],
                "label": obj_desc["label"],
                "fields": [
                    {
                        "name": f["name"],
                        "label": f["label"],
                        "type": f["type"],
                        "required": not f["nillable"]
                    }
                    for f in obj_desc["fields"]
                ],
                "update_time": datetime.now().isoformat()
            }
            
            # Mettre à jour le cache
            cache[object_name] = result
            save_cache(cache)
            
            return result
        except Exception as e:
            logger.error(f"Erreur lors de l'inspection de l'objet {object_name}: {str(e)}")
            return {"error": f"Impossible d'inspecter l'objet {object_name}: {str(e)}"}
    else:
        # Si aucun objet n'est spécifié, retourner la liste des objets disponibles
        if sf is None:
            if not init_salesforce():
                return {"error": "Impossible de se connecter à Salesforce"}
        
        try:
            # Lire les objets à partir du cache ou récupérer en direct
            if "objects" in cache:
                return {"objects": [
                    {"name": name, "label": obj.get("label", name)}
                    for name, obj in cache.items()
                    if name != "objects"
                ]}
            
            # Récupérer les objets disponibles
            describe = sf.describe()
            objects = describe["sobjects"]
            
            # Ajouter les objets au cache
            cache["objects"] = {
                "timestamp": datetime.now().isoformat(),
                "count": len(objects)
            }
            
            # Retourner la liste des objets
            return {"objects": [
                {"name": obj["name"], "label": obj["label"]}
                for obj in objects
            ]}
        except Exception as e:
            logger.error(f"Erreur lors de l'inspection des objets: {str(e)}")
            return {"error": f"Impossible de lister les objets: {str(e)}"}

@mcp.tool(name="salesforce.refresh_metadata")
async def refresh_salesforce_metadata(objects_to_refresh: list = None) -> dict:
    """
    Force la mise à jour des métadonnées Salesforce.
    
    Args:
        objects_to_refresh: Liste des objets à rafraîchir (optionnel)
        
    Returns:
        Un dictionnaire contenant le résultat de l'opération
    """
    global sf
    
    if sf is None:
        if not init_salesforce():
            return {"error": "Impossible de se connecter à Salesforce"}
    
    try:
        # Charger le cache existant
        cache = load_cache()
        
        # Si aucun objet n'est spécifié, récupérer tous les objets
        if not objects_to_refresh:
            try:
                # Récupérer la liste des objets
                describe = sf.describe()
                objects = describe["sobjects"]
                
                # Mettre à jour le cache des objets
                cache["objects"] = {
                    "timestamp": datetime.now().isoformat(),
                    "count": len(objects)
                }
                
                # Limiter à 10 objets pour éviter les temps de réponse trop longs
                objects_to_refresh = [obj["name"] for obj in objects[:10]]
            except Exception as e:
                logger.error(f"Erreur lors de la récupération des objets: {str(e)}")
                return {"error": f"Impossible de récupérer la liste des objets: {str(e)}"}
        
        # Rafraîchir les métadonnées pour chaque objet
        updated = []
        
        for obj_name in objects_to_refresh:
            try:
                # Récupérer les métadonnées de l'objet
                obj_desc = sf.__getattr__(obj_name).describe()
                
                # Mettre à jour le cache
                cache[obj_name] = {
                    "name": obj_desc["name"],
                    "label": obj_desc["label"],
                    "fields": [
                        {
                            "name": f["name"],
                            "label": f["label"],
                            "type": f["type"],
                            "required": not f["nillable"]
                        }
                        for f in obj_desc["fields"]
                    ],
                    "update_time": datetime.now().isoformat()
                }
                
                updated.append(obj_name)
            except Exception as e:
                logger.error(f"Erreur lors du rafraîchissement de l'objet {obj_name}: {str(e)}")
        
        # Enregistrer le cache
        save_cache(cache)
        
        return {
            "status": "ok",
            "updated": updated,
            "total": len(updated)
        }
    except Exception as e:
        logger.error(f"Erreur lors du rafraîchissement des métadonnées: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP Salesforce...")
    mcp.run(transport="stdio")