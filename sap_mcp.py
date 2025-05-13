# sap_mcp.py
from mcp_app import mcp
import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv
import logging
import sys
from typing import Optional

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Charger les variables d'environnement
load_dotenv()

# Afficher un message de démarrage
print("🚀 Initialisation du serveur MCP SAP...")

# Configuration SAP
SAP_BASE_URL = os.getenv("SAP_REST_BASE_URL")
SAP_USER = os.getenv("SAP_USER")
SAP_CLIENT_PASSWORD = os.getenv("SAP_CLIENT_PASSWORD")
SAP_CLIENT = os.getenv("SAP_CLIENT")

# Cache pour les métadonnées SAP
CACHE_FILE = "metadata_sap.json"

# Session SAP partagée
sap_session = {"cookies": None, "expires": None}

def load_cache():
    """Charge le cache des métadonnées SAP"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Erreur lors du chargement du cache: {str(e)}")
    return {}

def save_cache(data):
    """Enregistre le cache des métadonnées SAP"""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Erreur lors de l'enregistrement du cache: {str(e)}")

async def login_sap():
    """Authentification à SAP B1"""
    url = SAP_BASE_URL + "/Login"
    auth_payload = {
        "UserName": SAP_USER,
        "Password": SAP_CLIENT_PASSWORD,
        "CompanyDB": SAP_CLIENT
    }
    headers = {
        "Content-Type": "application/json"
    }
    
    try:
        logger.info(f"Connexion à SAP {SAP_BASE_URL}...")
        
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            response = await client.post(url, json=auth_payload, headers=headers)
            response.raise_for_status()
            
            sap_session["cookies"] = response.cookies
            sap_session["expires"] = datetime.utcnow().timestamp() + 60 * 20  # 20 minutes
            
            logger.info("✅ Connexion SAP établie avec succès")
            return True
    except Exception as e:
        logger.error(f"❌ Erreur de connexion SAP: {str(e)}")
        return False

async def call_sap(endpoint: str, method="GET", payload: Optional[dict] = None):
    """Appel à l'API REST SAP B1"""
    # Vérifier et rafraîchir la session si nécessaire
    if not sap_session["cookies"] or datetime.utcnow().timestamp() > sap_session["expires"]:
        if not await login_sap():
            return {"error": "Impossible de se connecter à SAP"}
    
    try:
        url = SAP_BASE_URL + endpoint
        
        async with httpx.AsyncClient(cookies=sap_session["cookies"], verify=False, timeout=30.0) as client:
            if method == "GET":
                response = await client.get(url)
            else:
                response = await client.post(url, json=payload or {})
            
            response.raise_for_status()
            
            if response.status_code == 204:  # No Content
                return {"status": "success", "message": "Opération réussie"}
            
            return response.json()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            # Session expirée, tenter de se reconnecter
            logger.warning("Session SAP expirée, reconnexion...")
            
            if await login_sap():
                return await call_sap(endpoint, method, payload)
            
        logger.error(f"Erreur HTTP lors de l'appel à {endpoint}: {str(e)}")
        
        try:
            # Tenter de récupérer le message d'erreur SAP
            error_msg = e.response.json()
            return {"error": error_msg}
        except:
            return {"error": f"Erreur HTTP {e.response.status_code}: {str(e)}"}
    except Exception as e:
        logger.error(f"Erreur lors de l'appel à {endpoint}: {str(e)}")
        return {"error": str(e)}

async def fetch_sap_metadata():
    """Récupère les métadonnées SAP"""
    try:
        # Tenter d'utiliser l'endpoint standard OData
        metadata = await call_sap("/$metadata")
        
        # Traiter les métadonnées (adapter selon le format retourné)
        schema = {
            "endpoints": [],
            "update_time": datetime.utcnow().isoformat()
        }
        
        # Si les métadonnées sont au format XML ou autre format spécial,
        # il faudrait les parser correctement ici
        
        # Sauvegarder dans le cache
        save_cache(schema)
        return schema
    except Exception as e:
        logger.warning(f"Impossible de récupérer les métadonnées via /$metadata: {str(e)}")
        
        # Fallback: liste manuelle d'endpoints courants
        schema = {
            "endpoints": [
                {
                    "name": "Items",
                    "path": "/Items",
                    "description": "Produits/articles"
                },
                {
                    "name": "BusinessPartners",
                    "path": "/BusinessPartners",
                    "description": "Partenaires commerciaux (clients, fournisseurs)"
                },
                {
                    "name": "Orders",
                    "path": "/Orders",
                    "description": "Commandes clients"
                },
                {
                    "name": "Invoices",
                    "path": "/Invoices",
                    "description": "Factures"
                },
                {
                    "name": "StockTransfers",
                    "path": "/StockTransfers",
                    "description": "Transferts de stock"
                },
                {
                    "name": "InventoryGenEntries",
                    "path": "/InventoryGenEntries",
                    "description": "Entrées de stock"
                },
                {
                    "name": "InventoryGenExits",
                    "path": "/InventoryGenExits",
                    "description": "Sorties de stock"
                }
            ],
            "update_time": datetime.utcnow().isoformat(),
            "note": "Liste manuelle des endpoints (échec de la récupération automatique)"
        }
        
        # Sauvegarder dans le cache
        save_cache(schema)
        return schema

@mcp.tool(name="ping")
async def ping() -> str:
    """Test simple de disponibilité du serveur MCP SAP"""
    return "pong! SAP MCP est opérationnel"

@mcp.tool(name="sap.read")
async def sap_read(endpoint: str, method: str = "GET", payload: Optional[dict] = None) -> dict:
    """
    Lecture de données SAP B1 via l'API REST.
    
    Args:
        endpoint: Endpoint SAP à appeler (ex: "/Items")
        method: Méthode HTTP à utiliser (GET par défaut)
        payload: Données à envoyer (pour POST)
        
    Returns:
        Un dictionnaire contenant les résultats ou une erreur
    """
    try:
        start_time = datetime.now()
        result = await call_sap(endpoint, method, payload)
        end_time = datetime.now()
        
        # Ajouter des métadonnées utiles
        if isinstance(result, dict) and "error" not in result:
            result["_metadata"] = {
                "query_time_ms": (end_time - start_time).total_seconds() * 1000,
                "endpoint": endpoint,
                "method": method
            }
        
        return result
    except Exception as e:
        logger.error(f"Erreur lors de l'appel à l'API SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap.inspect")
async def inspect_sap() -> dict:
    """
    Liste les endpoints SAP depuis le cache.
    
    Returns:
        Un dictionnaire contenant les endpoints disponibles ou une erreur
    """
    try:
        cache = load_cache()
        
        if not cache or "endpoints" not in cache:
            # Cache vide ou invalide, utiliser les données par défaut
            logger.warning("Cache SAP vide ou invalide, utilisation de valeurs par défaut")
            return {
                "endpoints": [
                    {"name": "Items", "path": "/Items"},
                    {"name": "BusinessPartners", "path": "/BusinessPartners"},
                    {"name": "Orders", "path": "/Orders"},
                    {"name": "Invoices", "path": "/Invoices"}
                ],
                "note": "Données par défaut (cache non disponible)",
                "update_time": datetime.utcnow().isoformat()
            }
        
        return cache
    except Exception as e:
        logger.error(f"Erreur lors de l'inspection SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap.refresh_metadata")
async def refresh_sap_metadata() -> dict:
    """
    Force la mise à jour des endpoints SAP.
    
    Returns:
        Un dictionnaire contenant le résultat de l'opération
    """
    try:
        start_time = datetime.now()
        schema = await fetch_sap_metadata()
        end_time = datetime.now()
        
        return {
            "status": "ok",
            "endpoints_count": len(schema.get("endpoints", [])),
            "refresh_time_ms": (end_time - start_time).total_seconds() * 1000,
            "update_time": schema.get("update_time")
        }
    except Exception as e:
        logger.error(f"Erreur lors du rafraîchissement des métadonnées SAP: {str(e)}")
        return {"error": str(e)}

@mcp.tool(name="sap.quick_search")
async def sap_quick_search(query: str, search_items: bool = True, search_partners: bool = True, limit: int = 5) -> dict:
    """
    Recherche rapide dans SAP (produits et partenaires).
    
    Args:
        query: Texte à rechercher
        search_items: Rechercher dans les produits
        search_partners: Rechercher dans les partenaires
        limit: Nombre maximal de résultats par catégorie
        
    Returns:
        Un dictionnaire contenant les résultats de la recherche
    """
    results = {
        "query": query,
        "items": [],
        "partners": []
    }
    
    try:
        # Recherche dans les produits
        if search_items:
            item_query = await call_sap(f"/Items?$filter=contains(ItemName,'{query}')&$top={limit}")
            
            if not isinstance(item_query, dict) or "error" not in item_query:
                if "value" in item_query:
                    results["items"] = [
                        {
                            "ItemCode": item.get("ItemCode"),
                            "ItemName": item.get("ItemName"),
                            "Price": item.get("Price"),
                            "OnHand": item.get("QuantityOnStock") or item.get("OnHand", 0)
                        }
                        for item in item_query.get("value", [])
                    ]
        
        # Recherche dans les partenaires
        if search_partners:
            partner_query = await call_sap(f"/BusinessPartners?$filter=contains(CardName,'{query}')&$top={limit}")
            
            if not isinstance(partner_query, dict) or "error" not in partner_query:
                if "value" in partner_query:
                    results["partners"] = [
                        {
                            "CardCode": partner.get("CardCode"),
                            "CardName": partner.get("CardName"),
                            "CardType": partner.get("CardType")
                        }
                        for partner in partner_query.get("value", [])
                    ]
        
        # Ajouter des statistiques
        results["stats"] = {
            "items_count": len(results["items"]),
            "partners_count": len(results["partners"]),
            "total_results": len(results["items"]) + len(results["partners"])
        }
        
        return results
    except Exception as e:
        logger.error(f"Erreur lors de la recherche rapide SAP: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    print("🚀 Démarrage du serveur MCP SAP...")
    mcp.run(transport="stdio")